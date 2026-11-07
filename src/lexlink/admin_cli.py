"""
Command line client for the admin API (``uv run lexlink-admin ...``).

Environment:
    LEXLINK_ADMIN_URL    server base URL, e.g. https://mcp.example.com
    LEXLINK_ADMIN_TOKEN  an admin token (LEXLINK_ADMIN_TOKENS on the server)

Commands:
    lexlink-admin tokens list
    lexlink-admin tokens issue NAME      token alone on stdout, details on stderr
    lexlink-admin tokens revoke NAME
    lexlink-admin logs [--date D | --from D --to D] [--limit N] [--token NAME]
                       [--token-id ID] [--tool NAME] [--status ok|error]
                       [--client NAME] [--method M]

Results are printed as JSON on stdout. The admin token is never printed.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 30


def _request(method: str, path: str, *, query: dict | None = None, body: dict | None = None):
    base = os.getenv("LEXLINK_ADMIN_URL", "").strip().rstrip("/")
    token = os.getenv("LEXLINK_ADMIN_TOKEN", "").strip()
    if not base or not token:
        print("set LEXLINK_ADMIN_URL and LEXLINK_ADMIN_TOKEN", file=sys.stderr)
        raise SystemExit(2)
    url = base + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"{}")
        except ValueError:
            payload = {}
        return exc.code, payload
    except (urllib.error.URLError, OSError) as exc:
        print(f"request failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)


def _fail(status: int, payload: dict) -> int:
    print(f"error {status}: {payload.get('error', '?')}: {payload.get('message', '')}",
          file=sys.stderr)
    return 1


def _dump(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lexlink-admin", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tokens", help="manage user tokens").add_subparsers(
        dest="action", required=True)
    t.add_parser("list")
    t.add_parser("issue").add_argument("name")
    t.add_parser("revoke").add_argument("name")
    lg = sub.add_parser("logs", help="query request logs")
    lg.add_argument("--date")
    lg.add_argument("--from", dest="from_")
    lg.add_argument("--to")
    lg.add_argument("--limit", type=int)
    lg.add_argument("--token", help="token name")
    lg.add_argument("--token-id")
    lg.add_argument("--tool", help="tool_name")
    lg.add_argument("--status")
    lg.add_argument("--client", help="client_name")
    lg.add_argument("--method")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "logs":
        query = {k: v for k, v in {
            "date": args.date, "from": args.from_, "to": args.to, "limit": args.limit,
            "token": args.token, "token_id": args.token_id, "tool_name": args.tool,
            "status": args.status, "client_name": args.client, "method": args.method,
        }.items() if v is not None}
        status, payload = _request("GET", "/admin/logs", query=query)
    elif args.action == "list":
        status, payload = _request("GET", "/admin/tokens")
    elif args.action == "issue":
        status, payload = _request("POST", "/admin/tokens", body={"name": args.name})
        if status == 201:
            print(f"issued {payload['name']} (token_id {payload['token_id']}); "
                  "this is the only time the token is shown", file=sys.stderr)
            print(payload["token"])
            return 0
    else:
        status, payload = _request(
            "DELETE", "/admin/tokens/" + urllib.parse.quote(args.name, safe=""))
    if status >= 400:
        return _fail(status, payload)
    _dump(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
