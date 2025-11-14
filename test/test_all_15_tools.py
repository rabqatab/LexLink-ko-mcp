"""
Comprehensive E2E Test - All 15 MCP Tools.

This test verifies that ALL 15 LexLink tools work correctly
by making actual API calls to law.go.kr through the MCP protocol.
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from test.utils.mcp_client import MCPClient
from test.utils.logger import TestLogger


class AllToolsE2ETest:
    """Comprehensive test suite for all 15 LexLink tools."""

    def __init__(self, oc: str, server_url: str = "http://127.0.0.1:8081"):
        self.oc = oc
        self.server_url = server_url
        self.logger = TestLogger("lexlink_all_tools_test")

        self.logger.log_config({
            "oc": oc,
            "server_url": server_url,
            "test_type": "comprehensive_all_tools"
        })

        self.mcp = MCPClient(
            base_url=server_url,
            session_config={"oc": oc}
        )

    def _test_tool(self, tool_name: str, params: dict, test_number: int) -> str:
        """
        Helper to test a tool and log results.

        Returns: "PASS" or "FAIL: error message"
        """
        print(f"\n[{test_number}/15] Testing {tool_name}...")
        try:
            result = self.mcp.call_tool(tool_name, params)

            # Log MCP call
            call_log = self.mcp.get_call_log()
            if call_log:
                last_call = call_log[-1]
                self.logger.log_mcp_call(
                    last_call["method"],
                    last_call["params"],
                    last_call["response"],
                    last_call["elapsed_ms"]
                )

            parsed = json.loads(result["result"]["content"][0]["text"])
            assert parsed["status"] == "ok", f"{tool_name} failed: {parsed}"

            print(f"  ✓ {tool_name}: SUCCESS")

            # Log result
            self.logger.log_result(tool_name, {
                "status": "PASS",
                "params": params,
                "response_status": parsed["status"],
                "request_id": parsed.get("request_id")
            })

            return "PASS"
        except Exception as e:
            print(f"  ✗ {tool_name}: FAIL - {e}")
            self.logger.log_result(tool_name, {
                "status": "FAIL",
                "error": str(e),
                "params": params
            })
            return f"FAIL: {e}"

    def test_phase1_core_law_apis(self) -> dict:
        """Test Phase 1: Core Law APIs (6 tools)."""
        print("\n=== Phase 1: Core Law APIs (6 tools) ===")

        return {
            "eflaw_search": self._test_tool("eflaw_search", {"query": "자동차관리법", "display": 5, "type": "XML"}, 1),
            "law_search": self._test_tool("law_search", {"query": "민법", "display": 5, "type": "XML"}, 2),
            "eflaw_service": self._test_tool("eflaw_service", {"id": "001823", "type": "XML"}, 3),
            "law_service": self._test_tool("law_service", {"id": "001823", "type": "XML"}, 4),
            "eflaw_josub": self._test_tool("eflaw_josub", {"id": "001823", "jo": "000100", "type": "XML"}, 5),
            "law_josub": self._test_tool("law_josub", {"id": "001823", "jo": "000100", "type": "XML"}, 6),
        }

    def test_phase2_english_laws(self) -> dict:
        """Test Phase 2: English Laws (2 tools)."""
        print("\n=== Phase 2: English Laws (2 tools) ===")

        return {
            "elaw_search": self._test_tool("elaw_search", {"query": "insurance", "display": 5, "type": "XML"}, 7),
            "elaw_service": self._test_tool("elaw_service", {"id": "000744", "type": "XML"}, 8),
        }

    def test_phase2_administrative_rules(self) -> dict:
        """Test Phase 2: Administrative Rules (2 tools)."""
        print("\n=== Phase 2: Administrative Rules (2 tools) ===")

        return {
            "admrul_search": self._test_tool("admrul_search", {"query": "학교", "display": 5, "type": "XML"}, 9),
            "admrul_service": self._test_tool("admrul_service", {"id": "62505", "type": "XML"}, 10),
        }

    def test_phase2_law_ordinance_linkage(self) -> dict:
        """Test Phase 2: Law-Ordinance Linkage (4 tools)."""
        print("\n=== Phase 2: Law-Ordinance Linkage (4 tools) ===")

        return {
            "lnkLs_search": self._test_tool("lnkLs_search", {"query": "건축법", "display": 5, "type": "XML"}, 11),
            "lnkLsOrdJo_search": self._test_tool("lnkLsOrdJo_search", {"knd": "002118", "display": 5, "type": "XML"}, 12),
            "lnkDep_search": self._test_tool("lnkDep_search", {"org": "1400000", "display": 5, "type": "XML"}, 13),
            "drlaw_search": self._test_tool("drlaw_search", {}, 14),
        }

    def test_phase2_delegated_laws(self) -> dict:
        """Test Phase 2: Delegated Laws (1 tool)."""
        print("\n=== Phase 2: Delegated Laws (1 tool) ===")

        return {
            "lsDelegated_service": self._test_tool("lsDelegated_service", {"id": "000900", "type": "XML"}, 15),
        }

    def run_all_tests(self) -> dict:
        """Run all 15 tool tests."""
        print("\n" + "="*60)
        print("LexLink - Comprehensive Test for All 15 Tools")
        print("="*60)

        # Initialize MCP session
        self.mcp.initialize()

        # Run all test phases
        all_results = {}
        all_results.update(self.test_phase1_core_law_apis())
        all_results.update(self.test_phase2_english_laws())
        all_results.update(self.test_phase2_administrative_rules())
        all_results.update(self.test_phase2_law_ordinance_linkage())
        all_results.update(self.test_phase2_delegated_laws())

        # Summary
        print("\n" + "="*60)
        print("Test Summary - All 15 Tools")
        print("="*60)

        passed = sum(1 for v in all_results.values() if v == "PASS")
        failed = len(all_results) - passed

        for tool_name, status in all_results.items():
            symbol = "✓" if status == "PASS" else "✗"
            print(f"{symbol} {tool_name}: {status}")

        print(f"\n{passed}/{len(all_results)} tests passed")

        if failed > 0:
            print(f"⚠️  {failed} tests failed!")
        else:
            print("🎉 All tests passed!")

        # Finalize logging
        json_path, md_path = self.logger.finalize()
        print(f"\n📄 Detailed logs saved:")
        print(f"   JSON: {json_path}")
        print(f"   Markdown: {md_path}")

        # Close MCP client
        self.mcp.close()

        return {
            "passed": passed,
            "failed": failed,
            "total": len(all_results),
            "results": all_results,
            "log_files": {
                "json": str(json_path),
                "markdown": str(md_path)
            }
        }


def main():
    """Main test runner."""
    oc = os.getenv("LAW_OC", "ddongle0205")

    print(f"Configuration:")
    print(f"  OC: {oc}")
    print(f"  Server: http://127.0.0.1:8081")

    # Check if server is running
    import httpx
    try:
        httpx.get("http://127.0.0.1:8081", timeout=2.0)
    except (httpx.ConnectError, httpx.TimeoutException):
        print("\n⚠️  Warning: Server doesn't appear to be running")
        print("Please start the server first with: uv run dev")
        sys.exit(1)

    # Run tests
    test_suite = AllToolsE2ETest(oc=oc)
    results = test_suite.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
