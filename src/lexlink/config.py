"""
Session configuration schema for LexLink MCP server.

This module defines the configuration options that can be set by users
through Smithery's session management interface.
"""

from pydantic import BaseModel, Field


class LexLinkConfig(BaseModel):
    """
    Session configuration schema for LexLink MCP server.

    Users can provide these settings via Smithery URL query parameters
    or the Smithery UI session configuration panel.

    Example URL: http://127.0.0.1:8081/mcp?oc=g4c
    """

    oc: str = Field(
        default="test",
        description=(
            "User identifier (email local part). Required for law.go.kr API. "
            "Example: g4c@korea.kr → g4c. Defaults to 'test' for demo purposes."
        )
    )

    base_url: str = Field(
        default="http://www.law.go.kr",
        description="Base URL for law.go.kr API (override for testing)"
    )

    http_timeout_s: int = Field(
        default=15,
        ge=5,
        le=60,
        description="HTTP request timeout in seconds (5-60)"
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "oc": "g4c",
                "base_url": "http://www.law.go.kr",
                "http_timeout_s": 15
            }
        }
