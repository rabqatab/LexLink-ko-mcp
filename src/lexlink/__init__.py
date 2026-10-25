"""LexLink - Korean Law API MCP Server."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Fallback used only when the package metadata is unavailable (e.g. running
# from a plain source checkout without an install). Keep in sync with
# pyproject.toml [project].version.
_FALLBACK_VERSION = "2.1.0"

try:
    __version__ = _pkg_version("lexlink")
except PackageNotFoundError:  # pragma: no cover - depends on install state
    __version__ = _FALLBACK_VERSION

__all__ = ["__version__"]
