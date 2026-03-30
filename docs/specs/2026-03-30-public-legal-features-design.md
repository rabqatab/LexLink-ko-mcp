# Design: Public Legal Assistance Features

**Date:** 2026-03-30
**Scope:** 4 new MCP tools + 3 new MCP prompts for public-facing legal assistance
**Version:** LexLink v2.1.0 (builds on v2.0.0, 44 existing tools)

---

## 1. Overview

Add 6 features that transform LexLink from an API wrapper into a legal assistance platform for non-lawyers. Three are MCP prompts (LLM-driven reasoning), three are MCP tools (server-side logic), and one feature has both.

| # | Feature | Type | Name(s) |
|---|---------|------|---------|
| 1 | Legal Situation Analyzer | Prompt | `analyze-legal-situation` |
| 2 | Legal Document Explainer | Prompt | `explain-legal-document` |
| 3 | Legal Precedent Checker | Prompt + Tool | `check-legal-precedent` (prompt) + `check_precedent_odds` (tool) |
| 4 | Cross-Domain Legal Resolver | Tool | `legal_resolver` |
| 5 | Plain Korean Translator | Tool | `simplify_article` |
| 6 | Law Amendment Timeline | Tool × 2 | `law_amendment_summary` + `article_amendment_diff` |

**Total additions:** 5 new tools + 3 new prompts
**New tool count:** 44 + 5 = 49 tools, 6 + 3 = 9 prompts

---

## 2. MCP Prompts (3)

### 2.1 `analyze-legal-situation`

**Purpose:** User describes a situation in plain Korean → gets applicable laws, rights, action steps, and precedents.

**Parameters:**
- `situation: str` — plain language description (e.g., "집주인이 보증금을 안 돌려줘요")

**Prompt instructs the LLM to:**
1. Use `aiSearch(situation)` to find relevant law articles
2. Use `prec_search(situation)` to find similar precedents
3. For the most relevant law found, use `article_citation(mst, law_name, article)` to find related provisions
4. Synthesize response:
   - **적용 법률:** Applicable laws with article numbers
   - **당신의 권리:** Rights under those laws
   - **조치 방법:** Actionable steps (내용증명, 소액재판, 노동위원회 신고, etc.)
   - **유사 판례:** Similar precedents and outcomes
   - **관련 기관:** Which government agency or office to contact

### 2.2 `explain-legal-document`

**Purpose:** User pastes legal text (contract, court notice, etc.) → gets plain Korean explanation.

**Parameters:**
- `document_text: str` — chunk of legal text

**Prompt instructs the LLM to:**
1. Identify legal terms in the text
2. Use `dlytrm_rlt_search` / `lstrm_rlt_search` to find everyday equivalents for key terms
3. Use `eflaw_search` / `aiSearch` to identify referenced legal provisions
4. Synthesize response:
   - **쉬운 설명:** Plain Korean explanation
   - **핵심 용어:** Key legal terms translated to everyday language
   - **당신에게 미치는 영향:** What this means for the user
   - **주의사항:** Red flags or unusual clauses
   - **관련 법령:** Referenced legal provisions

### 2.3 `check-legal-precedent`

**Purpose:** User asks a yes/no legal question → gets precedent-backed answer.

**Parameters:**
- `question: str` — legal question (e.g., "임대인이 계약 갱신을 거절할 수 있나요?")

**Prompt instructs the LLM to:**
1. Use `aiSearch(question)` to identify relevant legal provisions
2. Use `check_precedent_odds(question)` to get precedent statistics and factors
3. Synthesize response:
   - **답변:** Yes / No / It depends — with legal basis
   - **판례 통계:** N건 중 M건 인용 (from `check_precedent_odds`)
   - **대표 판례:** Representative case summaries
   - **핵심 판단 요소:** Key factors that influenced outcomes
   - **당신의 경우:** What matters for the user's specific situation

---

## 3. MCP Tools (5)

### 3.1 `check_precedent_odds`

**Purpose:** Search precedents for a legal question and extract outcome statistics + key factors.

**Parameters:**
- `query: str` — legal question or keywords
- `display: int = 20` — number of precedents to search
- `top_n: int = 5` — number of precedents to analyze in detail
- `oc: Optional[str] = None`
- `type: str = "JSON"`
- `ctx: Context = None`

**Logic:**
1. Call `prec_search(query, display=display)` via `run_search`
2. From ranked results, take top `top_n` precedent IDs
3. For each, call `prec_service(id, sections="summary")` via `run_service` to get 판시사항 + 판결요지
4. Extract outcomes from 판결요지 using keyword matching:
   - "인용" → accepted
   - "기각" → rejected
   - "파기" / "파기환송" → overturned
   - "각하" → dismissed
5. Extract key factor phrases from 판시사항:
   - Sentences containing "~여부", "~인지", "~을 고려하여", "~에 비추어"
6. Return structured result

**Return schema:**
```python
{
    "query": str,
    "total_found": int,          # totalCnt from search
    "analyzed": int,             # top_n actually analyzed
    "outcome_summary": {         # keyword-matched outcomes
        "인용": int,
        "기각": int,
        "파기환송": int,
        "각하": int,
        "불명": int,             # couldn't determine
    },
    "key_factors": [str],        # extracted factor phrases (deduplicated)
    "representative_cases": [
        {
            "id": str,
            "name": str,         # 사건명
            "date": str,         # 선고일자
            "case_number": str,  # 사건번호
            "outcome": str,      # detected outcome keyword
            "holding": str,      # 판시사항 (truncated to 500 chars)
            "summary": str,      # 판결요지 (truncated to 500 chars)
        }
    ],
}
```

### 3.2 `legal_resolver`

**Purpose:** Given a situation description, find all applicable laws, precedents, and interpretations in one call.

**Parameters:**
- `situation: str` — plain language description
- `display: int = 5` — results per sub-query
- `oc: Optional[str] = None`
- `type: str = "JSON"`
- `ctx: Context = None`

**Logic:**
1. Call `aiSearch(situation, display=display)` — get relevant law articles
2. Extract unique law names from results
3. For each unique law (max 3), call `prec_search(law_name, display=3)` — get precedents
4. For the top law article, call `article_citation(mst, law_name, article)` — get citation network
5. Call `expc_search(situation, display=3)` — get legal interpretations
6. Aggregate and return

**Return schema:**
```python
{
    "situation": str,
    "applicable_laws": [
        {
            "law_name": str,
            "law_id": str,
            "article": str,          # e.g., "제71조"
            "article_text": str,     # full article content from aiSearch
        }
    ],
    "related_precedents": [
        {
            "id": str,
            "name": str,
            "case_number": str,
            "date": str,
            "court": str,
        }
    ],
    "legal_interpretations": [
        {
            "id": str,
            "title": str,            # 안건명
            "answer": str,           # 회답 (if available from search)
            "date": str,
        }
    ],
    "citations": [
        {
            "from_law": str,
            "from_article": str,
            "to_law": str,
            "to_article": str,
            "type": str,             # "internal" or "external"
        }
    ],
    "laws_analyzed": int,
    "api_calls_made": int,
}
```

**Note:** Makes 10-15 API calls per invocation. Expected latency: 3-5 seconds.

### 3.3 `simplify_article`

**Purpose:** Get a law article with legal terms replaced by everyday Korean (쉬운 법률).

**Parameters:**
- `law_name: str` — law name (e.g., "민법")
- `article: int` — article number (e.g., 750 for 제750조)
- `article_branch: int = 0` — branch number (e.g., 2 for 제37조의2)
- `oc: Optional[str] = None`
- `type: str = "JSON"`
- `ctx: Context = None`

**Logic:**
1. Call `eflaw_search(law_name)` to get MST + law ID
2. Format article number to XXXXXX format
3. Call `eflaw_josub(mst, jo=formatted)` to get article text
4. Extract article text from response (parse XML/JSON for 조문내용)
5. Extract candidate legal terms from text:
   - Korean compound nouns with legal suffixes (~자, ~인, ~권, ~의무, ~행위, ~사항)
   - Multi-syllable Sino-Korean terms (한자어 patterns)
6. For each candidate term (max 20), call `dlytrm_rlt_search(term)` or `lstrm_rlt_search(term)`
7. Build simplified text with inline annotations: "채권자(빚을 받을 권리가 있는 사람)"
8. Return original + simplified + glossary

**Return schema:**
```python
{
    "law_name": str,
    "article": str,              # e.g., "제750조"
    "mst": str,
    "original_text": str,
    "simplified_text": str,      # with inline (쉬운말) annotations
    "term_glossary": [
        {
            "term": str,
            "plain_korean": str,
            "source": str,       # "법령용어DB", "일상용어DB", or "not_found"
        }
    ],
    "terms_found": int,
    "terms_mapped": int,         # successfully found in DB
}
```

**Note:** Knowledge base API coverage is partial. Terms with `source: "not_found"` are included in the glossary so the client LLM can provide its own explanation.

### 3.4 `law_amendment_summary`

**Purpose:** List all revisions of a law within a date range.

**Parameters:**
- `law_name: str` — law name to search
- `date_from: str` — start date (YYYYMMDD)
- `date_to: str` — end date (YYYYMMDD)
- `oc: Optional[str] = None`
- `type: str = "JSON"`
- `ctx: Context = None`

**Logic:**
1. Call `law_search(query=law_name, display=100)` — get all versions
2. Filter results by 공포일자 within `date_from~date_to` range
3. Filter by matching law name (exact or abbreviated match)
4. Sort by date descending
5. Return revision list

**Return schema:**
```python
{
    "law_name": str,
    "law_id": str,
    "period": str,               # "20180101~20260330"
    "revisions": [
        {
            "date": str,         # 공포일자
            "effective_date": str, # 시행일자
            "type": str,         # 제개정구분명 (일부개정, 전부개정, 제정, etc.)
            "announcement_no": str,  # 공포번호
            "mst": str,          # 법령일련번호 (use for article_amendment_diff)
        }
    ],
    "total_revisions": int,
}
```

### 3.5 `article_amendment_diff`

**Purpose:** Compare how a specific article changed between two law versions.

**Parameters:**
- `mst_old: str` — MST of the older version (from `law_amendment_summary`)
- `mst_new: str` — MST of the newer version
- `article: int` — article number
- `article_branch: int = 0`
- `oc: Optional[str] = None`
- `type: str = "JSON"`
- `ctx: Context = None`

**Logic:**
1. Format article number to XXXXXX
2. Call `eflaw_josub(mst=mst_old, jo=formatted)` — get old version text
3. Call `eflaw_josub(mst=mst_new, jo=formatted)` — get new version text
4. Extract article text (조문내용) from both responses
5. Compute line-level diff using Python `difflib.unified_diff`
6. Classify changes: added, deleted, modified
7. Return structured diff

**Return schema:**
```python
{
    "article": str,              # e.g., "제52조"
    "old_version": {
        "mst": str,
        "date": str,
        "text": str,
    },
    "new_version": {
        "mst": str,
        "date": str,
        "text": str,
    },
    "has_changes": bool,
    "changes": [
        {
            "type": str,         # "added", "deleted", "modified"
            "old_line": str | None,
            "new_line": str | None,
        }
    ],
    "unified_diff": str,         # standard unified diff output
    "summary": str,              # "2 lines modified, 1 line added, 0 lines deleted"
}
```

**Note:** If an article doesn't exist in one of the versions (added or repealed), the tool returns the full text as a single "added" or "deleted" change.

---

## 4. SERVER_INSTRUCTIONS Update

Add to the instructions string in `create_server()`:

```
**Public Legal Assistance:**
- legal_resolver: Given a situation, find all applicable laws, precedents, and interpretations in one call
- simplify_article: Get a law article with legal terms replaced by everyday Korean (쉬운 법률)
- check_precedent_odds: Find precedent statistics and key outcome factors for a legal question
- law_amendment_summary: See all revisions of a law in a date range
- article_amendment_diff: Compare how a specific article changed between two versions

**Guided Workflows (Prompts):**
- analyze-legal-situation: Describe your situation in plain Korean → get applicable laws, rights, and action steps
- explain-legal-document: Paste a legal document → get plain Korean explanation
- check-legal-precedent: Ask a yes/no legal question → get precedent-backed answer with success rate

## Tool Selection for Casual Users

When a user describes a personal legal situation (not a specific law query):
→ Use analyze-legal-situation prompt or legal_resolver tool FIRST
→ Do NOT start with eflaw_search unless the user mentions a specific law name

When a user pastes legal text and asks "이게 무슨 뜻이야?":
→ Use explain-legal-document prompt

When a user asks "~할 수 있나요?" or "~되나요?" style questions:
→ Use check-legal-precedent prompt

When a user asks about law changes over time:
→ Use law_amendment_summary first, then article_amendment_diff for details
```

---

## 5. Risks & Limitations

1. **Knowledge base coverage is partial** — `lstrm_rlt_search`/`dlytrm_rlt_search` don't cover all legal terms. `simplify_article` will have gaps (reported as `source: "not_found"`).

2. **Precedent outcome extraction is heuristic** — keyword matching ("인용"/"기각") works for Korean legal text patterns but may misclassify unusual rulings. The `불명` (unknown) category catches these.

3. **Amendment diff depends on article text extraction** — parsing law article content from JSON/XML may fail for complex articles with deeply nested sub-paragraphs (항/호/목).

4. **`legal_resolver` latency** — makes 10-15 API calls per invocation. Expected 3-5 seconds. Acceptable for single comprehensive analysis but shouldn't be called in loops.

5. **Prompt quality depends on client LLM** — the 3 prompts require multi-step tool chaining. Less capable models may skip steps or misinterpret results. Prompts should use explicit numbered steps and REQUIRED/MUST language.

6. **Not legal advice** — all features should include a disclaimer that results are informational and not a substitute for professional legal counsel. This should be embedded in prompt text and tool return values.

---

## 6. Execution Order

1. `_helpers.py` — add shared utility functions (term extraction, outcome keyword matching, text diffing)
2. Tools first (5): `check_precedent_odds`, `legal_resolver`, `simplify_article`, `law_amendment_summary`, `article_amendment_diff`
3. Prompts (3): `analyze-legal-situation`, `explain-legal-document`, `check-legal-precedent`
4. SERVER_INSTRUCTIONS update
5. Documentation update (README, CHANGELOG, etc.)
6. Testing with real queries
