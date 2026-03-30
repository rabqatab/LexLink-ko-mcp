# PoC: Response Format Comparison — XML vs JSON vs TOON

**Date:** 2026-03-30
**Author:** minhan.nick.cho
**Status:** Complete
**Context:** LexLink v2.0.0 (44 tools), law.go.kr now supports JSON

---

## 1. Objective

Evaluate switching LexLink's default response format from XML to JSON or TOON (Token-Oriented Object Notation) by measuring:
- **Token count** (cost to LLM consumers)
- **Byte size** (PlayMCP 24KB limit, network bandwidth)
- **API latency** (response time from law.go.kr)
- **LLM parseability** (can models extract structured data correctly?)
- **PlayMCP fit rate** (what percentage of responses fit under 24KB?)

## 2. Methodology

### Test Scenarios
8 representative tool calls covering search (various sizes) and service (full text):

| # | Scenario | Type | Description |
|---|----------|------|-------------|
| 1 | `eflaw_search(민법, 5)` | Search | Law search, 5 results |
| 2 | `eflaw_search(민법, 20)` | Search | Law search, 20 results |
| 3 | `prec_search(담보권, 10)` | Search | Precedent search, 10 results |
| 4 | `trty_search(무역, 10)` | Search | Treaty search, 10 results |
| 5 | `admrul_search(학교, 10)` | Search | Admin rule search, 10 results |
| 6 | `eflaw_service(민법 제3조)` | Service | Single law article |
| 7 | `prec_service(228541)` | Service | Full precedent text |
| 8 | `aiSearch(음주운전, 5)` | AI Search | Semantic search, 5 results |

### Measurement Setup
- **Token counting:** tiktoken `o200k_base` encoding (GPT-4o / Claude compatible)
- **Latency:** Median of 3 runs per format per scenario
- **TOON conversion:** JSON → TOON via custom Python converter (no stable SDK available)
- **LLM parseability:** gemini-2.0-flash extracting 3 fields from 5 law results
- **API endpoint:** `http://www.law.go.kr/DRF/` with `type=XML` or `type=JSON`
- **TOON latency:** Not measured (converted client-side from JSON, adds ~1ms)

## 3. Results

### 3.1 Token Count Comparison

| Scenario | XML tokens | JSON tokens | TOON tokens | JSON savings | TOON savings |
|----------|-----------|------------|------------|-------------|-------------|
| eflaw_search(민법, 5) | 1,485 | 1,202 | 575 | **-19.1%** | **-61.3%** |
| eflaw_search(민법, 20) | 5,710 | 4,602 | 1,860 | **-19.4%** | **-67.4%** |
| prec_search(담보권, 10) | 2,800 | 2,471 | 1,462 | **-11.8%** | **-47.8%** |
| trty_search(무역, 10) | 2,114 | 1,797 | 919 | **-15.0%** | **-56.5%** |
| admrul_search(학교, 10) | 2,906 | 2,378 | 1,149 | **-18.2%** | **-60.5%** |
| eflaw_service(민법 제3조) | 901 | 715 | 662 | **-20.6%** | **-26.5%** |
| prec_service(228541) | 7,653 | 7,743 | 7,581 | +1.2% | **-0.9%** |
| aiSearch(음주운전, 5) | 5,590 | 5,198 | 4,571 | **-7.0%** | **-18.2%** |

**Key observations:**
- **Search tools (tabular data):** TOON dominates — 47-67% fewer tokens than XML, because tabular format (header + rows) eliminates repeated keys per row.
- **Service tools (prose text):** Minimal difference across all formats — the bulk is Korean legal text, not structural markup.
- **JSON vs XML for search:** Consistent 11-20% savings from removing closing tags.
- **JSON vs XML for service:** ~20% savings for structured content, but precedent full text (mostly prose) shows no improvement.

### 3.2 Byte Size Comparison

| Scenario | XML bytes | JSON bytes | TOON bytes | JSON savings | TOON savings |
|----------|----------|-----------|-----------|-------------|-------------|
| eflaw_search(민법, 5) | 4,159 | 4,005 | 1,462 | -3.7% | **-64.8%** |
| eflaw_search(민법, 20) | 16,033 | 15,519 | 4,697 | -3.2% | **-70.7%** |
| prec_search(담보권, 10) | 8,527 | 8,600 | 4,467 | +0.9% | **-47.6%** |
| trty_search(무역, 10) | 6,011 | 5,990 | 2,397 | -0.3% | **-60.1%** |
| admrul_search(학교, 10) | 8,090 | 7,766 | 2,973 | -4.0% | **-63.3%** |
| eflaw_service(민법 제3조) | 2,455 | 2,397 | 2,109 | -2.4% | **-14.1%** |
| prec_service(228541) | 30,155 | 30,106 | 29,882 | -0.2% | **-0.9%** |
| aiSearch(음주운전, 5) | 18,773 | 18,445 | 15,837 | -1.7% | **-15.6%** |

**Key observations:**
- **JSON byte savings are minimal** (0-4%) — Korean UTF-8 text is the dominant size factor, not structural syntax.
- **TOON byte savings are massive for search** (47-71%) — tabular format eliminates key repetition per row.
- **For PlayMCP 24KB limit:** Only `prec_service` exceeds 24KB in all formats. TOON doesn't help with prose-heavy responses.

### 3.3 API Latency (law.go.kr response time)

| Scenario | XML (ms) | JSON (ms) | Difference |
|----------|---------|----------|------------|
| eflaw_search(민법, 5) | 180 | 205 | JSON +14% |
| eflaw_search(민법, 20) | 187 | 225 | JSON +20% |
| prec_search(담보권, 10) | 195 | 443 | JSON +127% |
| trty_search(무역, 10) | 198 | 217 | JSON +10% |
| admrul_search(학교, 10) | 193 | 198 | JSON +3% |
| eflaw_service(민법 제3조) | 597 | 639 | JSON +7% |
| prec_service(228541) | 213 | 223 | JSON +5% |
| aiSearch(음주운전, 5) | 571 | 463 | JSON -19% |

**Key observations:**
- **XML is generally faster** — law.go.kr's native format is XML; JSON requires server-side conversion.
- **prec_search JSON is notably slow** (+127%) — likely due to server-side XML→JSON conversion overhead for complex precedent data.
- **aiSearch is faster in JSON** — possibly different backend handling.
- **TOON adds negligible latency** (client-side JSON→TOON conversion is ~1ms).

### 3.4 PlayMCP 24KB Fit Rate

| Scenario | XML | JSON | TOON |
|----------|-----|------|------|
| eflaw_search(민법, 5) | ✓ | ✓ | ✓ |
| eflaw_search(민법, 20) | ✓ | ✓ | ✓ |
| prec_search(담보권, 10) | ✓ | ✓ | ✓ |
| trty_search(무역, 10) | ✓ | ✓ | ✓ |
| admrul_search(학교, 10) | ✓ | ✓ | ✓ |
| eflaw_service(민법 제3조) | ✓ | ✓ | ✓ |
| prec_service(228541) | **✗** | **✗** | **✗** |
| aiSearch(음주운전, 5) | ✓ | ✓ | ✓ |

All three formats have the same fit/fail pattern. The 24KB limit is only hit by full-text precedent service calls, where the content is predominantly Korean legal prose that cannot be compressed by format changes.

### 3.5 LLM Parseability

**Test:** Extract 3 fields (법령명한글, 법령ID, 공포일자) from 5 law search results using gemini-2.0-flash.

| Format | Accuracy | Notes |
|--------|----------|-------|
| XML | **5/5 (100%)** | Parsed all fields correctly |
| JSON | **5/5 (100%)** | Parsed all fields correctly |
| TOON | **5/5 (100%)** | Parsed all fields correctly |

All three formats were parsed perfectly by gemini-2.0-flash. However, this was a simple extraction task. TOON's tabular format (CSV-like rows) is unfamiliar to LLMs trained primarily on JSON/XML, which may cause issues with:
- Complex nested structures
- Ambiguous delimiter handling (commas in values)
- Edge cases in quoting rules

## 4. TOON Sample Output

### eflaw_search (5 results) — Tabular format

```
LawSearch:
  law[5]{"현행연혁코드","법령일련번호","자법타법여부","법령상세링크","법령명한글",
         "법령구분명","소관부처명","공포번호","제개정구분명","소관부처코드",id,
         "법령ID","공동부령정보","시행일자","공포일자","법령약칭명"}:
    현행,188376,,/DRF/lawService.do?OC=...&MST=188376&type=HTML,난민법,법률,법무부,...
    연혁,152004,,/DRF/lawService.do?OC=...&MST=152004&type=HTML,난민법,법률,법무부,...
    ...
```

The tabular header declares column names once, then each row is just comma-separated values — this is where the 60%+ token savings come from.

## 5. Analysis

### Token savings by use case

| Use Case | JSON vs XML | TOON vs XML | Winner |
|----------|------------|------------|--------|
| Search results (list data) | -11 to -19% | **-48 to -67%** | TOON |
| Single article (structured) | -21% | -27% | TOON (marginal) |
| Full text (prose) | +1% | -1% | Draw |
| AI search (mixed) | -7% | -18% | TOON |

### Trade-off matrix

| Factor | XML | JSON | TOON |
|--------|-----|------|------|
| Token efficiency (search) | Baseline | -15% avg | **-57% avg** |
| Token efficiency (prose) | Baseline | ~0% | ~0% |
| Byte size (search) | Baseline | -2% avg | **-61% avg** |
| API latency | **Fastest** | +10-20% slower | +10-20% slower (JSON + ~1ms) |
| LLM parseability | Proven | Proven | Unknown at scale |
| PlayMCP fit rate | Same | Same | Same |
| SDK maturity | N/A | stdlib | **In development** |
| law.go.kr native | **Yes** | Converted server-side | Converted client-side |
| Ecosystem support | Universal | Universal | **Niche (new spec, v3.0 draft)** |

## 6. Recommendations

### Option A: Switch to JSON (Conservative)
- **Benefit:** 15% avg token savings on search, proven LLM compatibility, zero new dependencies
- **Cost:** 10-20% higher API latency, requires updating `type` default and XML parsing pipeline
- **Risk:** Low

### Option B: Switch to JSON + TOON conversion (Aggressive)
- **Benefit:** 57% avg token savings on search, massive PlayMCP headroom
- **Cost:** Must maintain custom TOON converter until Python SDK stabilizes, LLM parseability unproven at scale, double conversion (XML→JSON on server, JSON→TOON on client)
- **Risk:** Medium-high (LLM parsing failures, TOON spec changes)

### Option C: Stay on XML (Status quo)
- **Benefit:** Zero risk, fastest API latency, proven pipeline
- **Cost:** Most tokens per response
- **Risk:** None

### Author's recommendation
**Option A (JSON)** as the default, with TOON as an opt-in experimental feature (`RESPONSE_FORMAT=toon` env var). JSON gives reliable savings with zero risk. TOON can be evaluated more thoroughly as the Python SDK matures and LLM training data catches up.

## 7. Appendix: TOON Format Overview

TOON (Token-Oriented Object Notation) is a line-based, indentation-driven serialization format designed to minimize tokens for LLM consumption.

**Key features:**
- No quotes on alphanumeric keys
- Tabular arrays: header declares column names once, rows are CSV-like
- ~35-60% fewer tokens than JSON for tabular data
- Spec: v3.0 working draft ([github.com/toon-format/spec](https://github.com/toon-format/spec))
- Python SDK: in development ([github.com/toon-format/toon](https://github.com/toon-format/toon))

**Example:**
```
# JSON (78 tokens)
{"hikes": [{"id": 1, "name": "Blue Lake", "km": 7.5}, {"id": 2, "name": "Ridge", "km": 12}]}

# TOON (31 tokens)
hikes[2]{id,name,km}:
  1,Blue Lake,7.5
  2,Ridge,12
```
