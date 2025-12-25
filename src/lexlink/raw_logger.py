"""
Crude raw logger for PlayMCP traffic analysis.

Captures everything - request, response, headers, timing.
Save to JSONL for later analysis.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "playmcp"


def ensure_log_dir():
    """Create log directory if not exists."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file() -> Path:
    """Get today's log file path."""
    ensure_log_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"{today}.jsonl"


def log_raw(
    request_id: str,
    phase: str,  # "request" or "response"
    data: Any,
    extra: Optional[dict] = None
):
    """
    Log raw data to JSONL file.

    Args:
        request_id: Unique ID for correlating request/response
        phase: "request" or "response"
        data: Raw data (will be JSON serialized)
        extra: Additional metadata
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "request_id": request_id,
        "phase": phase,
        "data": data,
        **(extra or {})
    }

    try:
        log_file = get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        # Don't crash on logging errors
        print(f"[RAW_LOGGER] Error writing log: {e}")


def generate_request_id() -> str:
    """Generate unique request ID."""
    return str(uuid.uuid4())[:8]
