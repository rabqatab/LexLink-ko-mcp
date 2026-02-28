# Changelog / 변경 로그

All notable changes to LexLink are documented here in both English and Korean.

---

## English

### v1.4.0 - 2026-02-28
**Feature: MCP Resources - Law ID Cache**

- **New MCP Resources:**
  - `lexlink://laws/frequently-used` (static) - Cached list of ~20 frequently-used Korean law names mapped to stable 법령ID codes
  - `lexlink://law/{name}` (template) - Look up a specific law's 법령ID by Korean name or abbreviation
- **Implementation:**
  - In-memory cache seeded with 20 verified law entries (IDs verified against live law.go.kr API)
  - Dynamic caching: `eflaw_search` and `law_search` auto-cache top 3 ranked results after each search
  - Both full names and abbreviations are matchable (e.g., "자본시장법" → 자본시장과 금융투자업에 관한 법률)
  - Template resource returns fallback message directing to `eflaw_search` or `law_search` when law is not cached
- **LLM Preference Test (100 runs):**
  - Both Gemini 2.5 Flash and Gemini 3 Flash Preview showed 100% resource adoption (0% search tool fallback)
  - Template resource preferred over static: 92% (2.5-flash) / 70% (3-flash-preview)
- **Other Changes:**
  - Fixed `__init__.py` version: `0.1.0` → `1.3.2`
  - Updated `SERVER_INSTRUCTIONS` with resources section and MST requirement for `article_citation`
- **Impact:**
  - Eliminates redundant `eflaw_search` calls for frequently-used laws
  - LLMs can look up 법령ID directly via resources, skipping the search step

### v1.3.2 - 2026-01-13
**Fix: Smithery Build npm Detection Error**

- **Issue:** Smithery build system incorrectly detected npm as package manager, failing with "npm error path /home/repo/package.json"
- **Root Cause:** Previous `smithery.yaml` only had `runtime: python` which is insufficient for Smithery's current build system
- **Solution:**
  - Rewrote `smithery.yaml` with proper `startCommand` configuration
  - Added `type: stdio` to declare stdio-based MCP server
  - Added `configSchema` for optional `oc` parameter in Smithery UI
  - Added `commandFunction` to run `uv run start` with `OC` env var
- **Files Changed:**
  - `smithery.yaml` - Complete rewrite with `startCommand` configuration
- **Reference:**
  - [perplexity-mcp smithery.yaml](https://github.com/jsonallen/perplexity-mcp/blob/main/smithery.yaml) - Working Python MCP example

### v1.3.1 - 2025-12-25
**Feature: PlayMCP Traffic Logging**

- **New Modules:**
  - `raw_logger.py` - Dashboard-compatible MCP traffic logger
  - `log_processor.py` - Log format converter utility
- **Implementation:**
  - `RawLoggingMiddleware` in HTTP server for request/response capture
  - JSONL format with merged request/response pairs
  - Daily log rotation at `logs/playmcp/YYYY-MM-DD.jsonl`
  - SSE streaming response parsing
- **Log Schema:**
  - `request_id`, `timestamp`, `duration_ms`
  - `method`, `tool`, `arguments`, `result`
  - `status_code`, `client_ip`, `headers`
- **Impact:**
  - Enables traffic analysis for PlayMCP deployments
  - Dashboard-compatible format for monitoring

### v1.3.0 - 2025-12-24
**Feature: Phase 5 - AI-Powered Search Tools**

- **New Tools:**
  - `aiSearch` - AI-powered semantic law search (Tool 25)
  - `aiRltLs_search` - AI-powered related laws search (Tool 26)
- **Implementation:**
  - Uses law.go.kr's intelligent search system (지능형 법령검색)
  - Semantic search for natural language queries
  - Returns full article text (조문내용) for comprehensive results
  - XML parsing with ranked_data for LLM consumption
- **LLM Guidance:**
  - Added ⭐ PREFERRED TOOL hints in tool descriptions
  - Added `tool-selection-guide` MCP prompt for tool selection guidance
  - Tools marked as preferred for vague/unclear queries
- **Impact:**
  - Tool count: 24 → 26 tools
  - MCP prompts: 5 → 6 prompts
  - Better handling of natural language legal queries

### v1.2.9 - 2025-12-09
**Fix: Case-insensitive item key matching for API inconsistency**

- **Issue:** law.go.kr API uses inconsistent XML tag casing
  - `prec` search → `<prec>` (lowercase)
  - `detc` search → `<Detc>` (capitalized)
  - `expc` search → `<Expc>` (capitalized)
- **Fix:** Made `extract_items_list`, `update_items_list`, and `slim_response` case-insensitive

### v1.2.8 - 2025-12-09
**Fix: Case-sensitive item key extraction for non-law searches**

- **Issue:** `extract_items_list()` used capitalized keys ('Prec', 'Detc', 'Expc', 'Decc') but XML parser outputs lowercase ('prec', 'detc', etc.)
- **Result:** `ranked_data` never set → empty responses for all non-law searches
- **Fix:** Changed all 8 calls to use lowercase keys

### v1.2.7 - 2025-12-09
**Refactor: Pattern-based essential field detection**

- **Issue:** Manual field definitions per data type required maintenance for each new API
- **Solution:** Regex pattern matching for automatic field detection
- **Patterns:** `*일련번호` (IDs), `*명한글/*명` (names), `*일자` (dates), etc.
- **Benefit:** Works automatically for any data type without manual definitions

### v1.2.6 - 2025-12-09
**Fix: Data-type-specific essential fields for slim response**

- **Issue:** `slim_response()` used law-specific field names for all data types
  - Precedent searches (`prec_search`) returned empty results
  - Fields like `판례일련번호`, `사건명` were filtered out because they didn't match law fields
- **Solution:**
  - Implemented `essential_fields_by_type` dictionary with correct fields per data type
  - Each API type (law, prec, detc, expc, decc, admrul, elaw) now has its own essential fields

### v1.2.5 - 2025-12-09
**Fix: Add 법령ID to essential fields for correct parameter usage**

- **Issue:** LLM was confusing `법령일련번호` (MST) with `법령ID` in slimmed responses
  - Example: Calling `eflaw_service(id="235555")` when 235555 is MST, not 법령ID
  - Correct usage should be `eflaw_service(mst=235555)` or `eflaw_service(id="001624")`
- **Solution:**
  - Added `법령ID` back to `essential_fields` in `slim_response()`
  - Now LLM can see both fields and use correct parameter
- **Essential fields:** 법령명한글, 법령일련번호, **법령ID**, 현행연혁코드, 시행일자
- **Note:** If ranking not working, ensure EC2 has latest code with relevance ranking

### v1.2.4 - 2025-12-09
**Fix: Slim response mode for PlayMCP size limits**

- **Issue:** v1.2.3's truncation approach was insufficient because `ranked_data` still contained full data (~25KB per 50 results)
- **Solution:**
  - Replaced `truncate_response()` with `slim_response()` function
  - When `SLIM_RESPONSE=true`: removes `raw_content` entirely and keeps only essential fields in `ranked_data`
  - Essential fields kept: 법령명한글, 법령일련번호, 현행연혁코드, 시행일자
  - Fields removed: 법령약칭명, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 공동부령정보, 자법타법여부, 법령상세링크
- **Configuration:**
  - Smithery: No change needed (full response)
  - PlayMCP: Set `SLIM_RESPONSE=true` in systemd service
- **Impact:**
  - Response size reduced from ~50KB to ~3-5KB for 50 results
  - PlayMCP works reliably without size errors

### v1.2.3 - 2025-12-08
**Fix: Response truncation for PlayMCP size limits**

- **Issue:** PlayMCP has response size limits (~50KB), causing "Tool call returned too large content part" errors
- **Solution:**
  - Added `truncate_response()` helper function for optional response size limiting
  - Applied truncation to all 11 search tools (eflaw_search, law_search, elaw_search, admrul_search, lnkLs_search, lnkLsOrdJo_search, lnkDep_search, prec_search, detc_search, expc_search, decc_search)
  - Added `MAX_RESPONSE_SIZE` environment variable (only truncates when set)
- **Configuration:**
  - Smithery: No change needed (no size limit)
  - PlayMCP: Set `MAX_RESPONSE_SIZE=50000` in systemd service
- **Impact:**
  - Smithery keeps full functionality (unlimited responses)
  - PlayMCP avoids size errors with truncated responses + Korean message

### v1.2.2 - 2025-12-06
**Feature: HTTP/SSE Server for Kakao PlayMCP**

- **New Feature:**
  - Added HTTP/SSE server support for Kakao PlayMCP deployment
  - New `uv run serve` command to start HTTP server
  - OCHeaderMiddleware extracts OC from HTTP headers (Key/Token auth)
  - Supports both SSE (`/sse`) and Streamable HTTP (`/mcp`) transports
- **Breaking Changes:**
  - Renamed `LAW_OC` environment variable to `OC` (matches official law.go.kr API naming)
- **Configuration Changes:**
  - Removed `base_url` from Smithery UI config (kept as internal field only)
  - Updated default timeout from 15s to 60s
  - Timeout range extended to 5-120s
- **Documentation:**
  - Added Kakao PlayMCP deployment guide (`docs/DEPLOYMENT_GUIDE.md`)
  - Updated README with PlayMCP deployment section
  - Added `http_server.py` to project structure
- **Impact:**
  - LexLink can now be deployed to Kakao PlayMCP and similar HTTP-based platforms
  - Each PlayMCP user provides their own OC via HTTP header (uses their own API quota)

### v1.2.1 - 2025-11-30
**Fix: Improve LLM guidance for specific article queries**

- **Issue:** LLMs were fetching entire laws (1MB+ for 자본시장법) instead of using `jo` parameter for specific articles like "제174조"
- **Solution:**
  - Added **IMPORTANT** notices in `eflaw_service` and `law_service` docstrings about using `jo` parameter
  - Added **BEST TOOL** guidance in `eflaw_josub` and `law_josub` docstrings
  - Added practical examples: `jo="017400"` for 제174조, `jo="000300"` for 제3조
  - Warned about large response sizes (400+ articles, 1MB+ responses)
- **Impact:**
  - LLMs now correctly use `jo` parameter for specific article queries
  - LLMs prefer `law_josub`/`eflaw_josub` for article queries
  - Faster responses and cleaner output for specific article requests

### v1.2.0 - 2025-11-30
**Feature: Phase 4 - Article Citation Extraction**

- **New Tool:**
  - `article_citation` - Extract legal citations from any law article (Tool 24)
- **Implementation:**
  - HTML parsing approach for 100% accuracy (no LLM hallucination risk)
  - CSS class-based citation type detection (sfon1-4 classes)
  - MST ↔ lsiSeq ID mapping between XML API and HTML pages
  - Zero external API costs (no LLM calls required)
  - ~350ms average extraction time
- **Features:**
  - Distinguishes internal vs external citations
  - Extracts article, paragraph, and sub-item references
  - Consolidates duplicate citations with citation counts
  - Preserves raw citation text for context
- **MCP Prompts Added:**
  - `extract-law-citations` - Extract and explain citations from a law article
  - `analyze-citation-network` - Analyze legal citation network for a law
- **Test Coverage:**
  - Unit tests: Citation module 100% coverage
  - Integration tests: End-to-end extraction validated
  - LLM workflow tests: Gemini 2.0 Flash validated
- **Known Limitations:**
  - Range references (e.g., "제88조 내지 제93조") return first article only
  - External law names require separate search for MST lookup
- **Impact:**
  - Tool count: 23 → 24 tools
  - MCP prompts: 3 → 5 prompts
  - Enables citation network analysis workflows

### v1.1.0 - 2025-11-14
**Feature: Phase 3 - Case Law & Legal Research APIs**

- **Changes:**
  - Added 8 new tools for case law and legal research (15 → 23 tools)
  - `prec_search`, `prec_service` - Court precedents (판례)
  - `detc_search`, `detc_service` - Constitutional Court decisions (헌재결정례)
  - `expc_search`, `expc_service` - Legal interpretations (법령해석례)
  - `decc_search`, `decc_service` - Administrative appeal decisions (행정심판례)
- **Implementation:**
  - Added generic parser functions (`extract_items_list`, `update_items_list`) that work with any XML tag
  - Added 13 new Phase 3 parameters: `prnc_yd`, `dat_src_nm`, `ed_yd`, `reg_yd`, `expl_yd`, `dpa_yd`, `rsl_yd`, `curt`, `inq`, `rpl`, `itmno`, `cls`
  - All ranking and validation functions compatible with Phase 3 tools
  - Zero breaking changes to existing Phase 1 & 2 tools
- **Impact:**
  - Tool count increased by 53% (15 → 23 tools)
  - API coverage increased from ~10% to ~15%
  - Legal research categories expanded by 133% (3 → 7 categories)
  - All 23 tools validated and working in production

### v1.0.8 - 2025-11-13
**Fix: Complete parameter type consistency across all tools**

- **Issue:** v1.0.2 fixed 7 tools but missed 2 additional tools (`eflaw_josub`, `law_josub`), creating inconsistency where same parameters had different types across tools
- **Root Cause:**
  - `eflaw_josub` and `law_josub` still had `id: Optional[str]` and `mst: Optional[str]` instead of `Union[str, int]`
  - `lnkLsOrdJo_search` had `jo: Optional[int]` instead of `Union[str, int]`
  - Caused validation errors when LLMs passed integers to these specific tools
- **Solution:**
  - Fixed `eflaw_josub`: `id` and `mst` now accept `Union[str, int]`
  - Fixed `law_josub`: `id` and `mst` now accept `Union[str, int]`
  - Fixed `lnkLsOrdJo_search`: `jo` now accepts `Union[str, int]`
- **Verification:**
  - All 7 tools with `id` parameter now consistently `Optional[Union[str, int]]`
  - All 6 tools with `mst` parameter now consistently `Optional[Union[str, int]]`
  - All 5 tools with `jo` parameter now consistently `Optional[Union[str, int]]`
- **Impact:**
  - 100% parameter type consistency achieved
  - No validation errors regardless of which tool LLMs choose
  - Better developer experience - same parameters work identically everywhere

### v1.0.7 - 2025-11-10
**Fix: Improve search reliability and LLM guidance**

- **Issue:** LLMs often failed to find common laws like "민법" (Civil Code) because:
  1. Ranking fetch limit (50 results) was too small for large result sets (e.g., 77 results for "민법")
  2. LLMs defaulted to small `display` values (e.g., 5), missing exact matches
  3. `jo` parameter rejected integers, causing validation errors and retry loops
- **Root Cause:**
  - v1.0.5 ranking fetched only 50 results; "민법" was beyond position 50 alphabetically
  - Tool descriptions didn't guide LLMs to use larger display values
  - Parameter type strictness caused UX friction
- **Solution:**
  - Increased ranking fetch limit from 50 to **100 results** (API maximum)
  - Updated `jo` parameter to accept `Union[str, int]` with auto-conversion
  - Added guidance in tool descriptions: **"Recommend 50-100 for law searches (법령 검색) to ensure exact matches are found"**
- **Changes:**
  - All 4 search tools now fetch up to 100 results for ranking
  - All 4 tools with `jo` parameter (`eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`) now accept integers
  - All 7 search tool descriptions updated with display recommendations
- **Impact:**
  - LLMs now find "민법" correctly even with small initial display values
  - No more validation errors when LLMs pass article numbers as integers
  - Better guidance leads to more efficient searches

### v1.0.6 - 2025-11-10
**Enhancement: Improve MCP server quality score (Smithery.ai optimization)**

- **Changes:**
  - Set OC configuration default value to "test" for easier onboarding
  - Added tool annotations to all 15 tools (readOnlyHint=True, destructiveHint=False, idempotentHint=True)
  - Enhanced parameter descriptions in docstrings for all tools
  - Implemented 3 MCP prompts for common use cases
- **Prompts Added:**
  - `search-korean-law`: Search for a Korean law by name and provide a summary
  - `get-law-article`: Retrieve and explain a specific article from a law
  - `search-admin-rules`: Search administrative rules by keyword
- **Impact:** Expected Smithery quality score improvement from 47/100 to ~73/100 (+26 points)
  - Tool annotations: +9pts
  - Parameter descriptions: +12pts
  - MCP prompts: +5pts

### v1.0.5 - 2025-11-10
**Fix: Improve ranking by fetching more results before ranking**

- **Issue:** v1.0.4 ranking was not working properly because it only ranked the limited results returned by the API (e.g., with `display=5`, only 5 alphabetically-ordered results were fetched). If "민법" wasn't in those first 5 results, ranking couldn't help.
- **Root Cause:** Ranking logic was applied AFTER API returned limited results, so relevant matches outside the initial page were never considered.
- **Solution:**
  - When ranking is enabled and `display < 50`, automatically fetch up to 50 results from API
  - Apply ranking to the larger result set (50 results)
  - Trim back to original requested `display` amount after ranking
  - Update `numOfRows` in response to reflect actual number of results returned
- **Implementation:**
  - Updated all 4 search tools: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - Added `original_display` tracking and `ranking_enabled` flag
  - Fetch 50 results when ranking applies, then trim to requested amount
- **Examples:**
  - User requests `display=5` for query "민법"
  - System fetches 50 results (includes "민법" even if it's not in first 5 alphabetically)
  - Ranking places "민법" first
  - System returns top 5 ranked results (now "민법" appears first)
- **Impact:** Ranking now actually works - exact matches appear first regardless of alphabetical position in API results

### v1.0.4 - 2025-11-10
**Feature: Add relevance ranking to search results**

- **Issue:** law.go.kr API returns results in alphabetical order, causing irrelevant matches to appear first (e.g., searching "민법" returned "난민법" first instead of exact match "민법")
- **Solution:**
  - Added intelligent relevance ranking that prioritizes exact matches over alphabetical ordering
  - Ranking applies automatically to XML responses for keyword searches
  - Results are reordered: exact match → starts with query → contains query → other matches
- **Implementation:**
  - Added `ranking.py` module with `rank_search_results()`, `should_apply_ranking()`, and `detect_query_language()` functions
  - Added `parser.py` module for XML parsing and structured data extraction
  - Updated 4 major search tools: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - Ranking preserves raw XML while adding `ranked_data` field for LLM consumption
  - Special handling for `elaw_search`: Detects query language (Korean vs English) and ranks by matching name field
- **Examples:**
  - Query "민법" now returns: "민법" (exact) → "민법 시행령" (starts with) → "난민법" (alphabetical)
  - Query "insurance" ranks: "Insurance Act" → "Insurance Business Act" → other matches
- **Impact:** Significantly improves search relevance, reducing LLM confusion and providing better user experience

### v1.0.3 - 2025-11-10
**Fix: Clarify article number format in tool descriptions**

- **Issue:** LLMs misinterpreted the 6-digit article number format (`jo` parameter), generating "000200" for Article 20 (제20조) instead of correct "002000", resulting in wrong article retrieval
- **Root Cause:** Tool descriptions used ambiguous example "000200" for "Article 2", leading LLMs to incorrectly pattern-match Article 20 → "000200"
- **Solution:**
  - Added comprehensive article number format documentation with multiple examples
  - Added `format_article_number()` helper function in `validation.py` for future use
  - Clarified that XXXXXX format = first 4 digits (article number, zero-padded) + last 2 digits (branch article suffix)
- **Changes:**
  - Updated 4 tools: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`
  - Updated `lnkLsOrdJo_search` which uses separate 4+2 digit format
  - Added clear examples: "000200" (Art. 2), "002000" (Art. 20), "001502" (Art. 15-2)
- **Impact:** LLMs will now correctly format article numbers, preventing queries from returning wrong articles

### v1.0.2 - 2025-11-10
**Fix: Accept both string and integer for id/mst parameters**

- **Issue:** LLMs extract numeric values from XML responses as integers (e.g., `<법령일련번호>188376</법령일련번호>` → `mst=188376`), but tools expected strings, causing Pydantic validation errors
- **Solution:** Changed parameter types to accept both strings and integers with automatic conversion
- **Changes:**
  - Updated 7 tool signatures: `id: Optional[str]` → `id: Optional[Union[str, int]]`
  - Added automatic string conversion at start of each affected tool
  - Applied to: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`, `elaw_service`, `admrul_service`, `lsDelegated_service`
- **Impact:** LLMs can now pass numeric IDs as integers without validation errors

### v1.0.1 - 2025-11-10
**Fix: Remove JSON format option from all tools**

- **Issue:** LLMs were selecting JSON format, but law.go.kr API does not support JSON despite documentation (returns HTML error pages with "미신청된 목록/본문" message)
- **Solution:** Removed JSON as an option from all 14 tool descriptions
- **Changes:**
  - Updated `type` parameter documentation to explicitly state "JSON not supported by API"
  - Added warning in module docstring about JSON format limitation
  - Tool defaults remain XML (working format)
- **Impact:** Prevents LLMs from requesting JSON format and receiving error pages

### v1.0.0 - 2025-11-10
**Initial Release**

- 15 MCP tools for Korean law information access
- 6 core law APIs (eflaw/law search and retrieval)
- 9 extended APIs (English laws, administrative rules, law-ordinance linkage)
- Session configuration via Context injection
- 100% semantic validation
- Production-ready for Smithery deployment

---

## 한국어 (Korean)

### v1.4.0 - 2026-02-28
**기능: MCP 리소스 - 법령 ID 캐시**

- **신규 MCP 리소스:**
  - `lexlink://laws/frequently-used` (정적) - 자주 사용되는 ~20개 한국 법령명과 안정적인 법령ID 매핑 캐시
  - `lexlink://law/{name}` (템플릿) - 한글 법령명 또는 약칭으로 특정 법령의 법령ID 조회
- **구현:**
  - 20개 검증된 법령 항목으로 시드된 인메모리 캐시 (실제 law.go.kr API로 ID 검증)
  - 동적 캐싱: `eflaw_search`와 `law_search`가 검색 후 상위 3개 결과를 자동 캐시
  - 정식명칭과 약칭 모두 검색 가능 (예: "자본시장법" → 자본시장과 금융투자업에 관한 법률)
  - 캐시에 없는 법령은 `eflaw_search` 또는 `law_search` 사용 안내 메시지 반환
- **LLM 선호도 테스트 (100회):**
  - Gemini 2.5 Flash와 Gemini 3 Flash Preview 모두 100% 리소스 채택 (검색 도구 폴백 0%)
  - 템플릿 리소스 선호: 92% (2.5-flash) / 70% (3-flash-preview)
- **기타 변경:**
  - `__init__.py` 버전 수정: `0.1.0` → `1.3.2`
  - `SERVER_INSTRUCTIONS`에 리소스 섹션 및 `article_citation`의 MST 요구사항 추가
- **영향:**
  - 자주 사용되는 법령에 대한 불필요한 `eflaw_search` 호출 제거
  - LLM이 리소스를 통해 법령ID를 직접 조회하여 검색 단계 생략 가능

### v1.3.2 - 2026-01-13
**수정: Smithery 빌드 npm 감지 오류**

- **문제:** Smithery 빌드 시스템이 npm을 패키지 매니저로 잘못 감지하여 "npm error path /home/repo/package.json" 오류 발생
- **원인:** 기존 `smithery.yaml`에 `runtime: python`만 있어 현재 Smithery 빌드 시스템에 부족함
- **해결책:**
  - `smithery.yaml`을 적절한 `startCommand` 설정으로 재작성
  - stdio 기반 MCP 서버 선언을 위해 `type: stdio` 추가
  - Smithery UI에서 선택적 `oc` 파라미터를 위한 `configSchema` 추가
  - `OC` 환경변수와 함께 `uv run start`를 실행하는 `commandFunction` 추가
- **변경된 파일:**
  - `smithery.yaml` - `startCommand` 설정으로 전면 재작성
- **참조:**
  - [perplexity-mcp smithery.yaml](https://github.com/jsonallen/perplexity-mcp/blob/main/smithery.yaml) - 작동하는 Python MCP 예시

### v1.3.1 - 2025-12-25
**기능: PlayMCP 트래픽 로깅**

- **신규 모듈:**
  - `raw_logger.py` - 대시보드 호환 MCP 트래픽 로거
  - `log_processor.py` - 로그 형식 변환 유틸리티
- **구현:**
  - HTTP 서버에 `RawLoggingMiddleware` 추가로 요청/응답 캡처
  - 요청/응답 쌍이 병합된 JSONL 형식
  - `logs/playmcp/YYYY-MM-DD.jsonl` 일별 로그 로테이션
  - SSE 스트리밍 응답 파싱
- **로그 스키마:**
  - `request_id`, `timestamp`, `duration_ms`
  - `method`, `tool`, `arguments`, `result`
  - `status_code`, `client_ip`, `headers`
- **영향:**
  - PlayMCP 배포 환경의 트래픽 분석 가능
  - 모니터링을 위한 대시보드 호환 형식

### v1.3.0 - 2025-12-24
**기능: Phase 5 - AI 기반 검색 도구**

- **신규 도구:**
  - `aiSearch` - AI 기반 의미론적 법령 검색 (도구 25)
  - `aiRltLs_search` - AI 기반 연관법령 검색 (도구 26)
- **구현:**
  - law.go.kr의 지능형 법령검색 시스템 활용
  - 자연어 쿼리를 위한 의미론적 검색
  - 포괄적인 결과를 위한 전체 조문 텍스트(조문내용) 반환
  - LLM 소비를 위한 ranked_data가 포함된 XML 파싱
- **LLM 가이드:**
  - 도구 설명에 ⭐ 우선 사용 도구 힌트 추가
  - 도구 선택 안내를 위한 `tool-selection-guide` MCP 프롬프트 추가
  - 모호하거나 불명확한 쿼리에 우선 사용 도구로 표시
- **영향:**
  - 도구 개수: 24 → 26개
  - MCP 프롬프트: 5 → 6개
  - 자연어 법령 쿼리 처리 개선

### v1.2.9 - 2025-12-09
**수정: API 대소문자 불일치 대응 - 대소문자 무관 키 매칭**

- **문제:** law.go.kr API의 XML 태그 대소문자 불일치
  - `prec` 검색 → `<prec>` (소문자)
  - `detc` 검색 → `<Detc>` (대문자)
  - `expc` 검색 → `<Expc>` (대문자)
- **수정:** `extract_items_list`, `update_items_list`, `slim_response` 대소문자 무관 처리

### v1.2.8 - 2025-12-09
**수정: 비법령 검색의 대소문자 구분 키 추출 오류**

- **문제:** `extract_items_list()`가 대문자 키('Prec', 'Detc', 'Expc', 'Decc') 사용하나 XML 파서는 소문자('prec', 'detc' 등) 출력
- **결과:** `ranked_data` 미설정 → 모든 비법령 검색 빈 응답
- **수정:** 8개 호출 모두 소문자 키로 변경

### v1.2.7 - 2025-12-09
**리팩토링: 패턴 기반 필수 필드 자동 감지**

- **문제:** 데이터 유형별 필드 수동 정의는 새 API 추가 시 유지보수 필요
- **해결책:** 정규식 패턴 매칭으로 필수 필드 자동 감지
- **패턴:** `*일련번호` (ID), `*명한글/*명` (이름), `*일자` (날짜) 등
- **장점:** 새 데이터 유형도 수동 정의 없이 자동 작동

### v1.2.6 - 2025-12-09
**수정: 데이터 유형별 필수 필드 분리**

- **문제:** `slim_response()`가 모든 데이터 유형에 법령 전용 필드명 사용
  - 판례 검색(`prec_search`)이 빈 결과 반환
  - `판례일련번호`, `사건명` 등 필드가 법령 필드와 맞지 않아 필터링됨
- **해결책:**
  - `essential_fields_by_type` 딕셔너리로 데이터 유형별 필드 정의
  - 각 API 유형(law, prec, detc, expc, decc, admrul, elaw)별 필수 필드 지정

### v1.2.5 - 2025-12-09
**수정: 올바른 파라미터 사용을 위한 법령ID 필드 추가**

- **문제:** LLM이 슬림 응답에서 `법령일련번호` (MST)와 `법령ID`를 혼동
  - 예시: MST인 235555를 `eflaw_service(id="235555")`로 호출 (잘못된 사용)
  - 올바른 사용: `eflaw_service(mst=235555)` 또는 `eflaw_service(id="001624")`
- **해결책:**
  - `slim_response()`의 `essential_fields`에 `법령ID` 추가
  - LLM이 두 필드를 모두 확인하고 올바른 파라미터 사용 가능
- **필수 필드:** 법령명한글, 법령일련번호, **법령ID**, 현행연혁코드, 시행일자
- **참고:** 랭킹이 작동하지 않으면 EC2에 최신 코드 배포 필요

### v1.2.4 - 2025-12-09
**수정: PlayMCP용 슬림 응답 모드**

- **문제:** v1.2.3의 트렁케이션 방식은 `ranked_data`에 여전히 전체 데이터가 포함되어 있어 부족함 (50개 결과당 ~25KB)
- **해결책:**
  - `truncate_response()`를 `slim_response()` 함수로 대체
  - `SLIM_RESPONSE=true` 설정 시: `raw_content` 완전 제거 및 `ranked_data`에서 필수 필드만 유지
  - 유지 필드: 법령명한글, 법령일련번호, 현행연혁코드, 시행일자
  - 제거 필드: 법령약칭명, 공포일자, 공포번호, 제개정구분명, 소관부처코드, 소관부처명, 법령구분명, 공동부령정보, 자법타법여부, 법령상세링크
- **설정:**
  - Smithery: 변경 불필요 (전체 응답)
  - PlayMCP: systemd 서비스에 `SLIM_RESPONSE=true` 설정
- **영향:**
  - 응답 크기 50개 결과 기준 ~50KB에서 ~3-5KB로 감소
  - PlayMCP에서 크기 오류 없이 안정적으로 작동

### v1.2.3 - 2025-12-08
**수정: PlayMCP 응답 크기 제한 대응**

- **문제:** PlayMCP가 응답 크기 제한(~50KB)이 있어 "Tool call returned too large content part" 오류 발생
- **해결책:**
  - 선택적 응답 크기 제한을 위한 `truncate_response()` 헬퍼 함수 추가
  - 11개 검색 도구 모두에 트렁케이션 적용 (eflaw_search, law_search, elaw_search, admrul_search, lnkLs_search, lnkLsOrdJo_search, lnkDep_search, prec_search, detc_search, expc_search, decc_search)
  - `MAX_RESPONSE_SIZE` 환경 변수 추가 (설정 시에만 트렁케이션 적용)
- **설정:**
  - Smithery: 변경 불필요 (크기 제한 없음)
  - PlayMCP: systemd 서비스에 `MAX_RESPONSE_SIZE=50000` 설정
- **영향:**
  - Smithery는 전체 기능 유지 (무제한 응답)
  - PlayMCP는 한글 안내 메시지와 함께 트렁케이션된 응답으로 크기 오류 방지

### v1.2.2 - 2025-12-06
**기능: Kakao PlayMCP용 HTTP/SSE 서버**

- **신규 기능:**
  - Kakao PlayMCP 배포를 위한 HTTP/SSE 서버 지원 추가
  - HTTP 서버 시작을 위한 `uv run serve` 명령어 추가
  - HTTP 헤더에서 OC를 추출하는 OCHeaderMiddleware (Key/Token 인증)
  - SSE (`/sse`) 및 Streamable HTTP (`/mcp`) 전송 방식 지원
- **주요 변경사항:**
  - `LAW_OC` 환경 변수를 `OC`로 변경 (공식 law.go.kr API 명명과 일치)
- **설정 변경:**
  - Smithery UI 설정에서 `base_url` 제거 (내부 필드로만 유지)
  - 기본 타임아웃을 15초에서 60초로 변경
  - 타임아웃 범위를 5-120초로 확장
- **문서:**
  - Kakao PlayMCP 배포 가이드 추가 (`docs/DEPLOYMENT_GUIDE.md`)
  - README에 PlayMCP 배포 섹션 추가
  - 프로젝트 구조에 `http_server.py` 추가
- **영향:**
  - LexLink를 Kakao PlayMCP 및 유사한 HTTP 기반 플랫폼에 배포 가능
  - 각 PlayMCP 사용자가 HTTP 헤더를 통해 자신의 OC를 제공 (자체 API 할당량 사용)

### v1.2.1 - 2025-11-30
**수정: 특정 조문 조회를 위한 LLM 가이드 개선**

- **문제:** LLM이 "제174조" 같은 특정 조문 요청 시 `jo` 매개변수를 사용하지 않고 전체 법령(자본시장법의 경우 1MB 이상)을 가져옴
- **해결책:**
  - `eflaw_service`와 `law_service` 문서에 `jo` 매개변수 사용에 대한 **중요** 안내 추가
  - `eflaw_josub`와 `law_josub` 문서에 **최적화된 도구** 안내 추가
  - 실용적인 예시 추가: 제174조는 `jo="017400"`, 제3조는 `jo="000300"`
  - 큰 응답 크기(400개 이상 조문, 1MB 이상)에 대한 경고 추가
- **영향:**
  - LLM이 이제 특정 조문 조회 시 `jo` 매개변수를 올바르게 사용
  - LLM이 조문 조회 시 `law_josub`/`eflaw_josub`를 선호
  - 특정 조문 요청에 대해 더 빠른 응답과 깔끔한 출력

### v1.2.0 - 2025-11-30
**기능: Phase 4 - 조문 인용 추출**

- **신규 도구:**
  - `article_citation` - 법령 조문에서 인용된 법률 추출 (도구 24)
- **구현:**
  - HTML 파싱 방식으로 100% 정확도 (LLM 환각 위험 없음)
  - CSS 클래스 기반 인용 유형 감지 (sfon1-4 클래스)
  - XML API와 HTML 페이지 간 MST ↔ lsiSeq ID 매핑
  - 외부 API 비용 없음 (LLM 호출 불필요)
  - 평균 추출 시간 ~350ms
- **기능:**
  - 내부 인용과 외부 인용 구분
  - 조문, 항, 호목 참조 추출
  - 중복 인용 통합 및 인용 횟수 집계
  - 맥락 파악을 위한 원문 인용 텍스트 보존
- **MCP 프롬프트 추가:**
  - `extract-law-citations` - 법령 조문에서 인용 추출 및 설명
  - `analyze-citation-network` - 법령의 인용 네트워크 분석
- **테스트 커버리지:**
  - 단위 테스트: 인용 모듈 100% 커버리지
  - 통합 테스트: 엔드투엔드 추출 검증
  - LLM 워크플로우 테스트: Gemini 2.0 Flash 검증
- **알려진 제한사항:**
  - 범위 참조(예: "제88조 내지 제93조")는 첫 번째 조문만 반환
  - 외부 법령명은 MST 조회를 위해 별도 검색 필요
- **영향:**
  - 도구 개수: 23 → 24개
  - MCP 프롬프트: 3 → 5개
  - 인용 네트워크 분석 워크플로우 지원

### v1.1.0 - 2025-11-14
**기능: Phase 3 - 판례 및 법령연구 API**

- **변경사항:**
  - 판례 및 법령연구를 위한 8개 신규 도구 추가 (15 → 23 도구)
  - `prec_search`, `prec_service` - 법원 판례 (판례)
  - `detc_search`, `detc_service` - 헌법재판소 결정례 (헌재결정례)
  - `expc_search`, `expc_service` - 법령해석례 (법령해석례)
  - `decc_search`, `decc_service` - 행정심판 재결례 (행정심판례)
- **구현:**
  - 모든 XML 태그와 호환되는 범용 파서 함수 추가 (`extract_items_list`, `update_items_list`)
  - 13개 Phase 3 매개변수 추가: `prnc_yd`, `dat_src_nm`, `ed_yd`, `reg_yd`, `expl_yd`, `dpa_yd`, `rsl_yd`, `curt`, `inq`, `rpl`, `itmno`, `cls`
  - 모든 순위 지정 및 검증 함수가 Phase 3 도구와 호환
  - 기존 Phase 1 & 2 도구에 대한 하위 호환성 완벽 유지
- **영향:**
  - 도구 개수 53% 증가 (15 → 23 도구)
  - API 커버리지 ~10%에서 ~15%로 증가
  - 법령연구 카테고리 133% 확장 (3 → 7 카테고리)
  - 모든 23개 도구 검증 완료 및 프로덕션 준비 완료

### v1.0.8 - 2025-11-13
**수정: 모든 도구에서 매개변수 타입 일관성 완성**

- **문제:** v1.0.2에서 7개 도구를 수정했지만 2개 추가 도구(`eflaw_josub`, `law_josub`)를 누락하여 동일한 매개변수가 도구마다 다른 타입을 가지는 불일치 발생
- **해결책:**
  - `eflaw_josub`, `law_josub`, `lnkLsOrdJo_search` 수정으로 `Union[str, int]` 허용
- **영향:** 100% 매개변수 타입 일관성 달성

### v1.0.7 - 2025-11-10
**수정: 검색 안정성 및 LLM 가이드 개선**

- 순위 지정 가져오기 제한을 50에서 100개로 증가
- `jo` 매개변수가 `Union[str, int]` 허용으로 자동 변환
- 도구 설명에 display 권장 사항 추가

### v1.0.6 - 2025-11-10
**개선: MCP 서버 품질 점수 향상 (Smithery.ai 최적화)**

- OC 설정 기본값을 "test"로 설정
- 모든 15개 도구에 도구 주석 추가
- 3개 MCP 프롬프트 구현: `search-korean-law`, `get-law-article`, `search-admin-rules`
- Smithery 품질 점수 47/100 → ~73/100 예상

### v1.0.5 - 2025-11-10
**수정: 순위 지정 전 더 많은 결과 가져오기로 순위 개선**

- 순위 활성화 시 `display < 50`이면 API에서 최대 50개 자동 가져오기
- 4개 검색 도구 모두 업데이트

### v1.0.4 - 2025-11-10
**기능: 검색 결과에 관련성 순위 추가**

- `ranking.py`, `parser.py` 모듈 추가
- 결과 재정렬: 정확한 일치 → 시작 일치 → 포함 → 기타

### v1.0.3 - 2025-11-10
**수정: 도구 설명에서 조문 번호 형식 명확화**

- XXXXXX = 앞 4자리(조문 번호) + 뒤 2자리(가지조문)
- 예시: "000200" (제2조), "002000" (제20조), "001502" (제15조의2)

### v1.0.2 - 2025-11-10
**수정: id/mst 매개변수에 문자열과 정수 모두 허용**

- 7개 도구 서명을 `Optional[Union[str, int]]`로 업데이트

### v1.0.1 - 2025-11-10
**수정: 모든 도구에서 JSON 형식 옵션 제거**

- law.go.kr API가 JSON을 지원하지 않음 (문서와 다름)
- 14개 도구 설명에서 JSON 옵션 제거

### v1.0.0 - 2025-11-10
**최초 릴리스**

- 한국 법령 정보 접근을 위한 15개 MCP 도구
- 6개 핵심 법령 API + 9개 확장 API
- Context 주입을 통한 세션 설정
- 100% 의미론적 검증
- Smithery 배포 준비 완료
