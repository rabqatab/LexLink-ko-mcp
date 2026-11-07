"""
Runtime token registry for the HTTP server.

Holds every bearer token the server accepts:
    - env user tokens   LEXLINK_AUTH_TOKENS="name:token,..."   (read at startup, not revocable)
    - env admin tokens  LEXLINK_ADMIN_TOKENS="name:token,..."  (read at startup, not revocable;
                        may also be used as normal MCP tokens)
    - issued tokens     created/revoked at runtime through the admin API and kept in a
                        JSON store file (only sha256 digests at rest, never the token)

Authentication compares sha256 digests in constant time without early exit.
A token's ``token_id`` is the first 12 hex chars of its digest (same as
``http_security.token_id_for``). Names are unique across all sources and stay
reserved after revocation, so a log's token_id always maps to one name.

Environment variables:
    LEXLINK_ADMIN_TOKENS   "name:token,..." operator tokens for /admin/* (see admin.py)
    LEXLINK_TOKEN_STORE    path of the issued-token store
                           (default: <LEXLINK_DATA_DIR or <repo>/data>/tokens.json)
    LEXLINK_DATA_DIR       base directory for the default store path
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
STORE_VERSION = 1
DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent / "data"


class TokenError(Exception):
    """Admin-facing failure with an HTTP status and a stable error code."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class TokenRecord:
    name: str
    token_id: str
    digest: str               # full sha256 hex of the token
    source: str               # "env" | "issued"
    admin: bool = False
    created_at: Optional[str] = None
    revoked_at: Optional[str] = None

    def public(self) -> dict:
        """Listing view: never contains the token or its digest."""
        d = {"name": self.name, "token_id": self.token_id, "source": self.source,
             "created_at": self.created_at, "revoked_at": self.revoked_at}
        if self.admin:
            d["admin"] = True
        return d


def _digest(token: str | bytes) -> str:
    raw = token.encode("utf-8") if isinstance(token, str) else token
    return hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_named_tokens(raw: str, var: str) -> list[tuple[str, str]]:
    """Parse ``"name:token,name2:token2"``; RuntimeError on malformed/duplicate entries."""
    pairs: list[tuple[str, str]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, token = entry.partition(":")
        name, token = name.strip(), token.strip()
        if not sep or not name or not token:
            raise RuntimeError(
                f"{var} has a malformed entry; expected 'name:token' "
                "pairs separated by commas"
            )
        if any(name == n or token == t for n, t in pairs):
            raise RuntimeError(f"{var} has a duplicate name or token")
        pairs.append((name, token))
    if not pairs:
        raise RuntimeError(f"{var} is set but contains no 'name:token' entries")
    return pairs


def default_store_path() -> Path:
    explicit = os.getenv("LEXLINK_TOKEN_STORE", "").strip()
    if explicit:
        return Path(explicit)
    base = os.getenv("LEXLINK_DATA_DIR", "").strip()
    return (Path(base) if base else DEFAULT_DATA_DIR) / "tokens.json"


class TokenRegistry:
    """Thread-safe token table; ``authenticate`` is cheap and lock-free (snapshot)."""

    def __init__(self, user_tokens=(), admin_tokens=(), store_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self.store_path = Path(store_path) if store_path else None
        records: list[TokenRecord] = []
        for admin, pairs in ((False, user_tokens), (True, admin_tokens)):
            for name, token in pairs:
                records.append(TokenRecord(
                    name=name, token_id=_digest(token)[:12], digest=_digest(token),
                    source="env", admin=admin))
        names = [r.name for r in records]
        digests = [r.digest for r in records]
        if len(set(names)) != len(names) or len(set(digests)) != len(digests):
            raise RuntimeError(
                "LEXLINK_AUTH_TOKENS and LEXLINK_ADMIN_TOKENS share a name or token")
        for r in self._load_store():
            if r.name in names or r.digest in digests:
                raise RuntimeError(
                    "the token store has a token whose name or value clashes with an "
                    "environment token; rename or remove it from the store")
            names.append(r.name)
            digests.append(r.digest)
            records.append(r)
        self._records: tuple[TokenRecord, ...] = tuple(records)

    # -- reads ------------------------------------------------------------

    def authenticate(self, presented: bytes) -> Optional[TokenRecord]:
        """Record for a valid, non-revoked token (constant-time, no early exit)."""
        digest = _digest(presented).encode("ascii")
        matched: Optional[TokenRecord] = None
        for r in self._records:
            if hmac.compare_digest(digest, r.digest.encode("ascii")) and r.revoked_at is None:
                matched = r
        return matched

    def list_tokens(self) -> list[dict]:
        return [r.public() for r in self._records]

    def name_for(self, token_id: str) -> Optional[str]:
        for r in self._records:
            if r.token_id == token_id:
                return r.name
        return None

    def ids_for_name(self, name: str) -> list[str]:
        return [r.token_id for r in self._records if r.name == name]

    # -- writes (admin API) -----------------------------------------------

    def issue(self, name: object) -> tuple[TokenRecord, str]:
        """Create a user token; returns (record, token). The token is not recoverable."""
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise TokenError(400, "invalid_name",
                             "name must match [a-z0-9][a-z0-9_-]{0,62}")
        with self._lock:
            if any(r.name == name for r in self._records):
                raise TokenError(409, "name_taken", "a token with this name already exists")
            token = secrets.token_urlsafe(32)
            rec = TokenRecord(name=name, token_id=_digest(token)[:12], digest=_digest(token),
                              source="issued", created_at=_now())
            self._commit(self._records + (rec,))
        return rec, token

    def revoke(self, name: str) -> tuple[TokenRecord, bool]:
        """Revoke an issued token; returns (record, newly_revoked)."""
        with self._lock:
            for i, r in enumerate(self._records):
                if r.name != name:
                    continue
                if r.source != "issued":
                    raise TokenError(409, "env_token_not_revocable",
                                     "environment tokens are changed in the env file")
                if r.revoked_at is not None:
                    return r, False
                done = TokenRecord(**{**r.__dict__, "revoked_at": _now()})
                self._commit(self._records[:i] + (done,) + self._records[i + 1:])
                return done, True
        raise TokenError(404, "not_found", "no token with this name")

    # -- store ------------------------------------------------------------

    def _commit(self, records: tuple[TokenRecord, ...]) -> None:
        """Persist first, then swap the in-memory table (a failed write changes nothing)."""
        if self.store_path is None:
            raise TokenError(503, "store_unavailable", "no token store is configured")
        issued = [
            {"name": r.name, "token_id": r.token_id, "sha256": r.digest,
             "created_at": r.created_at, "revoked_at": r.revoked_at}
            for r in records if r.source == "issued"
        ]
        try:
            self._write_store({"version": STORE_VERSION, "tokens": issued})
        except OSError as exc:
            logger.error("token store write failed: %s", type(exc).__name__)
            raise TokenError(503, "store_write_failed", "could not write the token store") from None
        self._records = records

    def _write_store(self, data: dict) -> None:
        path = self.store_path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tokens-", suffix=".tmp", dir=path.parent)  # 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _load_store(self) -> list[TokenRecord]:
        if self.store_path is None or not self.store_path.exists():
            return []
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if data.get("version") != STORE_VERSION:
                raise ValueError("unsupported version")
            out = []
            for t in data["tokens"]:
                digest = t["sha256"]
                if not (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
                        and NAME_RE.fullmatch(t["name"])):
                    raise ValueError("bad entry")
                out.append(TokenRecord(
                    name=t["name"], token_id=digest[:12], digest=digest, source="issued",
                    created_at=t.get("created_at"), revoked_at=t.get("revoked_at")))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # fail closed: guessing could resurrect revoked tokens
            raise RuntimeError(
                f"token store {self.store_path} is unreadable or malformed; "
                "fix or remove it (revoked tokens would become unknown)"
            ) from None
        if len({r.name for r in out}) != len(out):
            raise RuntimeError(f"token store {self.store_path} has duplicate names")
        return out


def build_registry(auth_tokens: list[tuple[str, str]], admin_tokens: list[tuple[str, str]]
                   ) -> TokenRegistry:
    return TokenRegistry(auth_tokens, admin_tokens, default_store_path())
