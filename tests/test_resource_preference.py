"""
Test: Do LLMs prefer MCP resources over search tools for law ID lookups?

Presents Gemini models with both resource-reading functions and search tools,
then sends Korean law queries to see which the model calls first.

Method 1: lexlink://laws/frequently-used (static list resource)
Method 2: lexlink://law/{name} (template resource)
Baseline: eflaw_search (tool call)

Usage:
    uv run python tests/test_resource_preference.py
"""

import json
import os
import time
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import dotenv
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_KEY = os.getenv("GOOGLE_API_KEYS", "").split(",")[0].strip()
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEYS not set in .env")

genai.configure(api_key=API_KEY)

MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview"]
RUNS_PER_MODEL = 50

# ---------------------------------------------------------------------------
# Function declarations (mimicking MCP capabilities advertised to LLM)
# ---------------------------------------------------------------------------

# Resource: static list
read_frequently_used_laws = FunctionDeclaration(
    name="read_frequently_used_laws",
    description=(
        "Read the lexlink://laws/frequently-used MCP resource. "
        "Returns a cached JSON list of ~20 frequently-used Korean law names "
        "mapped to their stable 법령ID codes. Use these IDs directly with "
        "eflaw_service, law_service, etc. to skip the search step. "
        "No parameters needed."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)

# Resource: template lookup
read_law_by_name = FunctionDeclaration(
    name="read_law_by_name",
    description=(
        "Read the lexlink://law/{name} MCP resource. "
        "Look up a specific Korean law's stable 법령ID by name (Korean). "
        "Returns the law's ID, full name, abbreviation, and type. "
        "If not found, use eflaw_search tool instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Korean law name (e.g. '민법', '형법', '자본시장법')",
            }
        },
        "required": ["name"],
    },
)

# Tool: eflaw_search (the traditional search approach)
eflaw_search = FunctionDeclaration(
    name="eflaw_search",
    description=(
        "Search current Korean laws by effective date (시행일 기준 현행법령 검색). "
        "Returns search results including 법령ID, 법령명한글, 법령일련번호 (MST). "
        "Use this when you need to find laws by keyword."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword (law name or content)",
            },
            "display": {
                "type": "integer",
                "description": "Number of results (default 20, max 100)",
            },
        },
        "required": ["query"],
    },
)

# Tool: eflaw_service (needs an ID — downstream consumer of resources)
eflaw_service = FunctionDeclaration(
    name="eflaw_service",
    description=(
        "Retrieve full law content by effective date. "
        "Requires either 'id' (법령ID) or 'mst' (법령일련번호). "
        "Use the jo parameter for specific articles."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Law ID (법령ID) — get this from resources or search",
            },
            "mst": {
                "type": "string",
                "description": "Law serial number (MST)",
            },
            "jo": {
                "type": "string",
                "description": "Article number in XXXXXX format (e.g. '000300' = 제3조)",
            },
        },
        "required": [],
    },
)

tools = Tool(function_declarations=[
    read_frequently_used_laws,
    read_law_by_name,
    eflaw_search,
    eflaw_service,
])

# ---------------------------------------------------------------------------
# System instruction (mirrors SERVER_INSTRUCTIONS)
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """You are using LexLink, a Korean legal information API.

## Resources
- Read `lexlink://laws/frequently-used` to get cached law name→법령ID mappings
- Use `lexlink://law/{name}` to look up a specific law's 법령ID by name
- Use the 법령ID directly with eflaw_service, law_service, etc. to skip the search step

## Available Tools
- eflaw_search: Search laws by keyword
- eflaw_service: Get full law text (requires 법령ID or MST)

## Quick Reference
- 법령ID: Stable law identifier usable with eflaw_service
- MST (법령일련번호): Version-specific identifier from search results
"""

# ---------------------------------------------------------------------------
# Test queries — mix of cached laws and uncached/vague queries
# ---------------------------------------------------------------------------
# Category A: Laws that ARE in the seed cache (should use resource)
CACHED_QUERIES = [
    "민법의 법령ID를 알려줘",
    "형법 본문을 조회하고 싶어",
    "상법의 ID가 뭐야?",
    "헌법 전문을 가져와",
    "근로기준법의 법령ID를 찾아줘",
    "건축법 내용을 확인하고 싶어",
    "자본시장법 법령ID 알려줘",
    "민사소송법의 ID를 조회해줘",
    "형사소송법 본문 가져와",
    "도로교통법 법령ID 찾아줘",
    "개인정보보호법 ID가 뭐야?",
    "소득세법의 법령ID를 알려줘",
    "법인세법 본문 조회해줘",
    "행정소송법의 ID를 찾아줘",
    "민사집행법 법령ID 알려줘",
]

# Category B: Laws NOT in seed cache (should use eflaw_search)
UNCACHED_QUERIES = [
    "주택임대차보호법의 법령ID를 알려줘",
    "식품위생법 본문을 조회하고 싶어",
    "저작권법 ID를 찾아줘",
    "의료법의 법령ID가 뭐야?",
    "환경영향평가법 내용을 확인해줘",
]


def build_query_pool(n: int) -> list[dict]:
    """Build a pool of n queries with expected outcomes."""
    pool = []
    # 70% cached, 30% uncached — weighted toward cached to measure resource usage
    n_cached = int(n * 0.7)
    n_uncached = n - n_cached

    for _ in range(n_cached):
        q = random.choice(CACHED_QUERIES)
        pool.append({"query": q, "category": "cached"})
    for _ in range(n_uncached):
        q = random.choice(UNCACHED_QUERIES)
        pool.append({"query": q, "category": "uncached"})

    random.shuffle(pool)
    return pool


# ---------------------------------------------------------------------------
# Run test
# ---------------------------------------------------------------------------
def run_single_test(model_name: str, query: str) -> dict:
    """Send one query and record which function the model calls first."""
    model = genai.GenerativeModel(
        model_name=model_name,
        tools=[tools],
        system_instruction=SYSTEM_INSTRUCTION,
    )

    try:
        response = model.generate_content(query)

        # Extract first function call
        first_call = None
        call_args = {}
        all_calls = []

        for candidate in response.candidates:
            for part in candidate.content.parts:
                if fn := part.function_call:
                    call_name = fn.name
                    call_arg = dict(fn.args) if fn.args else {}
                    all_calls.append({"name": call_name, "args": call_arg})
                    if first_call is None:
                        first_call = call_name
                        call_args = call_arg

        # Classify the first call
        if first_call == "read_frequently_used_laws":
            method = "static_resource"
        elif first_call == "read_law_by_name":
            method = "template_resource"
        elif first_call == "eflaw_search":
            method = "search_tool"
        elif first_call == "eflaw_service":
            method = "direct_service"
        elif first_call is None:
            method = "no_function_call"
        else:
            method = f"unknown:{first_call}"

        return {
            "method": method,
            "first_call": first_call,
            "first_call_args": call_args,
            "all_calls": all_calls,
            "error": None,
        }

    except Exception as e:
        return {
            "method": "error",
            "first_call": None,
            "first_call_args": {},
            "all_calls": [],
            "error": str(e),
        }


def run_model_tests(model_name: str, n: int) -> list[dict]:
    """Run n tests for a single model."""
    queries = build_query_pool(n)
    results = []

    for i, q in enumerate(queries):
        print(f"  [{i+1}/{n}] {model_name} | {q['category']:>8} | {q['query'][:30]}...", end="", flush=True)

        result = run_single_test(model_name, q["query"])
        result["query"] = q["query"]
        result["category"] = q["category"]
        result["model"] = model_name
        result["run_index"] = i + 1
        results.append(result)

        print(f" → {result['method']}")

        # Rate limit: ~15 RPM for free tier, generous for paid
        time.sleep(1.0)

    return results


def generate_report(all_results: dict[str, list[dict]]) -> str:
    """Generate a markdown report from test results."""
    lines = []
    lines.append("# MCP Resource Preference Test Report")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Runs per model:** {RUNS_PER_MODEL}")
    lines.append(f"**Query mix:** 70% cached laws / 30% uncached laws")
    lines.append("")

    for model_name, results in all_results.items():
        lines.append(f"## {model_name}")
        lines.append("")

        # Overall counts
        method_counts = defaultdict(int)
        for r in results:
            method_counts[r["method"]] += 1

        total = len(results)
        lines.append("### Overall First-Call Distribution")
        lines.append("")
        lines.append("| Method | Count | Percentage |")
        lines.append("|--------|------:|----------:|")
        for method in ["static_resource", "template_resource", "search_tool", "direct_service", "no_function_call", "error"]:
            count = method_counts.get(method, 0)
            pct = (count / total * 100) if total else 0
            if count > 0:
                lines.append(f"| {method} | {count} | {pct:.1f}% |")
        # Any unknown methods
        for method, count in method_counts.items():
            if method not in ["static_resource", "template_resource", "search_tool", "direct_service", "no_function_call", "error"]:
                pct = (count / total * 100) if total else 0
                lines.append(f"| {method} | {count} | {pct:.1f}% |")
        lines.append("")

        # Breakdown by category
        for category in ["cached", "uncached"]:
            cat_results = [r for r in results if r["category"] == category]
            if not cat_results:
                continue
            cat_total = len(cat_results)
            cat_counts = defaultdict(int)
            for r in cat_results:
                cat_counts[r["method"]] += 1

            lines.append(f"### {category.title()} Laws (n={cat_total})")
            lines.append("")
            lines.append("| Method | Count | Percentage |")
            lines.append("|--------|------:|----------:|")
            for method in ["static_resource", "template_resource", "search_tool", "direct_service", "no_function_call", "error"]:
                count = cat_counts.get(method, 0)
                pct = (count / cat_total * 100) if cat_total else 0
                if count > 0:
                    lines.append(f"| {method} | {count} | {pct:.1f}% |")
            for method, count in cat_counts.items():
                if method not in ["static_resource", "template_resource", "search_tool", "direct_service", "no_function_call", "error"]:
                    pct = (count / cat_total * 100) if cat_total else 0
                    lines.append(f"| {method} | {count} | {pct:.1f}% |")
            lines.append("")

        # Resource usage rate (combined static + template)
        resource_calls = method_counts.get("static_resource", 0) + method_counts.get("template_resource", 0)
        search_calls = method_counts.get("search_tool", 0)
        lines.append(f"### Summary")
        lines.append(f"- **Resource usage rate:** {resource_calls}/{total} ({resource_calls/total*100:.1f}%)")
        lines.append(f"- **Search fallback rate:** {search_calls}/{total} ({search_calls/total*100:.1f}%)")
        lines.append(f"- **Static vs Template preference:** {method_counts.get('static_resource', 0)} static / {method_counts.get('template_resource', 0)} template")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Cross-model comparison
    lines.append("## Cross-Model Comparison")
    lines.append("")
    lines.append("| Metric | " + " | ".join(all_results.keys()) + " |")
    lines.append("|--------" + "|--------" * len(all_results) + "|")

    for metric_name, metric_fn in [
        ("Resource usage (all)", lambda rs: sum(1 for r in rs if r["method"] in ("static_resource", "template_resource"))),
        ("Resource usage (cached)", lambda rs: sum(1 for r in rs if r["method"] in ("static_resource", "template_resource") and r["category"] == "cached")),
        ("Search fallback (all)", lambda rs: sum(1 for r in rs if r["method"] == "search_tool")),
        ("Static resource calls", lambda rs: sum(1 for r in rs if r["method"] == "static_resource")),
        ("Template resource calls", lambda rs: sum(1 for r in rs if r["method"] == "template_resource")),
        ("Errors", lambda rs: sum(1 for r in rs if r["method"] == "error")),
    ]:
        vals = []
        for model_name, results in all_results.items():
            count = metric_fn(results)
            total = len(results)
            vals.append(f"{count}/{total} ({count/total*100:.0f}%)")
        lines.append(f"| {metric_name} | " + " | ".join(vals) + " |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("MCP Resource Preference Test")
    print(f"Models: {', '.join(MODELS)}")
    print(f"Runs per model: {RUNS_PER_MODEL}")
    print("=" * 60)

    all_results: dict[str, list[dict]] = {}

    for model_name in MODELS:
        print(f"\n{'─' * 60}")
        print(f"Testing {model_name} ({RUNS_PER_MODEL} runs)")
        print(f"{'─' * 60}")

        results = run_model_tests(model_name, RUNS_PER_MODEL)
        all_results[model_name] = results

        # Quick summary
        methods = defaultdict(int)
        for r in results:
            methods[r["method"]] += 1
        print(f"\n  Quick summary for {model_name}:")
        for m, c in sorted(methods.items(), key=lambda x: -x[1]):
            print(f"    {m}: {c}/{RUNS_PER_MODEL} ({c/RUNS_PER_MODEL*100:.0f}%)")

    # Generate report
    report = generate_report(all_results)
    report_path = Path(__file__).parent / "resource_preference_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: {report_path}")

    # Also save raw data
    raw_path = Path(__file__).parent / "resource_preference_raw.json"
    raw_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw data saved to: {raw_path}")

    # Print report
    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
