"""Stdio transport entry point for LexLink MCP server."""

from .server import create_server


def main():
    """Run LexLink MCP server over stdio transport."""
    create_server().run()


if __name__ == "__main__":
    main()
