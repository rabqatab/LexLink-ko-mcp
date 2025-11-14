"""
Semantic Validation Test - Verify All 15 MCPs Return Meaningful Data.

This test validates that all 15 MCP tools return:
1. Functionally correct responses (MCP protocol works)
2. Semantically plausible responses (actual law data, not error pages)

For each tool, we check:
- MCP call succeeds (status = "ok")
- Response contains actual structured law data (XML/JSON)
- Not just HTML error pages
- Data fields are populated with meaningful values
"""

import json
import os
import sys
import re
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from test.utils.mcp_client import MCPClient
from test.utils.logger import TestLogger


class SemanticValidationTest:
    """Semantic validation test suite for all 15 tools."""

    def __init__(
        self,
        oc: str,
        server_url: str = "http://127.0.0.1:8081"
    ):
        """
        Initialize semantic validation test.

        Args:
            oc: law.go.kr OC identifier
            server_url: LexLink server URL
        """
        self.oc = oc
        self.server_url = server_url

        # Initialize logger
        self.logger = TestLogger("lexlink_semantic_validation")

        # Log test configuration
        self.logger.log_config({
            "oc": oc,
            "server_url": server_url,
            "test_type": "semantic_validation_all_15_tools"
        })

        # Initialize MCP client
        self.mcp = MCPClient(
            base_url=server_url,
            session_config={"oc": oc}
        )

    def _is_html_error(self, content: str) -> bool:
        """Check if content is an HTML error page."""
        html_indicators = [
            "<!DOCTYPE html",
            "<html",
            "미신청된 목록/본문",
            "error500",
            "OPEN API 신청"
        ]
        return any(indicator in content for indicator in html_indicators)

    def _is_xml_data(self, content: str) -> bool:
        """Check if content is valid XML law data."""
        if not content.strip().startswith("<?xml"):
            return False

        # Check for law data XML tags
        law_xml_tags = [
            "<LawSearch>",
            "<Law>",
            "<법령>",
            "<조문>",
            "<AdmRulSearch>",
            "<행정규칙>"
        ]
        return any(tag in content for tag in law_xml_tags)

    def _validate_xml_content(self, content: str) -> Dict[str, Any]:
        """
        Validate XML content has meaningful law data.

        Returns dict with:
        - has_data: bool
        - record_count: int
        - sample_fields: list of field names found
        """
        if not self._is_xml_data(content):
            return {"has_data": False, "reason": "Not valid XML law data"}

        # Count law records
        law_count = content.count("<law ") + content.count("<법령>")
        article_count = content.count("<조문>")

        # Extract sample field names
        field_pattern = r"<([^/>]+)>"
        fields = set(re.findall(field_pattern, content)[:20])  # First 20 unique fields

        has_meaningful_data = (
            law_count > 0 or
            article_count > 0 or
            "법령명" in content or
            "조문내용" in content
        )

        return {
            "has_data": has_meaningful_data,
            "law_count": law_count,
            "article_count": article_count,
            "sample_fields": sorted(list(fields))[:10],
            "total_length": len(content)
        }

    def _test_tool(
        self,
        tool_name: str,
        params: dict,
        test_number: int,
        description: str
    ) -> Dict[str, Any]:
        """
        Test a tool and validate semantic correctness.

        Returns test result with semantic analysis.
        """
        print(f"\n[{test_number}/15] Testing {tool_name}...")
        print(f"  Description: {description}")

        result = {
            "tool": tool_name,
            "params": params,
            "functional": {"status": "unknown"},
            "semantic": {"status": "unknown"}
        }

        try:
            # Call MCP tool
            mcp_result = self.mcp.call_tool(tool_name, params)

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

            # Parse MCP response
            parsed = json.loads(mcp_result["result"]["content"][0]["text"])

            # Functional validation
            if parsed["status"] == "ok":
                result["functional"] = {
                    "status": "PASS",
                    "request_id": parsed.get("request_id"),
                    "upstream_type": parsed.get("upstream_type")
                }
                print(f"  ✓ Functional: MCP call succeeded")
            else:
                result["functional"] = {
                    "status": "FAIL",
                    "error": parsed.get("message", "Unknown error")
                }
                print(f"  ✗ Functional: {parsed.get('message', 'Unknown error')}")
                result["semantic"] = {
                    "status": "SKIP",
                    "reason": "Functional test failed"
                }
                return result

            # Semantic validation
            raw_content = parsed.get("raw_content", "")

            # Check if HTML error page
            if self._is_html_error(raw_content):
                result["semantic"] = {
                    "status": "FAIL",
                    "reason": "HTML error page (permission denied)",
                    "message": "API access not authorized for this law type"
                }
                print(f"  ✗ Semantic: Permission denied (HTML error page)")

            # Check if valid XML law data
            elif self._is_xml_data(raw_content):
                validation = self._validate_xml_content(raw_content)

                if validation["has_data"]:
                    result["semantic"] = {
                        "status": "PASS",
                        "law_count": validation.get("law_count", 0),
                        "article_count": validation.get("article_count", 0),
                        "sample_fields": validation["sample_fields"],
                        "content_length": validation["total_length"]
                    }
                    print(f"  ✓ Semantic: Valid law data")
                    print(f"    - Laws: {validation.get('law_count', 0)}")
                    print(f"    - Articles: {validation.get('article_count', 0)}")
                    print(f"    - Fields: {', '.join(validation['sample_fields'][:5])}")
                else:
                    result["semantic"] = {
                        "status": "WARN",
                        "reason": "XML structure but no law data detected",
                        "details": validation
                    }
                    print(f"  ⚠ Semantic: XML but no clear law data")

            # Unknown format
            else:
                result["semantic"] = {
                    "status": "WARN",
                    "reason": "Unknown response format",
                    "content_preview": raw_content[:200]
                }
                print(f"  ⚠ Semantic: Unknown format")

            # Overall status
            overall = "PASS" if (
                result["functional"]["status"] == "PASS" and
                result["semantic"]["status"] == "PASS"
            ) else (
                "PARTIAL" if result["functional"]["status"] == "PASS"
                else "FAIL"
            )

            result["overall"] = overall

            # Log result
            self.logger.log_result(tool_name, result)

            return result

        except Exception as e:
            print(f"  ✗ Exception: {e}")
            result["functional"] = {"status": "ERROR", "error": str(e)}
            result["semantic"] = {"status": "SKIP", "reason": "Exception occurred"}
            result["overall"] = "ERROR"

            self.logger.log_result(tool_name, result)
            return result

    def run_all_tests(self) -> Dict[str, Any]:
        """Run semantic validation for all 15 tools."""
        print("\n" + "="*80)
        print("LexLink Semantic Validation - All 15 MCP Tools")
        print("Testing: Functional correctness + Semantic plausibility")
        print("="*80)

        # Initialize MCP session
        self.mcp.initialize()

        # Define all 15 tool tests
        test_cases = [
            # Phase 1: Core Law APIs (6 tools)
            {
                "tool": "eflaw_search",
                "params": {"query": "자동차", "display": 3, "type": "XML"},
                "description": "Search current laws (효력별 법령 검색)"
            },
            {
                "tool": "law_search",
                "params": {"query": "민법", "display": 3, "type": "XML"},
                "description": "Search all laws (통합 법령 검색)"
            },
            {
                "tool": "eflaw_service",
                "params": {"id": "001823", "type": "XML"},
                "description": "Get current law details (효력별 법령 상세)"
            },
            {
                "tool": "law_service",
                "params": {"id": "001823", "type": "XML"},
                "description": "Get law details (통합 법령 상세)"
            },
            {
                "tool": "eflaw_josub",
                "params": {"id": "001823", "jo": "000100", "type": "XML"},
                "description": "Get current law article (효력별 조문)"
            },
            {
                "tool": "law_josub",
                "params": {"id": "001823", "jo": "000100", "type": "XML"},
                "description": "Get law article (통합 조문)"
            },

            # Phase 2: English Laws (2 tools)
            {
                "tool": "elaw_search",
                "params": {"query": "insurance", "display": 3, "type": "XML"},
                "description": "Search English-translated laws (영문법령 검색)"
            },
            {
                "tool": "elaw_service",
                "params": {"id": "009589", "type": "XML"},
                "description": "Get English law details (영문법령 상세)"
            },

            # Phase 2: Administrative Rules (2 tools)
            {
                "tool": "admrul_search",
                "params": {"query": "학교", "display": 3, "type": "XML"},
                "description": "Search administrative rules (행정규칙 검색)"
            },
            {
                "tool": "admrul_service",
                "params": {"id": "62505", "type": "XML"},
                "description": "Get administrative rule details (행정규칙 상세)"
            },

            # Phase 2: Law-Ordinance Linkage (4 tools)
            {
                "tool": "lnkLs_search",
                "params": {"query": "건축", "display": 3, "type": "XML"},
                "description": "Search law-ordinance links (법령-자치법규 연계)"
            },
            {
                "tool": "lnkLsOrdJo_search",
                "params": {"knd": "002118", "display": 3, "type": "XML"},
                "description": "Search ordinance articles by law (조례규칙별 법령 조문 검색)"
            },
            {
                "tool": "lnkDep_search",
                "params": {"org": "1400000", "display": 3, "type": "XML"},
                "description": "Search by department (소관 부처별 검색)"
            },
            {
                "tool": "drlaw_search",
                "params": {},
                "description": "Get linkage statistics (법령-자치법규 연계현황)"
            },

            # Phase 2: Delegated Laws (1 tool)
            {
                "tool": "lsDelegated_service",
                "params": {"id": "000900", "type": "XML"},
                "description": "Get delegated law info (위임법령 정보)"
            }
        ]

        # Run all tests
        results = []
        for i, test_case in enumerate(test_cases, 1):
            result = self._test_tool(
                tool_name=test_case["tool"],
                params=test_case["params"],
                test_number=i,
                description=test_case["description"]
            )
            results.append(result)

        # Generate summary
        print("\n" + "="*80)
        print("Summary - Semantic Validation Results")
        print("="*80)

        # Count by overall status
        pass_count = sum(1 for r in results if r["overall"] == "PASS")
        partial_count = sum(1 for r in results if r["overall"] == "PARTIAL")
        fail_count = sum(1 for r in results if r["overall"] == "FAIL")
        error_count = sum(1 for r in results if r["overall"] == "ERROR")

        # Print detailed results
        print("\nDetailed Results:")
        print("-" * 80)
        print(f"{'#':<4} {'Tool':<25} {'Functional':<12} {'Semantic':<12} {'Overall':<10}")
        print("-" * 80)

        for i, result in enumerate(results, 1):
            func_status = result["functional"]["status"]
            sem_status = result["semantic"]["status"]
            overall = result["overall"]

            # Status symbols
            func_symbol = "✓" if func_status == "PASS" else ("✗" if func_status in ["FAIL", "ERROR"] else "⚠")
            sem_symbol = "✓" if sem_status == "PASS" else ("✗" if sem_status == "FAIL" else "⊘" if sem_status == "SKIP" else "⚠")
            overall_symbol = "✓" if overall == "PASS" else ("◐" if overall == "PARTIAL" else "✗")

            print(f"{i:<4} {result['tool']:<25} {func_symbol} {func_status:<10} {sem_symbol} {sem_status:<10} {overall_symbol} {overall:<8}")

        print("-" * 80)
        print(f"\nOverall Summary:")
        print(f"  ✓ PASS:    {pass_count}/15 tools (functional + semantic)")
        print(f"  ◐ PARTIAL: {partial_count}/15 tools (functional only, semantic issues)")
        print(f"  ✗ FAIL:    {fail_count}/15 tools (functional failed)")
        print(f"  ✗ ERROR:   {error_count}/15 tools (exceptions)")

        # Categorize by semantic status
        print(f"\nSemantic Analysis:")
        sem_pass = sum(1 for r in results if r["semantic"]["status"] == "PASS")
        sem_fail = sum(1 for r in results if r["semantic"]["status"] == "FAIL")
        sem_warn = sum(1 for r in results if r["semantic"]["status"] == "WARN")
        sem_skip = sum(1 for r in results if r["semantic"]["status"] == "SKIP")

        print(f"  ✓ Valid law data:     {sem_pass}/15 tools")
        print(f"  ✗ Permission denied:  {sem_fail}/15 tools")
        print(f"  ⚠ Warning:            {sem_warn}/15 tools")
        print(f"  ⊘ Skipped:            {sem_skip}/15 tools")

        # Recommendations
        if sem_fail > 0:
            print(f"\n⚠️  Recommendation:")
            print(f"   {sem_fail} tools have permission errors. To fix:")
            print(f"   1. Visit https://open.law.go.kr/LSO/main.do")
            print(f"   2. Go to [OPEN API] → [OPEN API 신청]")
            print(f"   3. Enable these law types (법령종류):")

            denied_tools = [r for r in results if r["semantic"].get("reason") == "HTML error page (permission denied)"]
            tool_categories = {
                "법령": ["eflaw_search", "law_search", "eflaw_service", "law_service", "eflaw_josub", "law_josub"],
                "행정규칙": ["admrul_search", "admrul_service"],
                "법령-자치법규 연계": ["lnkLs_search", "lnkLsOrdJo_search", "lnkDep_search", "drlaw_search"],
                "위임법령": ["lsDelegated_service"]
            }

            needed_categories = set()
            for result in denied_tools:
                for category, tools in tool_categories.items():
                    if result["tool"] in tools:
                        needed_categories.add(category)

            for category in sorted(needed_categories):
                print(f"      - {category}")

        # Finalize logging
        json_path, md_path = self.logger.finalize()
        print(f"\n📄 Detailed logs saved:")
        print(f"   JSON: {json_path}")
        print(f"   Markdown: {md_path}")

        # Close MCP client
        self.mcp.close()

        return {
            "total": len(results),
            "pass": pass_count,
            "partial": partial_count,
            "fail": fail_count,
            "error": error_count,
            "semantic_pass": sem_pass,
            "semantic_fail": sem_fail,
            "results": results,
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
    test_suite = SemanticValidationTest(oc=oc)
    results = test_suite.run_all_tests()

    # Exit with appropriate code
    # Success if all pass or at least functional passes
    success = (results["fail"] == 0 and results["error"] == 0)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
