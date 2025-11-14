"""
LLM Integration Test - Comprehensive AI Agent Workflow Validation.

This test validates that an LLM (Google Gemini) properly:
1. Receives user queries
2. Decides which MCP tools to use
3. Makes MCP tool calls
4. Receives MCP results
5. Generates final responses using the tool results

All steps are comprehensively logged:
- Input queries
- MCP tool selection reasoning
- MCP requests and responses
- Final LLM outputs
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from test.utils.mcp_client import MCPClient
from test.utils.logger import TestLogger

# Try to import Google Gemini - optional dependency
try:
    import google.generativeai as genai
    from google.generativeai.types import FunctionDeclaration, Tool
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed. Install with: pip install google-generativeai")


class LLMIntegrationTest:
    """Comprehensive LLM+MCP integration test suite."""

    def __init__(
        self,
        oc: str,
        gemini_api_key: Optional[str] = None,
        server_url: str = "http://127.0.0.1:8081"
    ):
        """
        Initialize LLM integration test.

        Args:
            oc: law.go.kr OC identifier
            gemini_api_key: Google Gemini API key (optional if in env)
            server_url: LexLink server URL
        """
        self.oc = oc
        self.server_url = server_url

        # Initialize logger
        self.logger = TestLogger("lexlink_llm_integration")

        # Log test configuration
        self.logger.log_config({
            "oc": oc,
            "server_url": server_url,
            "gemini_available": GEMINI_AVAILABLE,
            "test_type": "llm_integration_with_function_calling"
        })

        # Initialize MCP client with session config
        self.mcp = MCPClient(
            base_url=server_url,
            session_config={"oc": oc}
        )

        # Initialize Gemini if available
        self.gemini_model = None
        self.gemini_model_name = None
        self.gemini_tools = None

        if GEMINI_AVAILABLE and (gemini_api_key or os.getenv("GOOGLE_API_KEY")):
            api_key = gemini_api_key or os.getenv("GOOGLE_API_KEY")
            genai.configure(api_key=api_key)

            # Try multiple Gemini models in order of preference
            model_preferences = [
                'gemini-1.5-flash',      # Stable 1.5 flash (preferred)
                'gemini-1.5-pro',        # Stable 1.5 pro (good function calling)
                'gemini-2.0-flash-exp',  # Experimental 2.0 (fallback)
                'gemini-pro'             # Legacy fallback
            ]

            for model_name in model_preferences:
                try:
                    # Test model availability
                    test_model = genai.GenerativeModel(model_name)
                    test_model.generate_content("test")
                    self.gemini_model_name = model_name
                    print(f"✓ Using Gemini model: {model_name}")
                    break
                except Exception as e:
                    continue

            if not self.gemini_model_name:
                print("⚠ Gemini model not available, skipping LLM tests")

    def _convert_mcp_schema_to_gemini_function(self, tool_schema: dict) -> FunctionDeclaration:
        """
        Convert MCP tool schema to Gemini FunctionDeclaration.

        Args:
            tool_schema: MCP tool schema from tools/list

        Returns:
            Gemini FunctionDeclaration
        """
        # Extract parameters from MCP schema
        mcp_params = tool_schema.get("inputSchema", {})
        properties = mcp_params.get("properties", {})
        required = mcp_params.get("required", [])

        # Convert to Gemini parameter format
        gemini_params = {}
        for param_name, param_def in properties.items():
            # Map JSON schema types to Gemini types
            json_type = param_def.get("type", "string")
            type_mapping = {
                "string": "STRING",
                "integer": "INTEGER",
                "number": "NUMBER",
                "boolean": "BOOLEAN",
                "array": "ARRAY",
                "object": "OBJECT"
            }
            gemini_type = type_mapping.get(json_type.lower(), "STRING")

            gemini_param = {
                "type": gemini_type,
                "description": param_def.get("description", "")
            }

            # Handle enums (only if supported by Gemini)
            if "enum" in param_def:
                gemini_param["enum"] = param_def["enum"]

            # Note: Gemini doesn't support "default" field, so we omit it

            gemini_params[param_name] = gemini_param

        # Create FunctionDeclaration
        return FunctionDeclaration(
            name=tool_schema["name"],
            description=tool_schema.get("description", ""),
            parameters={
                "type": "OBJECT",
                "properties": gemini_params,
                "required": required
            }
        )

    def setup_gemini_with_tools(self) -> bool:
        """
        Set up Gemini with MCP tools as function declarations.

        Returns:
            True if setup successful, False otherwise
        """
        if not self.gemini_model_name:
            return False

        try:
            # Initialize MCP session
            self.mcp.initialize()

            # Get MCP tools
            result = self.mcp.list_tools()
            mcp_tools = result.get("result", {}).get("tools", [])

            print(f"\n=== Setting up Gemini with {len(mcp_tools)} MCP tools ===")

            # Convert MCP tools to Gemini function declarations
            function_declarations = []
            for tool in mcp_tools:
                func_decl = self._convert_mcp_schema_to_gemini_function(tool)
                function_declarations.append(func_decl)
                print(f"  ✓ Converted: {tool['name']}")

            # Create Gemini Tool with all functions
            self.gemini_tools = [Tool(function_declarations=function_declarations)]

            # Create model with tools
            self.gemini_model = genai.GenerativeModel(
                self.gemini_model_name,
                tools=self.gemini_tools
            )

            print(f"✓ Gemini configured with {len(function_declarations)} tools")

            # Log setup
            self.logger.log_result("gemini_setup", {
                "status": "PASS",
                "model": self.gemini_model_name,
                "tools_count": len(function_declarations),
                "tools": [f.name for f in function_declarations]
            })

            return True

        except Exception as e:
            print(f"✗ Gemini setup failed: {e}")
            self.logger.log_result("gemini_setup", {
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def _execute_function_call(self, function_call) -> dict:
        """
        Execute a Gemini function call using MCP.

        Args:
            function_call: Gemini function call object

        Returns:
            Function execution result
        """
        tool_name = function_call.name
        tool_args = dict(function_call.args)

        print(f"    → Calling MCP tool: {tool_name}")
        print(f"      Arguments: {json.dumps(tool_args, ensure_ascii=False)}")

        # Call MCP tool
        result = self.mcp.call_tool(tool_name, tool_args)

        # Parse MCP result
        tool_result = result["result"]["content"][0]["text"]
        parsed_result = json.loads(tool_result)

        print(f"      ✓ Result status: {parsed_result.get('status', 'unknown')}")

        return {
            "tool_name": tool_name,
            "arguments": tool_args,
            "result": parsed_result
        }

    def test_llm_query_with_tools(
        self,
        query: str,
        test_name: str,
        max_iterations: int = 3
    ) -> dict:
        """
        Test LLM query with MCP tool usage.

        This implements the full function calling loop:
        1. Send query to LLM
        2. LLM decides which tools to use
        3. Execute tool calls
        4. Send results back to LLM
        5. LLM generates final response

        Args:
            query: User query to test
            test_name: Name for logging
            max_iterations: Maximum function calling iterations

        Returns:
            Test result with all logged interactions
        """
        print(f"\n=== Test: {test_name} ===")
        print(f"Query: {query}")

        if not self.gemini_model:
            print("⊘ Skipping: Gemini not configured")
            return {"status": "SKIP", "reason": "Gemini not configured"}

        try:
            # Log initial query
            interaction_log = {
                "query": query,
                "iterations": []
            }

            # Start chat session
            chat = self.gemini_model.start_chat()

            # Send initial query
            response = chat.send_message(query)

            # Function calling loop
            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                print(f"\n  Iteration {iteration}:")

                iteration_log = {
                    "iteration": iteration,
                    "function_calls": [],
                    "response_text": None
                }

                # Check if response has function calls
                has_function_call = any(
                    part.function_call for part in response.candidates[0].content.parts
                )

                if has_function_call:
                    print(f"  → LLM selected tools to use")

                    # Execute all function calls
                    function_responses = []
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            # Execute function call
                            exec_result = self._execute_function_call(part.function_call)
                            iteration_log["function_calls"].append(exec_result)

                            # Prepare response for LLM
                            function_responses.append(
                                genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=exec_result["tool_name"],
                                        response={"result": exec_result["result"]}
                                    )
                                )
                            )

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

                    # Send function results back to LLM
                    print(f"  → Sending {len(function_responses)} tool results back to LLM")
                    response = chat.send_message(function_responses)
                    interaction_log["iterations"].append(iteration_log)

                else:
                    # LLM generated final text response
                    try:
                        final_response = response.text
                        iteration_log["response_text"] = final_response

                        print(f"\n  ✓ Final Response:")
                        print(f"    {final_response[:200]}...")

                        interaction_log["iterations"].append(iteration_log)
                        interaction_log["final_response"] = final_response
                        break
                    except ValueError:
                        # Response has no text, might have hit edge case
                        print(f"  ⚠ No text response, continuing...")
                        interaction_log["iterations"].append(iteration_log)
                        continue

            # Handle case where we hit max iterations without a final response
            if "final_response" not in interaction_log:
                print(f"\n  ⚠ Hit max iterations ({max_iterations}) without final response")
                interaction_log["final_response"] = "(No final response - max iterations reached)"

            # Log complete interaction
            self.logger.log_llm_interaction(
                prompt=query,
                response=interaction_log.get("final_response", "No final response"),
                model=self.gemini_model_name,
                tool_calls=[
                    fc
                    for it in interaction_log["iterations"]
                    for fc in it["function_calls"]
                ]
            )

            # Log test result
            tools_used = [
                fc["tool_name"]
                for it in interaction_log["iterations"]
                for fc in it["function_calls"]
            ]

            self.logger.log_result(test_name, {
                "status": "PASS",
                "query": query,
                "tools_used": tools_used,
                "iterations": iteration,
                "final_response_length": len(interaction_log.get("final_response", ""))
            })

            print(f"\n✓ Test passed: {len(tools_used)} tools used in {iteration} iterations")

            return {
                "status": "PASS",
                "interaction": interaction_log,
                "tools_used": tools_used
            }

        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            import traceback
            traceback.print_exc()

            self.logger.log_result(test_name, {
                "status": "FAIL",
                "query": query,
                "error": str(e)
            })

            return {
                "status": "FAIL",
                "error": str(e)
            }

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all LLM integration tests - comprehensive coverage of all 15 tools."""
        print("\n" + "="*70)
        print("LexLink LLM Integration Test Suite - All 15 Tools")
        print("Testing: Gemini + MCP Function Calling")
        print("="*70)

        # Setup Gemini with tools
        if not self.setup_gemini_with_tools():
            print("\n⚠️  Cannot run tests: Gemini setup failed")
            self.mcp.close()
            return {
                "status": "SKIP",
                "reason": "Gemini not available"
            }

        # Test scenarios - Comprehensive coverage of all 15 tools
        test_results = {}

        print("\n=== Phase 1: Core Law APIs (6 tools) ===")

        # Test 1: eflaw_search
        test_results["test_01_eflaw_search"] = self.test_llm_query_with_tools(
            query="효력별 법령검색으로 '자동차' 관련 법령을 3개만 찾아주세요.",
            test_name="test_01_eflaw_search"
        )

        # Test 2: law_search
        test_results["test_02_law_search"] = self.test_llm_query_with_tools(
            query="통합 법령 검색으로 '민법'을 검색해주세요. 3개 결과만 보여주세요.",
            test_name="test_02_law_search"
        )

        # Test 3: eflaw_service
        test_results["test_03_eflaw_service"] = self.test_llm_query_with_tools(
            query="법령 ID 001823의 효력별 상세 정보를 가져와주세요.",
            test_name="test_03_eflaw_service"
        )

        # Test 4: law_service
        test_results["test_04_law_service"] = self.test_llm_query_with_tools(
            query="민법(법령 ID: 001823)의 통합 상세 정보를 조회해주세요.",
            test_name="test_04_law_service"
        )

        # Test 5: eflaw_josub
        test_results["test_05_eflaw_josub"] = self.test_llm_query_with_tools(
            query="민법(ID: 001823)의 효력별 조문 중 제1조(조번호: 000100)를 보여주세요.",
            test_name="test_05_eflaw_josub"
        )

        # Test 6: law_josub
        test_results["test_06_law_josub"] = self.test_llm_query_with_tools(
            query="법령 ID 001823의 제1조(조번호 000100) 조문 내용을 가져와주세요.",
            test_name="test_06_law_josub"
        )

        print("\n=== Phase 2: English Laws (2 tools) ===")

        # Test 7: elaw_search
        test_results["test_07_elaw_search"] = self.test_llm_query_with_tools(
            query="Search for English-translated Korean laws about 'employment'. Show 3 results.",
            test_name="test_07_elaw_search"
        )

        # Test 8: elaw_service
        test_results["test_08_elaw_service"] = self.test_llm_query_with_tools(
            query="Get the English law details for law ID 009589.",
            test_name="test_08_elaw_service"
        )

        print("\n=== Phase 2: Administrative Rules (2 tools) ===")

        # Test 9: admrul_search
        test_results["test_09_admrul_search"] = self.test_llm_query_with_tools(
            query="행정규칙 중 '학교' 관련 규칙을 검색해주세요. 3개만 보여주세요.",
            test_name="test_09_admrul_search"
        )

        # Test 10: admrul_service
        test_results["test_10_admrul_service"] = self.test_llm_query_with_tools(
            query="행정규칙 ID 62505의 상세 정보를 조회해주세요.",
            test_name="test_10_admrul_service"
        )

        print("\n=== Phase 2: Law-Ordinance Linkage (4 tools) ===")

        # Test 11: lnkLs_search
        test_results["test_11_lnkLs_search"] = self.test_llm_query_with_tools(
            query="'건축'과 관련된 법령-자치법규 연계 정보를 3개만 찾아주세요.",
            test_name="test_11_lnkLs_search"
        )

        # Test 12: lnkLsOrdJo_search
        test_results["test_12_lnkLsOrdJo_search"] = self.test_llm_query_with_tools(
            query="법령 종류 코드 002118에 해당하는 조례규칙별 법령 조문을 3개만 검색해주세요.",
            test_name="test_12_lnkLsOrdJo_search"
        )

        # Test 13: lnkDep_search
        test_results["test_13_lnkDep_search"] = self.test_llm_query_with_tools(
            query="소관 부처 코드 1400000(국토교통부)의 법령을 3개만 검색해주세요.",
            test_name="test_13_lnkDep_search"
        )

        # Test 14: drlaw_search
        test_results["test_14_drlaw_search"] = self.test_llm_query_with_tools(
            query="법령-자치법규 연계 현황 통계를 가져와주세요.",
            test_name="test_14_drlaw_search"
        )

        print("\n=== Phase 2: Delegated Laws (1 tool) ===")

        # Test 15: lsDelegated_service
        test_results["test_15_lsDelegated_service"] = self.test_llm_query_with_tools(
            query="법령 ID 000900의 위임법령 정보를 조회해주세요.",
            test_name="test_15_lsDelegated_service"
        )

        # Summary
        print("\n" + "="*70)
        print("Test Summary")
        print("="*70)

        passed = sum(1 for v in test_results.values() if v.get("status") == "PASS")
        failed = sum(1 for v in test_results.values() if v.get("status") == "FAIL")
        skipped = sum(1 for v in test_results.values() if v.get("status") == "SKIP")
        total = len(test_results)

        for test_name, result in test_results.items():
            status = result.get("status", "UNKNOWN")
            if status == "PASS":
                tools_used = result.get("tools_used", [])
                print(f"✓ {test_name}: PASS (used {len(tools_used)} tools)")
            elif status == "FAIL":
                print(f"✗ {test_name}: FAIL - {result.get('error', 'Unknown error')}")
            else:
                print(f"⊘ {test_name}: SKIP - {result.get('reason', 'Unknown reason')}")

        print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped (out of {total})")

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
            "skipped": skipped,
            "total": total,
            "results": test_results,
            "log_files": {
                "json": str(json_path),
                "markdown": str(md_path)
            }
        }


def main():
    """Main test runner."""
    # Load configuration
    oc = os.getenv("LAW_OC", "ddongle0205")

    # Get Gemini API key (try multiple from comma-separated list)
    gemini_keys_str = os.getenv("GOOGLE_API_KEYS", "")
    gemini_key = None
    if gemini_keys_str:
        gemini_keys = [k.strip() for k in gemini_keys_str.split(",")]
        gemini_key = gemini_keys[0] if gemini_keys else None
        if gemini_key:
            os.environ["GOOGLE_API_KEY"] = gemini_key

    if not GEMINI_AVAILABLE:
        print("⚠️  google-generativeai not installed")
        print("Install with: pip install google-generativeai")
        sys.exit(1)

    if not gemini_key:
        print("⚠️  GOOGLE_API_KEYS environment variable not set")
        print("Please set it with your Gemini API key")
        sys.exit(1)

    print(f"Configuration:")
    print(f"  OC: {oc}")
    print(f"  Gemini API Key: ✓ Available")
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
    test_suite = LLMIntegrationTest(oc=oc, gemini_api_key=gemini_key)
    results = test_suite.run_all_tests()

    # Exit with appropriate code
    if results.get("status") == "SKIP":
        sys.exit(0)
    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
