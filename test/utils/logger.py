"""
Test Logger - Structured logging to files.

Logs test inputs, MCP calls, and outputs to JSON and markdown files
in the test/logs directory.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class TestLogger:
    """Structured logger for test execution."""

    def __init__(self, test_name: str, log_dir: str = "test/logs"):
        """
        Initialize test logger.

        Args:
            test_name: Name of the test (used for log file names)
            log_dir: Directory for log files
        """
        self.test_name = test_name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_data: Dict[str, Any] = {
            "test_name": test_name,
            "start_time": datetime.now().isoformat(),
            "test_config": {},
            "mcp_calls": [],
            "llm_interactions": [],
            "results": {},
            "end_time": None,
        }

    def log_config(self, config: Dict[str, Any]):
        """
        Log test configuration.

        Args:
            config: Configuration dictionary
        """
        self.log_data["test_config"] = config

    def log_mcp_call(
        self,
        method: str,
        params: Dict[str, Any],
        response: Dict[str, Any],
        elapsed_ms: int
    ):
        """
        Log an MCP protocol call.

        Args:
            method: MCP method name
            params: Request parameters
            response: Response data
            elapsed_ms: Elapsed time in milliseconds
        """
        self.log_data["mcp_calls"].append({
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "params": params,
            "response": response,
            "elapsed_ms": elapsed_ms,
        })

    def log_llm_interaction(
        self,
        prompt: str,
        response: str,
        model: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Log LLM interaction.

        Args:
            prompt: Prompt sent to LLM
            response: LLM response
            model: Model name (e.g., "gemini-1.5-pro")
            tool_calls: Tool calls made by LLM (if any)
        """
        self.log_data["llm_interactions"].append({
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "prompt": prompt,
            "response": response,
            "tool_calls": tool_calls or [],
        })

    def log_result(self, result_key: str, result_value: Any):
        """
        Log a test result.

        Args:
            result_key: Result identifier
            result_value: Result data
        """
        self.log_data["results"][result_key] = result_value

    def finalize(self):
        """Finalize logging and write to files."""
        self.log_data["end_time"] = datetime.now().isoformat()

        # Calculate duration
        start = datetime.fromisoformat(self.log_data["start_time"])
        end = datetime.fromisoformat(self.log_data["end_time"])
        duration_s = (end - start).total_seconds()
        self.log_data["duration_seconds"] = duration_s

        # Write JSON log
        json_path = self.log_dir / f"{self.test_name}_{self.timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.log_data, f, indent=2, ensure_ascii=False)

        # Write Markdown report
        md_path = self.log_dir / f"{self.test_name}_{self.timestamp}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            self._write_markdown_report(f)

        return json_path, md_path

    def _write_markdown_report(self, f):
        """Write human-readable markdown report."""
        f.write(f"# Test Report: {self.log_data['test_name']}\n\n")
        f.write(f"**Start Time:** {self.log_data['start_time']}  \n")
        f.write(f"**End Time:** {self.log_data['end_time']}  \n")
        f.write(f"**Duration:** {self.log_data['duration_seconds']:.2f}s\n\n")

        # Configuration
        f.write("## Test Configuration\n\n")
        f.write("```json\n")
        f.write(json.dumps(self.log_data["test_config"], indent=2))
        f.write("\n```\n\n")

        # MCP Calls
        f.write(f"## MCP Protocol Calls ({len(self.log_data['mcp_calls'])} total)\n\n")
        for i, call in enumerate(self.log_data["mcp_calls"], 1):
            f.write(f"### {i}. {call['method']} ({call['elapsed_ms']}ms)\n\n")
            f.write("**Request:**\n```json\n")
            f.write(json.dumps(call["params"], indent=2, ensure_ascii=False))
            f.write("\n```\n\n")
            f.write("**Response:**\n```json\n")
            f.write(json.dumps(call["response"], indent=2, ensure_ascii=False))
            f.write("\n```\n\n")

        # LLM Interactions
        if self.log_data["llm_interactions"]:
            f.write(f"## LLM Interactions ({len(self.log_data['llm_interactions'])} total)\n\n")
            for i, interaction in enumerate(self.log_data["llm_interactions"], 1):
                f.write(f"### {i}. {interaction['model']}\n\n")
                f.write(f"**Prompt:**\n```\n{interaction['prompt']}\n```\n\n")
                f.write(f"**Response:**\n```\n{interaction['response']}\n```\n\n")
                if interaction["tool_calls"]:
                    f.write("**Tool Calls:**\n```json\n")
                    f.write(json.dumps(interaction["tool_calls"], indent=2))
                    f.write("\n```\n\n")

        # Results
        f.write("## Test Results\n\n")
        for key, value in self.log_data["results"].items():
            f.write(f"**{key}:**  \n")
            if isinstance(value, (dict, list)):
                f.write("```json\n")
                f.write(json.dumps(value, indent=2, ensure_ascii=False))
                f.write("\n```\n\n")
            else:
                f.write(f"{value}\n\n")
