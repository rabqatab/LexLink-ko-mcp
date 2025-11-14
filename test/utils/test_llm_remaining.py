"""
Run remaining LLM integration tests (10-15) with rate limit handling.
This script runs tests one at a time with delays between them.
"""

import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test.test_llm_integration import LLMIntegrationTest

def main():
    """Run tests 10-15 with delays."""
    # Load configuration
    oc = os.getenv("LAW_OC", "ddongle0205")

    # Get API keys
    gemini_keys_str = os.getenv("GOOGLE_API_KEYS", "")
    if not gemini_keys_str:
        print("⚠️  GOOGLE_API_KEYS environment variable not set")
        sys.exit(1)

    gemini_keys = [k.strip() for k in gemini_keys_str.split(",")]
    print(f"Configuration:")
    print(f"  OC: {oc}")
    print(f"  API Keys available: {len(gemini_keys)}")
    print(f"  Server: http://127.0.0.1:8081")

    # Create test suite with first API key
    os.environ["GOOGLE_API_KEY"] = gemini_keys[0]
    test_suite = LLMIntegrationTest(oc=oc, gemini_api_key=gemini_keys[0])

    # Setup Gemini with tools
    if not test_suite.setup_gemini_with_tools():
        print("\n⚠️  Cannot run tests: Gemini setup failed")
        test_suite.mcp.close()
        sys.exit(1)

    print("\n" + "="*70)
    print("Running Remaining Tests (10-15) with Rate Limit Handling")
    print("="*70)

    # Define remaining tests
    remaining_tests = [
        ("test_10_admrul_service", "행정규칙 ID 62505의 상세 정보를 조회해주세요."),
        ("test_11_lnkLs_search", "'건축'과 관련된 법령-자치법규 연계 정보를 3개만 찾아주세요."),
        ("test_12_lnkLsOrdJo_search", "법령 종류 코드 002118에 해당하는 조례규칙별 법령 조문을 3개만 검색해주세요."),
        ("test_13_lnkDep_search", "소관 부처 코드 1400000(국토교통부)의 법령을 3개만 검색해주세요."),
        ("test_14_drlaw_search", "법령-자치법규 연계 현황 통계를 가져와주세요."),
        ("test_15_lsDelegated_service", "법령 ID 000900의 위임법령 정보를 조회해주세요."),
    ]

    test_results = {}

    for i, (test_name, query) in enumerate(remaining_tests, start=1):
        print(f"\n[{i}/{len(remaining_tests)}] Running {test_name}...")

        # Run test
        result = test_suite.test_llm_query_with_tools(
            query=query,
            test_name=test_name
        )

        test_results[test_name] = result

        # If test passed, wait before next test to respect rate limits
        if result.get("status") == "PASS":
            if i < len(remaining_tests):  # Don't wait after last test
                wait_time = 10  # 10 seconds between tests
                print(f"  ⏳ Waiting {wait_time}s before next test (rate limit handling)...")
                time.sleep(wait_time)
        else:
            # If test failed due to rate limit, wait longer
            error_msg = result.get("error", "")
            if "429" in error_msg or "ResourceExhausted" in error_msg:
                wait_time = 60  # 60 seconds for rate limit errors
                print(f"  ⏳ Rate limit hit, waiting {wait_time}s before retry...")
                time.sleep(wait_time)

    # Summary
    print("\n" + "="*70)
    print("Test Summary (Remaining Tests)")
    print("="*70)

    passed = sum(1 for v in test_results.values() if v.get("status") == "PASS")
    failed = sum(1 for v in test_results.values() if v.get("status") == "FAIL")
    total = len(test_results)

    for test_name, result in test_results.items():
        status = result.get("status", "UNKNOWN")
        if status == "PASS":
            tools_used = result.get("tools_used", [])
            print(f"✓ {test_name}: PASS (used {len(tools_used)} tools)")
        else:
            print(f"✗ {test_name}: FAIL - {result.get('error', 'Unknown error')[:100]}")

    print(f"\nTotal: {passed} passed, {failed} failed (out of {total})")

    # Close MCP client
    test_suite.mcp.close()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
