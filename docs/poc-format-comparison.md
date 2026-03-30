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

### Scale
- **102 API calls** across **16 tool categories**
- **6 distinct query sets** (law, English, case law, admin, ordinance, treaty, knowledge base, committee, tribunal, AI search)
- Each query tested in **XML and JSON** formats; JSON converted client-side to TOON
- **Token counting:** tiktoken `o200k_base` encoding (GPT-4o / Claude compatible)
- **LLM parseability:** gemini-2.0-flash field extraction test (3 formats × 5 results)

### Tool Coverage (all 44 tools represented by category)

| Category | Tools Covered | Queries |
|----------|--------------|---------|
| law_search | eflaw_search, law_search | 12 |
| elaw_search | elaw_search | 5 |
| admrul_search | admrul_search | 5 |
| prec_search | prec_search | 5 |
| detc_search | detc_search | 5 |
| expc_search | expc_search | 5 |
| decc_search | decc_search | 5 |
| aiSearch | aiSearch | 5 |
| aiRltLs | aiRltLs_search | 5 |
| ordin_search | ordin_search | 5 |
| trty_search | trty_search | 5 |
| kb_search | dlytrm_search, ls_rlt_search | 10 |
| committee_search | committee_search (ftc, nhrck) | 10 |
| special_decc | special_decc_search (tt) | 5 |
| service | eflaw_service, law_service, eflaw_josub, prec_service, detc_service, expc_service, decc_service | 10 |
| linkage | lnkLs_search | 5 |
| **Total** | | **102** |

---

## 3. Results

### 3.1 Aggregate by Category

| Category | N | XML tokens (avg) | JSON tokens (avg) | TOON tokens (avg) | JSON savings | TOON savings | XML latency | JSON latency |
|----------|---|-----------------|-------------------|-------------------|-------------|-------------|-------------|-------------|
| law_search | 12 | 2,427 | 1,972 | 897 | **-18.8%** | **-63.0%** | 198ms | 240ms |
| elaw_search | 5 | 2,791 | 2,333 | 1,180 | **-16.4%** | **-57.7%** | 180ms | 219ms |
| admrul_search | 5 | 2,954 | 2,426 | 1,196 | **-17.9%** | **-59.5%** | 185ms | 216ms |
| prec_search | 5 | 2,680 | 2,355 | 1,342 | **-12.1%** | **-49.9%** | 199ms | 285ms |
| detc_search | 5 | 476 | 402 | 270 | **-15.6%** | **-43.3%** | 194ms | 206ms |
| expc_search | 5 | 794 | 690 | 468 | **-13.1%** | **-41.1%** | 189ms | 220ms |
| decc_search | 5 | 153 | 126 | 89 | **-17.5%** | **-42.0%** | 187ms | 217ms |
| aiSearch | 5 | 3,858 | 3,488 | 2,860 | **-9.6%** | **-25.9%** | 540ms | 583ms |
| aiRltLs | 5 | 1,285 | 1,074 | 436 | **-16.4%** | **-66.0%** | 280ms | 297ms |
| ordin_search | 5 | 2,736 | 2,226 | 1,082 | **-18.6%** | **-60.4%** | 214ms | 226ms |
| trty_search | 5 | 1,951 | 1,676 | 928 | **-14.1%** | **-52.4%** | 178ms | 229ms |
| kb_search | 10 | 530 | 419 | 258 | **-20.9%** | **-51.4%** | 202ms | 218ms |
| committee_search | 10 | 1,422 | 1,208 | 744 | **-15.1%** | **-47.6%** | 193ms | 216ms |
| special_decc | 5 | 2,867 | 2,388 | 1,339 | **-16.7%** | **-53.3%** | 204ms | 295ms |
| service | 10 | 1,729 | 1,590 | 1,477 | **-8.0%** | **-14.5%** | 369ms | 418ms |
| linkage | 5 | 217 | 185 | 115 | **-14.9%** | **-46.8%** | 188ms | 215ms |

### 3.2 Overall Totals (102 queries)

| Metric | XML | JSON | TOON |
|--------|-----|------|------|
| **Total tokens** | 179,736 | 152,675 | 92,089 |
| **Token savings vs XML** | — | **-15.1%** | **-48.8%** |

### 3.3 Token Savings Distribution

**Search tools (tabular data) — 92 queries:**

| Savings range | JSON | TOON |
|--------------|------|------|
| 0-10% | 5 queries (aiSearch) | 0 queries |
| 10-20% | 82 queries | 3 queries |
| 20-30% | 5 queries (kb, small) | 12 queries (aiSearch, service) |
| 30-50% | 0 | 28 queries |
| 50-70% | 0 | **49 queries** |

**Service tools (prose-heavy) — 10 queries:**

| Savings range | JSON | TOON |
|--------------|------|------|
| -5 to +5% | 3 queries (full-text prose) | 5 queries |
| 5-20% | 5 queries | 3 queries |
| 20-40% | 2 queries (structured articles) | 2 queries |

### 3.4 API Latency

| | XML avg | JSON avg | Difference |
|---|---------|---------|-----------|
| Search tools | 205ms | 239ms | **JSON +17% slower** |
| Service tools | 369ms | 418ms | **JSON +13% slower** |
| AI search tools | 410ms | 440ms | **JSON +7% slower** |

XML is consistently faster — law.go.kr natively serves XML and converts to JSON server-side.

### 3.5 PlayMCP 24KB Fit Rate

Of 102 queries, only **1 query** (`prec_service(228541)` — full precedent text, 30KB) exceeds 24KB. This is true in all 3 formats. Format choice does not affect fit rate for the tested scenarios.

### 3.6 LLM Parseability (10 models × 3 formats × 5 queries = 150 calls per model)

**Task:** Extract 3 fields from 5 search results across 5 different query types (law, precedent, treaty, admin rule, ordinance). Each model tested on all 3 formats.

**Models tested (10):**
- **Google:** gemini-2.0-flash, gemini-2.5-flash, gemini-2.5-pro, gemini-3-flash-preview, gemini-3.1-pro-preview
- **OpenAI:** gpt-4.1-mini, gpt-4.1, o4-mini
- **Anthropic:** claude-haiku-4-5, claude-sonnet-4-6

#### Accuracy by Model × Format

| Model | Provider | XML | JSON | TOON | XML avg ms | JSON avg ms | TOON avg ms |
|-------|----------|-----|------|------|-----------|------------|------------|
| gemini-2.0-flash | Google | 25/25 (100%) | 25/25 (100%) | 21/25 **(84%)** | 2,305 | 2,255 | 2,363 |
| gemini-2.5-flash | Google | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 2,567 | 2,734 | 5,232 |
| gemini-2.5-pro | Google | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 9,927 | 9,578 | 11,377 |
| gemini-3-flash-preview | Google | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 6,731 | 5,651 | 7,990 |
| gemini-3.1-pro-preview | Google | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 12,522 | 11,942 | 13,983 |
| gpt-4.1-mini | OpenAI | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 3,960 | 4,042 | 3,817 |
| gpt-4.1 | OpenAI | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 4,020 | 3,025 | 3,164 |
| o4-mini | OpenAI | 25/25 (100%) | 25/25 (100%) | 20/25 **(80%)** | 7,651 | 5,423 | 11,392 |
| claude-haiku-4-5 | Anthropic | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 2,153 | 2,414 | 1,734 |
| claude-sonnet-4-6 | Anthropic | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 4,187 | 3,882 | 3,991 |

#### Format-Level Totals (across all models)

| Format | Total Correct | Accuracy |
|--------|--------------|----------|
| XML | 250/250 | **100.0%** |
| JSON | 250/250 | **100.0%** |
| TOON | 241/250 | **96.4%** |

#### Key Findings

1. **XML and JSON: 100% accuracy across all 10 models.** No model failed to parse either format.

2. **TOON: 96.4% accuracy.** Two models had issues:
   - **gemini-2.0-flash** missed 4/25 on TOON (84%) — the oldest/fastest Gemini model struggled with the tabular CSV-like format
   - **o4-mini** missed 5/25 on TOON (80%) — the reasoning model misinterpreted some TOON rows on one query type (ordinance data)

3. **TOON is slower for reasoning models.** o4-mini took 11.4s avg on TOON vs 5.4s on JSON — the model spent more reasoning tokens parsing the unfamiliar format. gemini-2.5-flash also doubled its TOON latency (5.2s vs 2.7s for JSON).

4. **Claude models handled TOON perfectly.** Both haiku-4-5 and sonnet-4-6 scored 100% on all 3 formats, and haiku was actually fastest on TOON (1.7s avg).

5. **GPT-4.1 family handled TOON perfectly.** Both gpt-4.1-mini and gpt-4.1 scored 100% with no latency penalty.

---

## 4. Full Query Detail (102 queries)

### Law Search (eflaw_search + law_search) — 12 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| eflaw_search(민법) | 2,900 | 2,342 | 1,010 | -19.2% | **-65.2%** |
| eflaw_search(형법) | 2,973 | 2,423 | 1,091 | -18.5% | **-63.3%** |
| eflaw_search(건축법) | 2,888 | 2,330 | 998 | -19.3% | **-65.4%** |
| eflaw_search(근로기준법) | 2,914 | 2,356 | 1,022 | -19.1% | **-64.9%** |
| eflaw_search(도로교통법) | 2,885 | 2,327 | 993 | -19.3% | **-65.6%** |
| eflaw_search(개인정보) | 3,054 | 2,496 | 1,162 | -18.3% | **-62.0%** |
| law_search(민법) | 2,685 | 2,185 | 993 | -18.6% | **-63.0%** |
| law_search(형법) | 2,132 | 1,744 | 834 | -18.2% | **-60.9%** |
| law_search(건축법) | 1,825 | 1,490 | 721 | -18.4% | **-60.5%** |
| law_search(근로기준법) | 942 | 769 | 423 | -18.4% | **-55.1%** |
| law_search(도로교통법) | 932 | 759 | 414 | -18.6% | **-55.6%** |
| law_search(개인정보) | 2,996 | 2,439 | 1,104 | -18.6% | **-63.2%** |

### English Law Search — 5 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| elaw_search(civil) | 2,785 | 2,329 | 1,175 | -16.4% | **-57.8%** |
| elaw_search(criminal) | 2,836 | 2,379 | 1,226 | -16.1% | **-56.8%** |
| elaw_search(labor) | 2,915 | 2,455 | 1,303 | -15.8% | **-55.3%** |
| elaw_search(trade) | 2,781 | 2,325 | 1,171 | -16.4% | **-57.9%** |
| elaw_search(tax) | 2,636 | 2,179 | 1,026 | -17.3% | **-61.1%** |

### Admin Rule Search — 5 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| admrul_search(학교) | 2,906 | 2,378 | 1,149 | -18.2% | **-60.5%** |
| admrul_search(환경) | 2,972 | 2,444 | 1,215 | -17.8% | **-59.1%** |
| admrul_search(의료) | 2,966 | 2,438 | 1,208 | -17.8% | **-59.3%** |
| admrul_search(건설) | 2,980 | 2,456 | 1,223 | -17.6% | **-59.0%** |
| admrul_search(금융) | 2,945 | 2,416 | 1,186 | -18.0% | **-59.7%** |

### Case Law Search (prec/detc/expc/decc) — 20 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| prec_search(담보권) | 2,800 | 2,471 | 1,462 | -11.8% | **-47.8%** |
| prec_search(횡령) | 2,876 | 2,549 | 1,536 | -11.4% | **-46.6%** |
| prec_search(명예훼손) | 2,606 | 2,279 | 1,265 | -12.5% | **-51.5%** |
| prec_search(이혼) | 2,542 | 2,220 | 1,203 | -12.7% | **-52.7%** |
| prec_search(상속) | 2,578 | 2,256 | 1,243 | -12.5% | **-51.8%** |
| detc_search(담보권) | 90 | 74 | 60 | -17.8% | **-33.3%** |
| detc_search(횡령) | 90 | 74 | 60 | -17.8% | **-33.3%** |
| detc_search(명예훼손) | 385 | 329 | 240 | -14.5% | **-37.7%** |
| detc_search(이혼) | 253 | 217 | 197 | -14.2% | -22.1% |
| detc_search(상속) | 1,563 | 1,315 | 794 | -15.9% | **-49.2%** |
| expc_search(담보권) | 88 | 73 | 59 | -17.0% | **-33.0%** |
| expc_search(횡령) | 895 | 791 | 566 | -11.6% | **-36.8%** |
| expc_search(명예훼손) | 91 | 76 | 62 | -16.5% | -31.9% |
| expc_search(이혼) | 339 | 294 | 271 | -13.3% | -20.1% |
| expc_search(상속) | 2,556 | 2,215 | 1,380 | -13.3% | **-46.0%** |
| decc_search(담보권) | 62 | 48 | 37 | -22.6% | **-40.3%** |
| decc_search(횡령) | 62 | 48 | 37 | -22.6% | **-40.3%** |
| decc_search(명예훼손) | 65 | 51 | 40 | -21.5% | **-38.5%** |
| decc_search(이혼) | 61 | 47 | 36 | -23.0% | **-41.0%** |
| decc_search(상속) | 516 | 438 | 294 | -15.1% | **-43.0%** |

### AI Search — 10 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| aiSearch(음주운전 처벌) | 5,590 | 5,198 | 4,571 | -7.0% | -18.2% |
| aiSearch(뺑소니) | 4,506 | 4,148 | 3,521 | -7.9% | -21.9% |
| aiSearch(사기죄 양형) | 1,853 | 1,583 | 956 | -14.6% | **-48.4%** |
| aiSearch(부당해고 구제) | 2,203 | 1,920 | 1,293 | -12.8% | **-41.3%** |
| aiSearch(개인정보 유출) | 5,136 | 4,590 | 3,961 | -10.6% | -22.9% |
| aiRltLs(민법) | 1,254 | 1,043 | 405 | -16.8% | **-67.7%** |
| aiRltLs(형법) | 1,314 | 1,103 | 465 | -16.1% | **-64.6%** |
| aiRltLs(건축법) | 1,286 | 1,075 | 437 | -16.4% | **-66.0%** |
| aiRltLs(근로기준법) | 1,282 | 1,071 | 433 | -16.5% | **-66.2%** |
| aiRltLs(도로교통법) | 1,290 | 1,079 | 442 | -16.4% | **-65.7%** |

### Phase 7: New Tools — 30 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| ordin_search(청소년) | 2,728 | 2,219 | 1,075 | -18.7% | **-60.6%** |
| ordin_search(주차) | 2,782 | 2,273 | 1,129 | -18.3% | **-59.4%** |
| ordin_search(환경) | 2,728 | 2,219 | 1,075 | -18.7% | **-60.6%** |
| ordin_search(복지) | 2,749 | 2,240 | 1,096 | -18.5% | **-60.1%** |
| ordin_search(교육) | 2,692 | 2,181 | 1,037 | -19.0% | **-61.5%** |
| trty_search(무역) | 2,114 | 1,797 | 919 | -15.0% | **-56.5%** |
| trty_search(인권) | 716 | 616 | 382 | -14.0% | **-46.6%** |
| trty_search(환경) | 2,465 | 2,148 | 1,270 | -12.9% | **-48.5%** |
| trty_search(항공) | 2,190 | 1,869 | 995 | -14.7% | **-54.6%** |
| trty_search(해양) | 2,268 | 1,950 | 1,074 | -14.0% | **-52.6%** |
| dlytrm_search(상속) | 1,015 | 807 | 487 | -20.5% | **-52.0%** |
| dlytrm_search(채권) | 1,036 | 828 | 508 | -20.1% | **-51.0%** |
| dlytrm_search(이혼) | 1,026 | 818 | 498 | -20.3% | **-51.5%** |
| dlytrm_search(저당) | 1,024 | 816 | 496 | -20.3% | **-51.6%** |
| dlytrm_search(계약) | 1,017 | 809 | 488 | -20.5% | **-52.0%** |
| committee(ftc,담합) | 279 | 243 | 222 | -12.9% | -20.4% |
| committee(ftc,불공정) | 1,972 | 1,698 | 1,018 | -13.9% | **-48.4%** |
| committee(ftc,카르텔) | 74 | 61 | 49 | -17.6% | **-33.8%** |
| committee(ftc,독점) | 73 | 60 | 48 | -17.8% | **-34.2%** |
| committee(ftc,시장지배) | 2,072 | 1,797 | 1,107 | -13.3% | **-46.6%** |
| committee(nhrck,차별) | 1,927 | 1,623 | 977 | -15.8% | **-49.3%** |
| committee(nhrck,인권) | 1,979 | 1,671 | 1,028 | -15.6% | **-48.1%** |
| committee(nhrck,장애) | 1,959 | 1,653 | 1,009 | -15.6% | **-48.5%** |
| committee(nhrck,고용) | 1,931 | 1,625 | 982 | -15.8% | **-49.1%** |
| committee(nhrck,평등) | 1,952 | 1,647 | 1,004 | -15.6% | **-48.6%** |
| special(tt,*) | 2,669 | 2,188 | 1,139 | -18.0% | **-57.3%** |
| special(tt,소득세) | 2,815 | 2,337 | 1,288 | -17.0% | **-54.2%** |
| special(tt,부가가치세) | 2,752 | 2,276 | 1,227 | -17.3% | **-55.4%** |
| special(tt,상속세) | 3,358 | 2,874 | 1,826 | -14.4% | **-45.6%** |
| special(tt,법인세) | 2,739 | 2,264 | 1,215 | -17.3% | **-55.6%** |

### Service Tools (full text) — 10 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| eflaw_service(민법§3) | 901 | 715 | 662 | -20.6% | -26.5% |
| eflaw_service(형법§250) | 918 | 730 | 664 | -20.5% | -27.7% |
| eflaw_service(건축법§3) | 2,271 | 1,801 | 1,409 | -20.7% | **-38.0%** |
| law_service(근로기준법) | 1,538 | 1,259 | 895 | -18.1% | **-41.8%** |
| eflaw_josub(민법§3) | 667 | 537 | 495 | -19.5% | -25.8% |
| prec_service(228541) | 7,653 | 7,743 | 7,581 | +1.2% | -0.9% |
| prec_service(612265) | 36 | 22 | 19 | -38.9% | **-47.2%** |
| detc_service(205207) | 382 | 300 | 294 | -21.5% | -23.0% |
| expc_service(332877) | 1,960 | 1,895 | 1,877 | -3.3% | -4.2% |
| decc_service(232787) | 960 | 894 | 875 | -6.9% | -8.9% |

### Linkage Tools — 5 queries

| Query | XML tok | JSON tok | TOON tok | JSON Δ | TOON Δ |
|-------|---------|---------|---------|--------|--------|
| lnkLs(건축법) | 448 | 387 | 198 | -13.6% | **-55.8%** |
| lnkLs(민법) | 62 | 48 | 37 | -22.6% | **-40.3%** |
| lnkLs(형법) | 62 | 48 | 37 | -22.6% | **-40.3%** |
| lnkLs(도로교통법) | 319 | 276 | 162 | -13.5% | **-49.2%** |
| lnkLs(소득세법) | 193 | 164 | 143 | -15.0% | -25.9% |

---

## 5. Analysis

### Token savings by data type

| Data Type | JSON vs XML | TOON vs XML | N queries |
|-----------|------------|------------|-----------|
| **Search results (tabular)** | -15 to -19% | **-45 to -67%** | 82 |
| **AI search (mixed text+table)** | -7 to -17% | **-18 to -68%** | 10 |
| **Service (structured articles)** | -18 to -21% | **-26 to -42%** | 5 |
| **Service (prose-heavy)** | -7 to +1% | -1 to -9% | 5 |

**Pattern:** TOON's advantage comes entirely from its tabular format (header + CSV rows) which eliminates key repetition in list results. For prose-heavy content where the text itself dominates, all three formats converge.

### Latency

XML is consistently 7-17% faster than JSON across all categories. This is because law.go.kr's backend natively produces XML and converts to JSON server-side. TOON adds negligible client-side overhead (~1ms for JSON→TOON conversion).

### Trade-off matrix

| Factor | XML | JSON | TOON |
|--------|-----|------|------|
| Token efficiency (search) | Baseline | **-15.1%** | **-48.8%** |
| Token efficiency (prose) | Baseline | ~-5% | ~-5% |
| API latency | **Fastest** | +7-17% slower | +7-17% slower (JSON backend + ~1ms) |
| LLM parseability (10 models) | **100%** (250/250) | **100%** (250/250) | **96.4%** (241/250) |
| PlayMCP fit rate | 99% | 99% | 99% |
| SDK maturity | N/A | stdlib `json` | **In development** |
| law.go.kr native | **Yes** | Server-side conversion | Client-side conversion from JSON |

---

## 6. Recommendations

### Option A: Switch to JSON (Conservative)
- **Token savings:** 15.1% overall (consistent across all tool types)
- **Pros:** Zero new dependencies, proven LLM compatibility, stdlib parsing
- **Cons:** 7-17% higher API latency
- **Risk:** Low

### Option B: JSON + TOON conversion (Aggressive)
- **Token savings:** 48.8% overall (up to 67% on search tools)
- **Pros:** Massive token reduction for search-heavy workloads
- **Cons:** Must maintain custom TOON converter until Python SDK stabilizes, 2 of 10 tested models (gemini-2.0-flash, o4-mini) had 16-20% error rates on TOON, TOON spec is v3.0 working draft
- **Risk:** Medium-high (96.4% parseability vs 100% for XML/JSON)

### Option C: Stay on XML (Status quo)
- **Token savings:** None
- **Pros:** Zero risk, fastest API latency, proven pipeline
- **Cons:** Most tokens per response
- **Risk:** None

### Author's recommendation

**Option A (JSON)** as the immediate switch. The 15% token savings is reliable, consistent, and requires no new dependencies. The 7-17% latency increase is acceptable (200ms → 230ms for search tools).

TOON should be revisited when:
1. Python SDK reaches stable release
2. LLM parseability improves (currently 96.4% vs 100% for JSON — gemini-2.0-flash and o4-mini fail on some TOON tabular data)
3. The format becomes more widely adopted in training data

---

## 7. Appendix

### TOON Format Overview

TOON (Token-Oriented Object Notation) is a line-based, indentation-driven serialization format designed to minimize tokens for LLM consumption. Spec: v3.0 working draft ([github.com/toon-format/spec](https://github.com/toon-format/spec)).

**Example — Search results:**
```
# JSON (repeats keys for every row)
{"law": [{"법령명한글": "민법", "법령ID": "001706"}, {"법령명한글": "형법", "법령ID": "001692"}]}

# TOON (header + CSV rows — keys declared once)
law[2]{"법령명한글","법령ID"}:
  민법,001706
  형법,001692
```

### Raw Data

Full benchmark data (102 queries, all metrics) saved at `/tmp/poc_full_results.json`.
