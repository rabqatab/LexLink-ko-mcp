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

    http_timeout_s: int = Field(
        default=60,
        ge=5,
        le=120,
        description="HTTP request timeout in seconds (5-120)"
    )

    # Internal field - not exposed in Smithery UI (no Field description)
    base_url: str = "http://www.law.go.kr"

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "oc": "g4c",
                "http_timeout_s": 60
            }
        }
