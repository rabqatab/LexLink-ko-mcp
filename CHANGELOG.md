# Changelog / 변경 로그

All notable changes to LexLink are documented here in both English and Korean.

---

## English

### Unreleased

#### Per-request OC (HTTP mode, opt-in)
- `LEXLINK_ACCEPT_OC_HEADER=true` (default off): a `tools/call` whose HTTP request carries a valid `X-LexLink-OC` (`^[A-Za-z0-9._-]{1,64}$`) uses that OC for every law.go.kr request of the call (composite/chain tools and citation verification included); otherwise the server `OC`. An invalid value is a `VALIDATION_ERROR` (value not echoed). The `oc` tool argument stays ignored in HTTP mode; stdio is unchanged. The value is carried in a contextvar set in the per-call wrapper (`oc_context.py`).
- The per-request OC is masked wherever the env OC is (`redact_oc` now also masks the env OC and the current request OC; request log incl. `LOG_ARGUMENTS`/`LOG_BODIES`, errors, hints, `OC=` links, exception text). `tools/call` log entries carry `oc_source` (`"header"` / `"server"`, never the value). Cache keys never contain the OC, errors are never cached, successes are shared between callers (public data). The user OC works only if the user registered the server IP at open.law.go.kr.
- New error code `OC_AUTH_FAILED` (was `UPSTREAM_ERROR`) for "사용자 정보 검증에 실패", with `oc_source` and, for a header OC, a hint that the caller's own OC needs the server's public IP registered.

#### HTTP request log
- Each entry now carries `user_agent`, `client_name` / `client_version` (from the session's `initialize` `clientInfo`, remembered per `mcp-session-id` in a bounded LRU and dropped on DELETE; values truncated, control chars stripped) and, for `tools/call`, `upstream_calls` (law.go.kr requests that call made; 0 for a cache hit). The count is taken in `client.py` / `citation.py` through a contextvar set in the tool-call wrapper and handed to the logger by (session id, JSON-RPC id).
- `LEXLINK_LOG_ARGUMENTS=true` logs argument values (OC and oc/token/authorization keys removed) without result bodies; `LEXLINK_LOG_BODIES=true` still logs both. Logged strings also mask the literal `OC` env value.
- Every `tools/call` result (errors included, HTTP and stdio) carries `result._meta["lexlink/upstream_calls"]`, the same count, so a gateway that only sees MCP traffic can read it. Added by wrapping the lowlevel `CallToolRequest` handler; `content`, `structuredContent` and `tools/list` are unchanged.

#### Status labels and error classification
- `eflaw_search` `nw` is 1=연혁, 2=시행예정, 3=현행 (measured live; the docs and error text said 2=현행, 3=시행예정, so `nw="2"` returned scheduled rows labelled 현행). `admrul_search` / `ordin_search` `nw` 1=현행, 2=연혁 re-measured and unchanged (3 behaves like 1).
- `article_amendment_diff`: an unknown MST (`NOT_FOUND` upstream) is now a `NOT_FOUND` error; "Article added/deleted" is only reported when both versions exist and the article is really absent from one. `chain_amendment_track` reports a failed diff in `warnings` as well as in `article_diff.error`.
- `*_service` tools (`prec`, `detc`, `expc`, `decc`, `trty`, `cgm_expc`, `special_decc`): an ok response whose body fields are all empty (e.g. `detc_service` id 150756, 150770) carries `warning: "empty_body"`, `empty_fields`, `message`, `hints`.
- The upstream shows the "미신청" page for a wrong `ef_yd`, an unknown id and an invalid `type` too. An invalid `type` is `VALIDATION_ERROR` before the call (on every tool); for a lawService call the client now checks one list request of the same target: list also 미신청 -> `API_NOT_SUBSCRIBED`, list works -> `UPSTREAM_HTML_ERROR` with `may_be_not_subscribed: true` (cause unknowable: rejected parameters or only the 본문 API unapplied; the alternatives stay in the hints; one extra request on the error path only), no answer -> `API_NOT_SUBSCRIBED` with an "unconfirmed" hint.
- Blank or whitespace `query` / `law_name` / `situation` is `VALIDATION_ERROR` before any upstream call (`chain_law_system`, `legal_resolver`, `check_precedent_odds` and 11 more; the 16 list tools whose query defaults to `*` reject an explicit blank).
- `lnkLsOrdJo_search` `jo` accepts `20`, `"0020"`, `"제20조"`, `"20의2"`, `"002002"` (was `int()` error on `"제11조"`); a branch in `jo` fills `jobr`, a conflict is an error.
- `article_citation`: non-numeric `mst` is `VALIDATION_ERROR`; ranges such as 「신탁법」 제46조부터 제48조 list every article from start to end (`range_text`, `range_note`; branch articles inside a range are not enumerated); docstring example fixed (제35조의5; 제37조의2 does not exist) and the Quick Reference states "000300" = 제3조, not 제300조 ("030000").
- Non-numeric `id`/`mst` is `VALIDATION_ERROR` (was a 500-class "not your fault" hint). `admrul_search` `date` accepts int or str and a bad value is a structured `VALIDATION_ERROR`. The missing-OC message in HTTP mode no longer tells callers to pass `oc` (it is ignored there).
- Review follow-ups: ids may have up to 30 digits (행정규칙일련번호 has 13); `cgm_expc_service` / `special_decc_service` "일치하는 고용노동부 법령해석이 없습니다" is `NOT_FOUND` in JSON and XML; `empty_body` needs the body fields to be present, is case-insensitive on `type` (`xml`), survives the cache and `sections="full"`, and is not checked for `type=HTML`; `article_amendment_diff` gives no added/deleted verdict (error) when the two MSTs belong to different 법령ID (renames keep the ID); range citations are de-duplicated against explicit repeats and expanded articles carry `ref_id: null`; non-numeric `jobr` is `VALIDATION_ERROR`.
#### Filters that did nothing, size control, id collision (#45)
- `date` on `prec_search` / `detc_search` / `decc_search` / `special_decc_search` was ignored upstream (prec `date=20240111`: 175,598 rows, no filter). It is now sent as the guide's range parameter `D~D` (`prnc_yd` / `ed_yd` / `rsl_yd`; measured 52 / 31 / 24 / 3 rows) and echoed as `filters_applied`; a `date` that disagrees with an explicit range is `VALIDATION_ERROR`. `dpa_yd` works upstream but the 처분일자 field is almost always empty (decc 7 of 35,255, ttSpecialDecc 0), so it now carries a `dpa_yd_sparse` warning.
- `nb`: a comma list returned 0 rows even when every number exists, so it is `VALIDATION_ERROR` (one call per number); the display form `대법원-2025-두-34754` (0 rows upstream) is converted to `2025두34754`. `detc_search` `nb` is now a string (`2022헌마1312`; the old `int` could not carry it); the upstream ignores `nb` whenever `query` is sent (even `*`: 38,739 rows), so `detc_search` omits `query` for `nb` and rejects a real query with `nb`. A digits-only `nb` is a substring match upstream and warns (`nb_substring`).
- `expc_search` `inq` takes a 질의기관코드 (digits, e.g. 1290000 = 국방부, 132 rows); a name returned 3,805 unrelated rows and is `VALIDATION_ERROR`.
- Ranking fields: `prec_search` ranked on `판례명` and `expc_search` on `사건명`, keys that do not exist in the rows (no-op); now `사건명` / `안건명`. An explicit `sort` is no longer re-ordered by relevance.
- `display` above 100 is capped to 100 on prec/detc/expc/decc/special_decc with a `display_capped` warning (it was sent as is; expc `display=500` was 474 KB). Unknown `sort` / `search` / `gana` / `cls` (numeric 재결구분코드) and `sections` values are `VALIDATION_ERROR` (the upstream ignores them or returns partial counts, e.g. `cls=zz` 716 rows). The `*_service` tools no longer send `lm` together with `id` (a non-exact title made the upstream answer "일치하는 … 없습니다" for a valid id; neutral `notes` entry `lm_not_sent`) and a blank `id` is `VALIDATION_ERROR` (the guides make `ID` required; lm-only returns a 0-byte body).
- `drlaw_search` gains `display` (max 100) and `page` (the upstream honours them; 981 rows in total); `parse_drlaw_html` no longer mislabels the second and later article rows of a law (rowspan cells), which used to give `법령명 "4"`.
- `lsDelegated_service` gains `jo` (client-side filter of the JSON body; `selection` reports articles in the law and matches): 건축법 3.69 MB -> 5 KB (제2조) / 61 KB (제11조); a body over 1 MB warns `large_response`. Policy `size` large -> normal (per-article median 2.3 KB, 5 of 140 articles over 100 KB, max 제80조 283 KB).
- `ordin_service`: every ok response carries a `resolved` block (자치법규명, 지자체기관명, 자치법규ID, 일련번호) because a number can be one ordinance's 자치법규ID and another's 일련번호 (`id=2116749` returns 정읍시립도서관 ... 시행규칙, `mst=2116749` is 서울특별시 건축 조례). New opt-in `verify_id` (default false) also looks up `mst=<id>` (a second request) and reports `id_collision` / `id_is_serial_number` neutrally (both are true; the result is what the id resolved to); with type=HTML it reports `id_check_undetermined`. Policy `upstream_calls` stays 1 (2 with `verify_id`). Take the key from `ordin_search`.
- `aiSearch`: docstring default fixed (display 7, not 20); `page` > 1 warns `page_ignored` (the upstream returns page 1 again); the colloquial `뺑소니` no longer triggers `relevance_unverified` (short alias list `COLLOQUIAL_LEGAL_TERMS`). `ls_rlt_search` documents exact-name matching and adds a hint to zero-result responses.
- Synchronous tool functions now run in worker threads (`install_threaded_tool_calls`, `tool.fn` stays sync) and `ResponseCache` has a lock. Measured over Streamable HTTP with `lsDelegated_service(id=001823)` (4.4-5.1 s): 6 concurrent `cache_stats` pings waited 1.56-4.07 s before and 0.00-0.02 s after.
- Behaviour change: `prec_search` and `expc_search` rows of a keyword query without `sort` are now re-ranked by title relevance (the old ranking field never matched, so they came back in upstream order, 선고일자 descending for prec); pass `sort` to keep upstream order. `nb` is a prefix match upstream (`2010헌바1` returns 109 rows, first 2010헌바125): non-exact rows give `nb_prefix_match` and a single exact row is kept alone in `ranked_data`; whitespace-joined numbers are `VALIDATION_ERROR`. The `*_service` `lm` note is a neutral `notes` entry `lm_not_sent` (not a warning). `aiSearch` page>1 drops the contradicting `no_more_results` hint. Docs: 40-worker limit and cancelled calls in OPERATIONS.
- Tests: `tests/test_filters_and_size.py`, fixture `tests/fixtures/drlaw_page_rowspan_trimmed.html`.
#### Composite tools: term-overlap flags, sample statements, no glossary (issues #43, #31)
- `legal_resolver` / `chain_full_research`: `aiSearch` returns unrelated laws first for colloquial questions (measured: 교통사고 합의금 과실비율 -> 법인세법 시행령 제61조 first). Each `applicable_laws` entry has `matched_query_terms` (the query's words found in its law name, title or text), `low_relevance` (none of the query's distinctive words found) and `upstream_rank`. The flag is an advisory literal word check (`relevance_basis: "term_overlap"`) that errs both ways; it never reorders or drops anything and never skips the precedent or citation lookup (the citation step always runs on the top upstream article). A `low_relevance:` warning says so, `low_relevance: true` is set on the result when every article is flagged, and `query_terms_not_found` lists the query words no article contains.
- Matching: verb endings and particles are cut from query words (이혼하고 -> 이혼, 외도를 -> 외도; `해서`, `싶어요`, `돌려줘요` alone are ignored), a 3+ character word also matches by its stem without the last character (양육권 ~ 양육, 퇴직금 ~ 퇴직급여), a 4+ character word by both halves (공정이용 ~ "공정한 이용"), and 집주인/세입자/남편/아내 by their statute word. Generic words (재산, 청구, 보증금, 손해배상, 합의금) never count as overlap on their own unless the query has nothing else.
- `legal_resolver` precedents: searched first by the situation's distinctive words (`search_basis: "situation_terms"`, retried once with the longest word, a 3-character one cut by its last character), then, if fewer than 3, by law name (`search_basis: "law_name"`). Each has `matched_query_terms` on its 사건명; a law-name hit with no shared word is `relevance_unverified: true` and warned. Repeated ids and 사건번호 are skipped (2024노3424 appeared twice for 근로기준법 퇴직금).
- `chain_full_research` carries `related_precedents` (before, the 집주인 보증금 case showed 0 precedents), `precedent_analysis.sample`/`statistics_note`/`uncounted_cases`, the flags, and an `api_calls_made` that counts every request.
- `check_precedent_odds`: a case is counted in `outcome_summary`/`key_factors` only when a distinctive query word is in its 사건명, 판시사항 or 판결요지 (the 본문 is not used: every 본문-search hit contains the words by construction). Other fetched cases go to `uncounted_cases` without an outcome; `representative_cases` holds counted cases only. Cases with a distinctive word in the 사건명 are fetched first, and body fetches stop after top_n counted or top_n+4 attempts. A query with no comparable word (ㅋㅋㅋㅋㅋ) or no related case returns empty statistics and a `low_relevance:` warning; fewer than 3 counted cases is `small_sample`; all-불명 counts get an `outcome_unclear:` warning. `type="HTML"` fetches the body as JSON (before, every case was 불명). `sample` and `statistics_note` say the counts are the sample's only, not a win probability; there are no percentages. Real queries keep usable counts (measured: 이혼 위자료 5, 재산분할 기여도 5, 유책배우자 이혼청구 5 (+1 uncounted), 양육권자 변경 3 (+2), 상간녀 위자료 0 counted of 1 found).
- #31 `check_precedent_odds(type="XML")` returned empty `holding`/`summary`/`key_factors`: `strip_html` removed the `<![CDATA[...]]>` wrapper together with the text. `strip_html` now unwraps CDATA first and strips only real tags, so text such as `a < b ... c > d` survives.
- `simplify_article`: the description, server instructions and output say the text is not simplified (`text_simplified: false`, `simplified_text` equals `original_text`) and that there is no glossary: `term_glossary` is always empty (`glossary_status: "withheld"`) and no term lookup is made (requests: 2 instead of 4-22). The 법령용어 database marks as 동의어 pairs that differ in law (배우자 -> 반려자, 피한정후견인 -> 한정치산자, 재산관리인 -> 관재인, 위법행위 -> 불법행위, 사용자 -> 경영자, 채무자 -> 부채자) and its relation labels do not separate them from sound pairs, so no safe rule exists. `extract_legal_terms` now works on word boundaries (no 지방자, 특별자, 지방자치단체인).
- `chain_dispute_prep` returns search metadata only (no holdings or text) and says so (`content_note`, description). Rows of the same judgment (same 사건번호, court and date, several ids; measured 개인정보 유출 과징금: 2024구합70753 twice) are returned once (`search_modes[...].duplicates_removed`). `title_matches_query` uses the same distinctive-word rule; a `low_relevance:` warning counts the rows without a match.
- `chain_law_system` under `SLIM_RESPONSE`: the note said 80 entries while the 20KB guard left 22 (건축법). `delegation_tree.note`, `truncated_notes`, `truncated_fields` and `truncated_note` now state the number really shown ("337건 중 22건만 표시") and point to `lsDelegated_service`.
- Prompts `get-law-article` and `get-article-with-citations` take `article_number` as int or str in the repo's jo style (`"35의5"`, `"제35조의5"`, `"35-5"`, `"003505"`) and pass `article` + `article_branch`; `analyze-law-citations` accepts the same forms. A bool and an explicit branch 0 (`"35의0"`) are rejected.
- Policy metadata `upstream_calls`: check_precedent_odds 7 -> 11 (measured 3-11), legal_resolver 8 -> 10 (measured 5-9), chain_full_research 16 -> 20 (measured 13-14), simplify_article 6 -> 3 (measured 2).
- Tests: `tests/test_composite_tools.py` (real query shapes: 아이 양육권, 남편이 외도를 해서 이혼하고 싶어요, 집주인 보증금, 교통사고 합의금 과실비율, 이혼 위자료); three existing tests were adapted to the new output.
#### Precedent citator, 헌재 leads, 부칙 relative dates
- New tool `prec_status` (68 tools in total; #35): has a later Supreme Court en banc decision overruled this precedent? There is no upstream citator, so it searches the case number as a quoted phrase in the full text (`prec_search query='"94므1713"' search=2`, newest first), keeps the later 전원합의체 decisions, reads each (`prec_service`, at most `max_scan` = 5, max 10) and reports evidence with the source decision and the verbatim quote: a `(변경)`/`(폐기)` marker after the case in the overruling decision's 참조판례 (`explicit_marker`) or a sentence naming the case with 변경/폐기 (`explicit_sentence`). Direction matters (an old decision never names its overruler). A generic "견해에 배치되는 범위 내에서 변경한다" sentence without the case number is only a `leads` entry (`possible_overruling_needs_review`). Status values: `overruled_found`, `possible_overruling_needs_review`, `no_overruling_found_in_searched_set` (never "not overruled"; `searched_scope` lists rows, scanned and unscanned candidates). Upstream calls: 1 (target) + 1-3 (citing list) + `max_scan`. Measured live on 32 known overrulings (mined from the `(변경)` markers of 180 en banc decisions, plus 94므1713 -> 2013므2250 and 88다카16867 -> 2018다248909) and 20 controls (cases cited by en banc decisions without a marker): 31/32 reported `overruled_found` with the right source decision, 1/32 (88다카16867, whose overruler does not mark it) only as a lead; 0/20 false `overruled_found` (final numbers in the review-fix item below). Limits: ground truth for 31 pairs is the same marker field the tool reads, so this measures discovery, not marker accuracy; 3 of 52 runs hit an upstream timeout and were reported as errors.
- New tool `law_constitutional_check` (#37): 헌재 위헌/헌법불합치 leads for one article. `law_as_of` is unchanged (`in_force` is never touched; its caveat now points to this tool). Finds decisions whose 사건명 names the law and article (`detc_search search=2`, one page of 100), reads up to `max_scan` = 6 (max 10) `detc_service` bodies and classifies the 주문 (위헌, 헌법불합치, 한정위헌, 합헌, 각하, 기각; a multi-provision 주문 is matched sentence by sentence). Checked: 형법 제241조 (2009헌바17 위헌 2015-02-26 found; 2007헌가17 합헌), 민법 제847조 (95헌가14 헌법불합치 1997-03-27; 2012헌바357 합헌 2015), 민법 제809조 (95헌가6 헌법불합치 1997-07-16; the 2018헌바115 주문 keeps 제809조 합헌 apart from 제815조 헌법불합치), 민법 제844조 (2013헌마623 헌법불합치). Limits: decisions whose 사건명 does not name the article are missed; effect dates (소급효, 잠정적용 시한) and later amendments are not computed.
- `law_as_of`: 부칙 relative dates ("공포 후 6개월이 경과한 날부터 시행") are computed from the 부칙's 공포일자 (민법 제157조/제160조: the period starts the day after 공포, elapsed date = next day; 공포 2021-04-20 + 6개월 = 2021-10-21) and reported in `partial_effect.article_scan.matches[].later_dates` / `computed_from_announcement`. The rule gave the `시행일자` of all 16 amendments checked (스토킹범죄의 처벌 등에 관한 법률 3, 가정폭력범죄의 처벌 등에 관한 특례법 13). A date that cannot be computed (대통령령으로 정하는 날, 시행일 기준 상대일, 공포 후 N개월 이내, no 공포일) gives `in_force: null` with reason `ARTICLE_STAGED_DATE_UNRESOLVED` for that article. Tests use the real 부칙 of the 2023-07-11 스토킹범죄의 처벌 등에 관한 법률 amendment.
- Investigated 2013므3963·3970 (2015-06-24, #36): not a search bug. The case is not in the upstream 판례 DB: `nb` variants (single, joined, comma, 공백, ㆍ), `nb=2013므` (11 decisions, none of them), the decision-date filter (57 decisions on 2015-06-24, no 므) and direct `lawSearch.do` calls all return nothing. Documented in API_REFERENCE ("알려진 한계"), together with how `nb` really works (prefix match; a joined case is indexed under its first number only).
- Review fixes for the three tools above (PR #47). `prec_status`: `94므1713`, `1994므1713` and `대법원 1995. 5. 23. 선고 94므1713 판결` all resolve (the index writes pre-2000 numbers with two-digit years; both spellings are tried); new statuses `case_not_found` (number not in the index, e.g. the joined case's second number `94므1720`, `2099다99999`, `2013므3963`: nothing can be said) and `incomplete_search` (citing list truncated, candidates beyond `max_scan`, a body not served or a 200 body that does not parse; the candidates are named), so `no_overruling_found_in_searched_set` now means everything was read; the statement counts decisions, `id=abc` is `VALIDATION_ERROR`; a sentence in a 반대의견/별개의견/보충의견 section is never evidence; a sentence naming two cases ties 변경 to the right one; `변경함이 상당하다` / `변경하는 것이 타당하다` / `폐기된다` give a lead only (0 occurrences in 180 en banc decisions, precision unmeasurable) while the explicit wording matched a marker for the same case in 135 of 137 sentences; "더 이상 유지하기 어렵다" in the majority opinion is a lead (this is how 2018다248909 treats 88다카16867; 80므60 -> 2015므8351 is found the same way). Re-measured: 31/32 `overruled_found` with the right source, 88다카16867 as a lead, 0 false `overruled_found` in 20 controls (4 controls are not in the index: `case_not_found`; 1 control turned out to be a real overruling, 80므60, reported as a lead).
- `law_constitutional_check`: the law name is resolved to the official name through `law_search` (abbreviations such as `가족관계등록법` work, an unknown name is a `VALIDATION_ERROR`, `민법` is kept apart from `민법 시행령`); candidates come from the quoted-phrase full-text search (`"형법 제270조"`), not only from the 사건명, and a decision titled for another article is kept when its 주문 or 심판대상조문 names this one; the 주문 is split per article (`제1조는 합헌이나 제2조는 위헌`); an adverse 주문 that cannot be tied to the article is `needs_review`, never adverse; a truncated list or unread candidates give `incomplete_search`; every result carries the note that the current text may have been amended since. Found 8 of 8 (형법 제270조 2017헌바127, 민법 제1118조 2020헌가4, 민법 제815조 2018헌바115, 가족관계등록법 제14조 2015헌마924, plus 형법 제241조, 민법 제847조/제809조/제844조), where title-only search found none of the first four. Defaults: `max_scan` 8 (max 12), policy 10 usual / 14 max upstream calls.
- `law_as_of`: an uncomputable 부칙 date now makes `in_force` null only when it comes from the chosen version's own amendment; an older amendment's `대법원규칙으로 정하는 날` is a caveat (`partial_effect.earlier_amendment_unresolved_dates`) because a later revision has taken effect (the 2016 부칙 of 가족관계의 등록 등에 관한 법률 had made 제14조/제15조 null at 2018-01-01 and 2026-01-01; 13 queries over 7 laws now give no null from this path). More forms: `공포 후 1년 6개월이 경과한 날`, `…경과한 날이 속하는 달의 1일`, `…의 다음 날` are computed; other continuations, `공포 6개월 후`, `공포한 날부터 N개월이 경과한 날` (one-day offset unverified) and `공포 후 N개월 이내` stay unresolved; item lines under a `각 호` head that name the article are evaluated.

#### Integration review fixes
- Term matching (`legal_resolver`, `chain_full_research`, `check_precedent_odds`, `chain_dispute_prep`): a query word must start a word of the text, no longer match in the middle of one (측정: `legal_resolver("남편 외도")` listed 재산국외도피 cases because 외도 sits inside 국외도피). 양육권~양육, 이혼하고~이혼, 퇴직금~퇴직급여 still match. A criminal case (사건번호 도/노/고합 ...) that shares only one query word is `relevance_unverified` (`unverified_reason: criminal_case_single_term`; 2012도14788 matched only 남편). When the citation step ran on a top article flagged `low_relevance`, a `citations_low_relevance:` warning names that article.
- `check_precedent_odds`: with two or more distinctive query words a case is counted only if a word of 3+ characters is in its 사건명 or 판시사항 (not only the 판결요지); `아이 양육권` no longer counts 부당해고구제재심판정취소, 미성년자입양허가, 친생자관계부존재확인. The results are re-sorted so cases with a query word in the 사건명 come first (`sample.selection` says so), and `statistics_note` says the relevance check is rough. Re-measured live: 이혼 위자료 5 counted, 재산분할 기여도 5, 유책배우자 이혼청구 5 (+1 uncounted), 아이 양육권 1 (+8 uncounted), 양육권자 변경 1 (+4; was 3 +2, the two dropped cases name neither 양육권자 in the 사건명 nor in the 판시사항).
- `law_constitutional_check`: the older 전문 form without brackets (`주           문이 사건 ...이           유`, e.g. 2009헌바106) is parsed. A decision whose outcome stays 불명 is now `needs_review` (`needs_review_reason`), so the status can no longer be `no_adverse_decision_in_searched_set` while a title-matched decision was unreadable (민법 제1008조).
- `law_as_of`: a 부칙 sentence naming the article with 공포-relative wording that is not computed ("공포 후 1년 6개월이 되는 날", "공포 후 1년 6개월 후", "공포한 날이 속하는 달의 다음 달 1일", "공포일부터 1년이 경과한 날", "공포한 날이 속하는 해의 다음 해 1월 1일") is reported as `unresolved` instead of being ignored. "공포한 날부터" and "공포한 날의 다음 날부터" are computed.
- `article_amendment_diff` with two MSTs of different 법령ID is `VALIDATION_ERROR` even when the article exists on both sides (renamed laws keep their 법령ID and still work).
- Prompt `explain-legal-document` no longer builds a 법률 용어/쉬운 말 table from `dlytrm_rlt_search` / `lstrm_rlt_search` (those links include pairs that differ in law); it uses `lstrm_search` definitions and says no verified plain-language mapping exists.
- `prec_status`: "변경하고 있는 것이 아니다" (and 변경한/하는 것이 아니다) is negated wording, not evidence. `prec_search nb="1994므1713"` finds nothing (pre-2000 cases are indexed with a two-digit year); a zero-row result now carries an `nb_year_form` hint to use `94므1713`. `simplify_article` policy evidence is `primary` (it returns the raw article text).
- Operations note: #46 monkey-patches `FuncMetadata.call_fn_with_arg_validation` of the mcp SDK to run tool functions in worker threads, so the dependency stays pinned to `mcp>=1.26.0,<1.27`; re-check the patch before raising the pin.

#### Clean stdio shutdown
- Closing stdio while a tool call ran (tool functions run in worker threads since #46) ended the process with return code 1 and an `anyio.ClosedResourceError` traceback (the response was written to a stream the SDK had already closed). `lexlink.stdio_server.main` now treats a run that fails only with closed-stream errors as a normal disconnect (exit 0, no traceback); every other error still propagates. Test: `tests/test_stdio_shutdown.py`.

#### Tool policy metadata
- Every tool's `tools/list` entry now carries `_meta["lexlink/policy"]` (contract v1): `version`, `category`, `evidence` (primary / derived / heuristic / none), `size` (normal / large), `upstream_calls` (usual maximum law.go.kr requests per call), `may_expose_credential` and optional `notes`. The table is `TOOL_POLICIES` in `src/lexlink/tool_policy.py`, filled from the code and live measurements; it is registered through the existing `server.tool` wrapper (FastMCP 1.26 `meta=`). A tool without an entry makes `create_server()` fail. Tool behaviour, input schemas and annotations are unchanged. Contract: `docs/API_REFERENCE.md`; tests: `tests/test_tool_policy.py` (real clients over stdio and Streamable HTTP).

#### Amendment history, old/new and 3단 comparison, appendices, term dictionary
- 11 new tools (66 total), each validated before the call because the upstream answers wrong input with a silent "0 results": `oldAndNew_search` / `oldAndNew_service` (신구법 대비), `thdCmp_search` / `thdCmp_service` (3단 비교, `knd` 1 인용조문 / 2 위임조문), `lsJoHstInf_search` (laws with amended articles by date or period), `lsHstInf_search` (laws changed on a day), `delHst_search` (deleted-data log), `lsAbrv_search` (law-name abbreviations), `licbyl_search` (별표/서식 list), `lstrm_search` / `lstrm_service` (legal-term dictionary; `lstrm_ai_search` stays the related-term link tool and has no definitions).
- Bad dates (`20261301`), unknown codes (`sort`, `rr_cls_cd`, `dic_knd_cd`, `search`, `gana`, `del`/`licbyl` `knd`), a 법령종류 `knd` that is not of the form `A0002` (A0001 헌법, A0002 법률, A0007 대통령령, A0009 총리령, A0011 부령 ...), and a missing required date or `knd` are `VALIDATION_ERROR` (full-width digits ０-９ in numeric arguments such as dates, id, mst, org, nb, anc_no, trm_seqs are folded to ASCII first, nothing else is; code/enum arguments such as `knd`, `search`, `rr_cls_cd`, `sort` are not folded and give `VALIDATION_ERROR`; `gana` uses the guide's codes `ga na da ra ma ba sa ah ja cha ka ta pa ha etc`; the full 법령종류 code list is not published, so only its shape is checked); an unknown id/mst is `NOT_FOUND`; zero rows is `ok` with `warning: "no_results"` and an empty list. List rows are always lists (upstream sends a bare object for one row). A page past the end of `lsJoHstInf_search` / `lsHstInf_search` / `delHst_search` is `warning: "page_out_of_range"` with the real total (upstream says `totalCnt: 0`).
- `thdCmp_service` is very large without `jo` (tool response, 인용조문/위임조문: 가사소송법 89/167 KB, 가족관계의 등록 등에 관한 법률 204/251 KB, 민법 610/592 KB; with `jo` 1-9 KB). The upstream has no article parameter, so `jo` keeps only that article's rows of the JSON body (`selection`, `ARTICLE_NOT_FOUND`); the result carries `anchor` (the law the upstream answered for) and warns when a 시행령/시행규칙 id returns its 모법. The `SLIM_RESPONSE` guard applies and points to `jo`.
- `lsAbrv_search`: the upstream ignores query/display/page and returns all 2,714 rows (2.3 MB); the tool fetches the unfiltered list once (one cache key; an incomplete list is an error and is not cached), applies the 등록일 range and the name/abbreviation filter, and pages itself.
- `lstrm_service` takes `trm_seqs` (the 법령용어ID from `lstrm_search`, comma list allowed) because the name lookup is NOT_FOUND for names with spaces, slashes or parentheses; it reads the XML form: the JSON form merges entries into parallel arrays and cannot say which 출처/용례 belongs to which entry. `licbyl_search` returns links and metadata only (documented), never file contents.
- `oldAndNew_service` returns a `caution`: the comparison table is upstream-edited and can differ from the statute (measured: 민법 제379조, mst 284415, raw DRF 구조문 "연 5분" vs old revision "연 5푼"); verify with `eflaw_service` / `law_as_of`. A mismatched id and mst warns.
- `thdCmp_service` `jo` on a knd=2 body whose 법률조문 rows carry a chapter heading as 조내용 (측정: 소득세법) keeps the rows that have delegated 시행령/시행규칙 children and warns (`selection.own_text_is_heading`) instead of a false ARTICLE_NOT_FOUND. `lsAbrv_search` with a `totalCnt` that disagrees with the rows returns the rows with a warning and does not cache them. `&reg`-style entities without `;` are not decoded.
- Fixtures (trimmed real responses; the OC is replaced by the public sample `OC=test`) and offline tests: `tests/test_history_compare.py`.

#### Leftover fixes and operations checks (#39)
- `thdCmp_service` `jo`: a kept row whose own 조내용 is a chapter/section heading (it carries delegated children) is marked per row with `own_text_is_heading: true`, also when real rows share its 조번호; `selection.heading_rows` counts them and the warning says how many of the returned rows; `selection.own_text_is_heading` stays true only when all are. A heading must look like one: the unit word ends the token (`제3장 총칙`, `제2장의2 ...`), the title is short and not a clause, and the row has no 조제목, so a titled article whose text starts "제3장에 따른 ..." is no longer a heading.
- `lsAbrv_search`: `upstream_total_mismatch` no longer replaces `no_results` / `page_out_of_range` (warnings are joined with " / "); a missing or non-numeric totalCnt reads "(missing or not a number)" instead of "None".
- `redact_oc`: an OC under 6 characters is replaced only directly after an ASCII-delimited `OC` label (`OC g4c 는`, `oc: g4c`, `(OC=g4c,`) or after `=` / `&` as before; Korean text next to it is kept. Other forms are NOT redacted: an unlabelled short value (`legal g4c text`), `DOC g4c`, `OC g4cx`.
- `normalize_jo`, `linkage.normalize_jo_code` and the `*_yd` date-range check share one helper: full-width digits are folded to ASCII (and ASCII is what is sent upstream, e.g. `eflaw_search` `ef_yd="２０２００１０１~２０２４１２３１"`); Arabic-Indic and other Unicode digits are rejected, as in `ascii_digits`.
- A JSON body that starts with `{` or `[` (after an optional BOM) but does not parse (typically a cut-off transfer, HTTP 200; also text such as `[공지] ...` and over-deep nesting) is an `UPSTREAM_ERROR` ("invalid JSON body") and is not cached; before it was returned as `ok` and cached.
- A `lawService` HTML page whose visible text is only "일치하는 … 없습니다" (e.g. `oldAndNew_service` `type=HTML` with an unknown mst) is `NOT_FOUND`, as the XML form already was.
- XML/HTML of oldAndNew, thdCmp, lsJoHstInf, lsHstInf, delHst, lsAbrv, licbyl, lstrm compared live with raw DRF: `raw_content` equals the raw body except that the upstream's `OC=...&amp;` inside result links is removed by the redaction; 0-row answers stay `ok` + `no_results` (XML); `lsJoHstInf` / `delHst` accept JSON and XML only and `thdCmp_service` `jo` needs JSON (`VALIDATION_ERROR`, checked before any call).
- Checked and unchanged (see docs/OPERATIONS.md): 503 at `LEXLINK_MAX_SESSIONS`, rate-limit key under a spoofed `X-Forwarded-For`, `LEXLINK_LOG_BODIES` content, log retention and file modes, upstream 500 / timeout / empty body.

#### As-of-date lookup (hypeproof-legal #59)
- New tool `law_as_of(law_name, as_of, article?, article_branch?, as_of_end?)`: the law (or one article) in force on date D. It lists every (MST, 시행일) of the law, picks the latest 시행일 <= D and fetches that exact revision (`lawService target=eflaw`, MST + efYd). Returns MST, 시행일, 공포일, article text, difference from the current text, later/scheduled/promulgated-not-yet-effective versions, a period mode (`as_of_end`) and a plain statement. `in_force` is true / false / null: false has `BEFORE_FIRST_ENFORCEMENT`, `BEFORE_EARLIEST_AVAILABLE_VERSION`, `AFTER_REPEAL` (`폐지제정` is not a repeal); null is `NOT_CURRENT_UPSTREAM` (law with no 현행/시행예정 row and no repeal). Same-name older 법령ID is used only within one lineage (same 법령구분명 and a 법률/대통령령/헌법 or the same ministry). 부칙 clauses that delay an article are quoted in `partial_effect.article_scan`. Upstream failures are never reported as "not found". Tool count 54 -> 55.
- `eflaw_search` gets optional `nw` (1=연혁, 2=시행예정, 3=현행); default unchanged. Its `ef_yd` doc now says it is a 시행일 range filter.
- `law_amendment_summary` gets `date_basis` ("announced" default = 공포일, or "effective" = 시행일 and always includes the revision in force at `date_from`); schema descriptions added to the date arguments and to `chain_amendment_track`.
- `eflaw_service` / `eflaw_josub`: `ef_yd` without `mst` (id + ef_yd) is a `VALIDATION_ERROR` (upstream ignores it or returns `{}`); with `mst` + `ef_yd` the `id` is dropped (with `id` upstream returns the current text). `ef_yd` accepts int or str.
- Schema-level `Field` descriptions on `id` / `mst` / `ef_yd` of the service tools point to `law_as_of`. `article="007602"` with a conflicting `article_branch` is an error.

#### Issue fixes (#10-#20)
- #10 `law_amendment_summary` / `chain_amendment_track` returned one revision: the eflaw LID history query now sends `nw=1,2,3` (민법: 1 -> 37 revisions). Upstream failures while resolving versions are returned as errors instead of "law not found".
- #11 `lm` is sent upstream as `LM` (lowercase matched nothing); `law_service`, `eflaw_service` (new `lm` parameter), `elaw_service` accept `lm` alone.
- #12 `article_citation` resolves "같은 법" (and "같은 법 시행령/시행규칙") to the most recently named law as an external citation; "이 법" stays internal. "100% accurate" wording softened.
- #13 `check_precedent_odds` classifies the outcome from the 주문 only (new `extract_order` / `classify_order`) and returns the 주문 text as `order`. Labels: 파기환송, 파기자판, 파기, 상고기각, 항소기각, 항고기각, 원판결변경, 일부인용, 인용, 기각, 각하, 취소, 무죄, 유죄, 공소기각, 불명. Not a win rate (see `outcome_note`). `extract_outcome` is removed.
- #14 `eflaw_service` with `mst` now requires `ef_yd` or `id`; otherwise it fails fast with a `VALIDATION_ERROR` instead of the misleading API_NOT_SUBSCRIBED page.
- #15 `aiSearch`, `legal_resolver`, `chain_full_research` add a `relevance_unverified` warning when no result shares a character bigram with the query (lexical hint only, nothing is dropped).
- #16 `chain_law_system`: `admin_rules` schema changed to `{name, id, article}` taken from the 위임행정규칙 entries of the delegation tree; `linked_ordinances` now comes from `lnkLsOrd` (real 자치법규) with `linked_ordinances_total`. Failures are reported in `warnings` instead of empty lists.
- #17 `SLIM_RESPONSE=true` is guarded centrally (wrapper around `server.tool`): responses over 20,000 bytes are trimmed and flagged with `truncated` / `truncated_notes`. Default mode is unchanged.
- #18 Zero-result guidance for `lstrm_ai_search`, `dlytrm_search`, `ls_rlt_search`, `lstrm_rlt_jo_search`; JSON `raw_content` is trimmed to the requested page's rows (e.g. `prec_search` display=5: 47 KB -> 1.6 KB).
- #19 Misc: `id_note` separates 자치법규ID / 일련번호; `committee_service` all-"null" body is `NOT_FOUND`; `simplify_article` maps terms from the correct `연계용어` level (동의어/상위어) and its text is unchanged; `drlaw_search` parsed rows; `elaw_search` markup stripped; OC no longer appears in HTTP debug logs.
- #20 `legal_resolver` citations verified working after #7; regression test added (no code change).

#### Idle session expiry
- `LEXLINK_SESSION_IDLE_TTL_SEC` (default 3600, `0` disables): Streamable HTTP sessions with no activity for that long are terminated by the server (internal DELETE sent straight to the inner app) and their binding removed, freeing the `LEXLINK_MAX_SESSIONS` slot (also after a 503 at the cap). Sessions with a request in flight or an open GET stream are never idle. Expiry is done by a sweep task (interval min(ttl/4, 60) s, started and cancelled with the app lifespan) and lazily on a request for an idle session. The session is marked expiring first (requests get the standard unknown-session 404), the binding is removed only after the terminate succeeded (2xx/404), otherwise it is kept and retried at the next sweep. Requests for an expired id get the byte-identical unknown-session 404 for every token, so clients open a new session. Works in no-auth mode. SSE sessions end with their stream. mcp 1.26 keeps terminated transports in its session table, so the entry is dropped via one guarded `_server_instances.pop` (also on explicit owner DELETE).

#### Session binding hardening
- Every Streamable HTTP request without `mcp-session-id` (any method, any query) reserves a cap slot before the app runs (503 at the cap, no overshoot under concurrency) and any `mcp-session-id` in its response is bound and counted; a session whose creating response is not 2xx is terminated and released right away (retried by the sweeper on failure, also with TTL 0). Query `session_id` is only enforced on the SSE `/messages/` path. Requests naming several different session ids get the unknown-session 404.
- A 404 from the app no longer frees a binding or the mcp instance; only a confirmed terminate or an owner DELETE 2xx does. The Host used for the internal DELETE is only taken from requests answered other than 421/404 (default: first `LEXLINK_ALLOWED_HOSTS` entry). The SSE foreign-id 404 is byte-identical to mcp's (no content-type). Ended SSE streams are tombstoned (404 for every token). Failed terminates back off exponentially per session (sweep interval up to 15 min) with one warning line (no traceback, no session id). `mcp.server.streamable_http_manager`, `mcp.server.streamable_http` and `mcp.server.sse` loggers are raised so session ids stay out of logs.

#### Session binding
- New pure ASGI `SessionBindingMiddleware` (order Auth > Logging > RateLimit > SessionBinding > app): MCP sessions (Streamable HTTP `mcp-session-id`, SSE `session_id` from the `endpoint` event) are bound to the creating token. Another token gets the same 404 an unknown session gets and never reaches the app; owner DELETE / SSE close removes the binding. `LEXLINK_MAX_SESSIONS` (default 10000) caps bindings; at the cap new sessions get 503 rather than evicting (eviction would leave an unbound, usable session). No-auth mode shares one id, so binding is a no-op.

#### HTTP hardening follow-up
- Default logs no longer contain client-controlled strings: `tool_name` only for registered tools (else `<unknown>`), argument keys only if declared in the tool schema (others counted in `unknown_arg_keys`), `method` limited to known MCP methods. `create_app` passes tool names/schemas to `LoggingMiddleware`.
- `LEXLINK_LOG_BODIES` now drops oc/token/authorization-like keys recursively (dicts, lists, JSON inside `result` text).
- `uvicorn.run(..., proxy_headers=False)`; documented factory command uses `--no-proxy-headers` so `LEXLINK_TRUSTED_PROXIES` is the only X-Forwarded-For authority.
- `BearerAuthMiddleware` closes websocket scopes with 1008; only lifespan passes unchecked.
- `LEXLINK_ALLOWED_ORIGINS` without `LEXLINK_ALLOWED_HOSTS` raises at startup.
- Log retention runs at writer start; log files 0600, directory 0700; dropped log entries are counted and warned about at most once a minute.
- SSE transport logs a startup warning (per-request log status and concurrency cannot see results on the GET stream). Docs: DEPLOYMENT_GUIDE commands now include tokens, allowed hosts, Authorization and Host headers; OPERATIONS.md documents SSE limits, per-process oc override, http-only factory, unbound sessions, unlogged 401s, delayed 429s.

#### Security
- HTTP/SSE mode is now authenticated and fail-closed: `LEXLINK_AUTH_TOKENS="name:token,..."` (Bearer, constant-time compare, 401 + `WWW-Authenticate: Bearer`). Startup raises without tokens unless `LEXLINK_ALLOW_NO_AUTH=true` (PlayMCP no-auth registration only; loud warning). In HTTP mode the tool `oc` argument is ignored (`params.set_ignore_oc_override`); stdio is unchanged.
- New `http_security.py` (pure ASGI): per-token concurrency (`LEXLINK_MAX_CONCURRENCY`, default 8) and per-minute (`LEXLINK_RATE_LIMIT_PER_MIN`, default 60) limits with 429 + `Retry-After`; Host/Origin validation via `LEXLINK_ALLOWED_HOSTS`/`LEXLINK_ALLOWED_ORIGINS` (DNS-rebinding protection is never disabled).
- Traffic log is now privacy-preserving by default (argument key names only, no values/results/tokens; `LEXLINK_LOG_BODIES=true` opts in, OC redacted), written by a background thread, with `LEXLINK_LOG_RETENTION_DAYS` (default 30) retention. `X-Forwarded-For` is honoured only from `LEXLINK_TRUSTED_PROXIES`.

#### Changed
- Responses no longer cut content that was already fetched: `check_precedent_odds` (holding/summary excerpts, `key_factors`), `legal_resolver` (`article_text`, `citations`), `chain_full_research` (`representative_cases`), and `chain_law_system` (delegation tree entries and references) return everything by default. `compact_delegation_tree` has no entry cap unless `max_entries` is given. The one exception: `simplify_article` looks up at most 20 legal terms upstream (`extract_legal_terms` cap).
- `SLIM_RESPONSE=true` (also `1`, `yes`, `on`; case-insensitive) additionally keeps those compact caps (500 chars, top 10/3, 80 delegation entries), so PlayMCP output is unchanged. Fan-out caps and `display` limits are unaffected.
- `RawLoggingMiddleware` (BaseHTTPMiddleware that buffered whole responses, hung GET streams and dropped multi-value headers) replaced by pure ASGI `LoggingMiddleware` that forwards every message immediately. `log_mcp_call`/`log_raw` removed.
- Module-level `_server`/`_sse_app`/`app` removed; use `create_app(transport)` (single `create_server()` call; `uvicorn --factory lexlink.http_server:create_app`, single worker). `create_server(transport_security=None)` accepts FastMCP transport security settings.
- New Korean operations guide: `docs/OPERATIONS.md`.

#### Fixed
- `prec_service` / `detc_service` / `expc_service`: an upstream "일치하는 … 없습니다" answer (unknown id, or a case whose body the API does not provide, e.g. 국세법령정보시스템 precedents) now returns the new `NOT_FOUND` error instead of `status: ok`. Errors are never cached.
- `prec_service(sections="summary")` falls back to including 판례내용 (`sections: "summary_fallback"` plus a warning) when both 판시사항 and 판결요지 are empty.
- `prec_search` marks 국세법령정보시스템 items with `본문제공: "API 미제공"`; use `dat_src_nm="대법원"` to search only sources whose body is served.
- Section filtering (`sections="summary"`) no longer mutates the cached full response, which a later full call used to return stripped.
- `check_precedent_odds` skips cases without a body, moves on to the next candidate, and reports `unavailable_cases`.
- `legal_resolver` citations were always empty (coroutine run on FastMCP's already running event loop, error swallowed, and wrong citation keys read). It now runs the extraction in a worker thread, reads `target_law_name` / `type`, and reports failures in a `warnings` list (also carried by `chain_full_research`).
- `lawService.do` bodyless successes (blank body, `{}`, or only empty values) and "일치하는 법령이 없습니다" now return `NOT_FOUND` instead of `status: ok`. `article_amendment_diff` still tries the other MST when one version is missing.
- `elaw_service`, `admrul_search`, `admrul_service`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `lsDelegated_service` now send `type`, so the cache key includes the response format.
- `check_precedent_odds` no longer falls back to the search row number when 판례일련번호 is missing.
- Generic `NOT_FOUND` hint no longer builds a nonexistent `<target>_search` tool name.
- `article_citation` verifies `mst` / `law_name` / article with one `lawService` call (`target=law`, `MST`, `JO` incl. branch) when an OC is available: a name mismatch returns `VALIDATION_ERROR` naming both laws, a missing article returns `ARTICLE_NOT_FOUND`, upstream `NOT_FOUND` passes through (all with `success: false`). Without an OC it skips verification and adds a `warnings` entry. The lsiSeq cache is keyed by `(mst, law_name)`, no longer by `mst` alone.
- Ranked searches (over-fetch of 100 rows) returned an empty page 2+. When `page * display <= 100` the first 100 rows are fetched, ranked, and sliced for the requested page (also `elaw_search`); beyond that ranking is skipped, `page`/`display` are forwarded unchanged and `ranking_applied: false` is set.
- Zero-result searches (`run_search`, `elaw_search`) and empty `legal_resolver` / `check_precedent_odds` / `chain_dispute_prep` results keep `status: ok` but add `warning: "no_results"`, `message` and Korean `hints` (shorten query, use the formal name, `search=2` where the tool has it).
- `extract_outcome` checks specific outcomes first (일부인용, 일부기각, 파기환송 ...) and requires disposition context for 기각/각하/인용/취소, so "일부인용" is no longer "인용" and "원심판결 인용" / "인용하지" / "인용된" are `불명`. `check_precedent_odds` adds `outcome_note` (heuristic, not a citable result).
- `ordin_search` `knd` docstring: official codes are 30001 조례, 30002 규칙, 30003 훈령, 30004 예규, 30006 기타, 30010 고시, 30011 의회규칙 (source: open.law.go.kr ordinListGuide); 1/2/3 are not valid.
- `lawService.do` "일치하는 … 없습니다" is `NOT_FOUND` only when the whole body is that message (short real bodies quoting the phrase pass); query-keyed linkage targets get a "연계 정보가 없거나 검색어를 확인하세요" hint. `id_note` is dropped with `raw_content` under `SLIM_RESPONSE`. `legal_resolver` reports `success: false` citation extractions in `warnings`.
- Search cache: `ResponseCache.get`/`put` now return/store shallow copies, and `enforce_display` no longer edits its input. `cgm_expc_search` / `special_decc_search` pages 2+ were empty and a larger `display` after a smaller one still returned the smaller page.
- Paging across the 100-row ranking window: row order is the ranked first 100 upstream rows, then upstream rows 101+ in upstream order. Pages inside the window are ranked, pages beyond it fetch the covering size-100 upstream page(s) (`ranking_applied: false`), and straddling pages combine the ranked tail with the head of upstream page 2 (`ranking_applied: "partial"`, at most 2 upstream calls). No duplicate or missing rows for display 1-100, JSON and XML, `run_search` and `elaw_search`, both over-fetch keys; `ranked_data` is present on every page (also elaw beyond the window).
- `page < 1` or `display < 1` raise a validation error (was silently page 1 / odd slices); `display > 100` still clamps. `ranked_data.page` is the requested page. A page past the last result adds the hint `no_more_results`.
- `legal_resolver`, `check_precedent_odds`, `chain_dispute_prep`, `chain_full_research`: when every sub-search failed they return the upstream error code (or `UPSTREAM_ERROR` for mixed codes) with hints instead of `ok` + `no_results`; when only some failed they return `ok` with `warnings` naming the source and code and never claim `no_results`.
- `article_citation` name check also accepts the body's `법령명약칭` (or, on mismatch only, one `law_search` for the official name's `법령약칭명`), ignores `「」`, parenthetical suffixes such as `(법률)` and whitespace; 법/시행령/시행규칙 mismatches are still rejected.
- `article_citation`: only `NOT_FOUND`, `ARTICLE_NOT_FOUND` and a name mismatch block (all with `success: false`); TIMEOUT, API_NOT_SUBSCRIBED, UPSTREAM_ERROR etc. continue the scrape with a `warnings` entry naming the code.
- `extract_outcome` is position-based (earliest genuine disposition). Negations and modals (`하지 아니`, `할 수 없`, `될 수 없`, `될 것`, `되어야`, `사유가 없`) no longer count, bare 파기 needs a disposition ending, `파기하고 … 환송` within 40 characters is 파기환송, `일부를 인용/기각` is 일부인용/일부기각, and 취소 only counts as a disposition (not 취소소송 / 취소를 구하는). The unused `OUTCOME_KEYWORDS` constant was removed.
- `ordin_search` `rr_cls_cd` docstring now says 제개정 종류, matching the API reference.

#### Changed (behaviour)
- Search responses: in `ranked_data`, each row's `id` (upstream row number 1, 2, 3, not a key) is renamed to `rank`. `raw_content` is unchanged and, when kept, a new `id_note` explains that its `id` is a row number. Use 판례일련번호, 법령ID, 법령일련번호(MST) etc. for service calls.

#### Docs
- `docs/ISSUES.md` lists `*_service` tools without a size-control option; their docstrings now warn that responses can be large.
- Docs refresh and restructure: README/README_kr slimmed to overview and quick start; `docs/API_REFERENCE.md` now starts with the tool list generated from the server (55 tools) and has derived-tool, response-size and known-limitation sections; `docs/DEPLOYMENT_GUIDE.md` merged into `docs/OPERATIONS.md`; new `docs/DEVELOPMENT.md` and `docs/README.md` index; `ROADMAP.md`, `STATUS.md`, `ISSUES.md` and the audit checklist moved to `docs/archive/`; AGENTS.md and `.env.example` corrected (9 prompts, `law_as_of`, `.env` is not read by the server, removed unused `LOG_LEVEL`).

#### Security
- The OC credential is removed from upstream response bodies (e.g. `판례상세링크`), error messages, and debug/request logs (`has_oc` flag only); the `httpx` logger is limited to WARNING. The client's generic error path logs a redacted message plus traceback frames only. Encoded forms (`%3FOC%3D`, `&#38;OC=`, `\x26OC=`, `<OC>..</OC>`) are removed; redaction is linear-time and leaves legal text alone (`OC: "Office of Command"`, `"law" means`).
- OC removal is now structural (hidden `name="OC"` form fields, `OC = '...'` / `"OC":"..."` assignments) regardless of the value; short literal values are replaced only when quote/`=`/`&`-delimited. Tool error messages and logs are redacted too (no `logger.exception`).

---

### v2.2.0 (2026-10-25)

#### Fixed (P0)
- `cgm_expc_search` / `cgm_expc_service`: upstream target names were inverted (`cgmExpcMoel` → `moelCgmExpc`); all 39 ministries returned empty results.
- Knowledge-base linkage tools (`lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`) called `lawSearch.do` instead of `lawService.do` and returned nothing. They now take `query`/`mst` and an optional `trm_rlt_cd`; `jo_rlt_lstrm_search` requires `jo`.
- `ordinLsCon_search` used a nonexistent upstream target; redesigned with three modes: `query` → lnkOrd, `law_id` → lnkLsOrd, `org` → lnkOrg.

#### Fixed (P1)
- `special_decc_search` ignored `display` and returned 100 rows (~59KB).
- `jo` arguments now accept `35`, `35의5`, `제35조의5`, and `003505` (normalized to 6 digits); `ARTICLE_NOT_FOUND` is returned when the article is missing.
- Upstream HTML/empty-body responses now become structured errors (`API_NOT_SUBSCRIBED`, `EMPTY_RESPONSE`, `UPSTREAM_HTML_ERROR`) instead of `status: ok`.
- Resource `lexlink://law/{name}` now URL-decodes the name and resolves aliases (e.g. 자통법).
- `serverInfo.version` now reports LexLink's version instead of the mcp library version.
- Cache key now includes the response format (a JSON body was being served to XML requests).
- Ministry rename 기획재정부 → 재정경제부 (old name kept as alias). 재정경제부 and 국세청 have a list API only.

#### Planned in this release (being merged)
- `law_amendment_summary` builds revision history from `eflaw_search` filtered by 법령ID (previously it listed current laws from `law_search`).
- `simplify_article`, `article_amendment_diff`, `chain_amendment_track` extract full article text (항/호/목) via the new `article_text.py` instead of the heading only.
- The current (현행) version is preferred over the scheduled (시행예정) version.
- Precedent tools fall back to body-text search (`search=2`).
- The stale `date_to="20261231"` default is replaced by the computed end of the current year.

#### Infrastructure
- New modules: `agency_codes.py`, `linkage.py`, `article_text.py`.
- `tests/` is now tracked (122+ offline tests).
- Audit document: `docs/AUDIT_CHECKLIST_2026-10-25.md`.

---

### v2.1.0 (2026-03-30)

#### Added
- **Intelligent Caching** (`cache.py`): Per-tool TTL caching with semantic query normalization. Search results cached 1hr, articles 24hr, AI search 30min. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp).
- **Law Name Resolution** (`resolver.py`): Auto-resolves Korean law abbreviations (자통법→자본시장과 금융투자업에 관한 법률). 52 seed aliases + dynamic learning from API responses. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp).
- **Phase 9: Chain Tools** (5 new tools): Multi-step research workflows in one call. Inspired by [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp).
  - chain_full_research: Complete legal research (statutes + precedent analysis + interpretations)
  - chain_amendment_track: Revision history + article-level diff
  - chain_dispute_prep: All case law sources across 4 databases
  - chain_law_system: Full law hierarchy (delegation tree + admin rules + ordinances)
  - cache_stats: Cache and resolver performance monitoring

#### Infrastructure
- New module: `src/lexlink/cache.py` (~183 lines)
- New module: `src/lexlink/resolver.py` (~225 lines)
- Caching integrated into `run_search` and `run_service` helpers
- Law name resolution integrated into `run_search`
- Total tools: 54 (was 49)

---

### v2.0.0 - 2026-03-30

#### Added
- **Phase 7: Extended Legal Information (18 new tools)**
  - 자치법규 (Local Ordinances): ordin_search, ordin_service, ordinLsCon_search
  - 조약 (Treaties): trty_search, trty_service
  - 법령정보 지식베이스 (Knowledge Base): 7 legal term search and linkage tools (lstrm_ai_search, dlytrm_search, lstrm_rlt_search, dlytrm_rlt_search, lstrm_rlt_jo_search, jo_rlt_lstrm_search, ls_rlt_search)
  - 위원회 결정문 (Committee Decisions): committee_search/service (12 committees)
  - 중앙부처 1차 해석 (Ministry Interpretations): cgm_expc_search/service (39 ministries)
  - 특별행정심판 (Special Appeals): special_decc_search/service (4 tribunals)

#### Changed
- **Phase 6: Code Refactoring** — extracted shared helpers to `_helpers.py`, reducing server.py by ~38%
  - TOOL_ANNOTATIONS, handle_tool_error, run_search, run_service helpers
  - All 26 existing tools refactored as thin wrappers
- **Issue #10 resolved**: Upgraded mcp dependency to >=1.26.0

#### Infrastructure
- New module: `src/lexlink/_helpers.py` (~211 lines)
- New parameter mappings: eft_yd, conc_yd, nat_cd, sborg, ordin_fd
- Total tools: 44 (was 26)

---

### v1.5.2 - 2026-03-02
**Fix: slim_response() redesign — safety guard + no field stripping**

- **Bug fix (empty responses):** `slim_response()` unconditionally removed `raw_content` even when `ranked_data` was missing (ranking chain failure), leaving empty responses `{status, request_id, upstream_type}` on PlayMCP
- **Bug fix (aiSearch oversized):** `list_keys` whitelist didn't include `법령조문`, so field filtering silently skipped for `aiSearch` — responses remained ~46KB
- **Redesign:** Removed all field filtering and truncation logic. `slim_response()` now only removes `raw_content` (redundant raw XML) when `ranked_data` exists as replacement
  - **Rationale:** Real API testing showed search tools already return slim identifier-only data (~5-13KB). The old field-filtering approach was stripping useful fields (사건종류명, 상세링크, etc.) from already-small responses
  - Service tools (`_service`) don't set `ranked_data`, so `raw_content` is correctly preserved (full text is the response)
- **aiSearch default display:** Changed from 20 → 7 to stay under 20KB (조문내용 ~600 chars/item × 7 = ~15KB)
- **Verified:** All search tools under 20KB; service tools preserve full text

### v1.5.1 - 2026-03-01
**Fix: Anti-Bot Bypass & Embedded Law IDs**

- **Anti-bot bypass:**
  - law.go.kr returns HTML pages with JavaScript redirects (`window.location.assign()`) instead of API data from cloud server IPs (GCP, AWS)
  - Added `_follow_antibot()` method in `client.py` that detects and follows JS redirects (up to 3 hops)
  - Added `_parse_antibot_url()` parser handling two known JS patterns:
    - Pattern A (concat): `x={t:'...', h:'...', o:'...'}; return x.t+x.h+x.o`
    - Pattern B (substr): `x={o:'...', c:N}; z=M; return o.substr(0,c)+o.substr(c+z)`
  - Enabled `follow_redirects=True` on httpx client (anti-bot token URLs return HTTP 302)
- **Embedded law IDs in SERVER_INSTRUCTIONS:**
  - MCP resources (`lexlink://laws/frequently-used`) are not surfaced to LLMs by PlayMCP or Smithery proxy clients
  - Embedded 20 verified 법령ID mappings directly in `SERVER_INSTRUCTIONS` so LLMs can skip `eflaw_search` for common laws regardless of client resource support
  - All 20 IDs verified against live law.go.kr API (2026-03-01)
- **Impact:** API calls work through anti-bot protection; common law lookups work on all MCP clients

### v1.5.0 - 2026-02-28
**Refactor: Remove Smithery Dependency**

- **Removed:** `smithery` package dependency and 8 transitive dependencies (art, rich, typer, etc.)
- **Removed:** `config.py` (`LexLinkConfig` schema), `smithery.yaml`
- **Simplified:** OC resolution from 3-tier (tool arg > session config > env) to 2-tier (tool arg > env var)
- **Simplified:** `create_server()` no longer takes `session_config` parameter
- **Simplified:** `http_server.py` no longer unwraps `SmitheryFastMCP` wrapper
- **Added:** `stdio_server.py` entry point replacing `smithery.cli.start:main`
- **Updated:** `_get_client()` reads from `LEXLINK_BASE_URL` and `LEXLINK_TIMEOUT` env vars
- **Scripts:** Removed `dev`, `start`, `playground`; added `stdio` for stdio transport
- **Impact:** Cleaner dependency tree, simpler codebase (~80 lines removed across 26 tools)

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

### 미배포 (Unreleased)

#### 요청별 OC (HTTP 모드, 선택)
- `LEXLINK_ACCEPT_OC_HEADER=true`(기본 꺼짐): 유효한 `X-LexLink-OC`(`^[A-Za-z0-9._-]{1,64}$`) 헤더가 있는 `tools/call`은 그 호출의 모든 law.go.kr 요청(복합·chain 도구, 인용 검증 포함)에 그 OC를 쓰고, 없으면 서버 `OC`를 씁니다. 형식 오류는 `VALIDATION_ERROR`(값은 되돌려 주지 않음). 도구 인자 `oc`는 HTTP 모드에서 계속 무시되고 stdio는 그대로입니다. 값은 호출별 래퍼가 설정하는 contextvar로 전달됩니다(`oc_context.py`).
- 요청별 OC는 서버 OC와 같은 곳에서 마스킹됩니다(`redact_oc`가 서버 OC와 현재 요청 OC를 함께 마스킹: 요청 로그(`LOG_ARGUMENTS`/`LOG_BODIES` 포함), 오류·힌트, `OC=` 링크, 예외 문자열). `tools/call` 로그에 `oc_source`(`"header"`/`"server"`, 값은 기록하지 않음)가 추가됩니다. 캐시 키에 OC는 없고 오류는 캐시하지 않으며 성공 응답은 공개 데이터이므로 호출자 사이에 공유합니다. 사용자 OC는 그 사용자가 서버 IP를 open.law.go.kr에 등록한 경우에만 동작합니다.
- "사용자 정보 검증에 실패"는 새 오류 코드 `OC_AUTH_FAILED`(이전 `UPSTREAM_ERROR`)로 돌려주며 `oc_source`가 붙고, 헤더 OC일 때는 호출자 본인 OC에 서버 공인 IP 등록이 필요하다는 힌트를 줍니다.

#### HTTP 요청 로그
- 각 항목에 `user_agent`, `client_name` / `client_version`(세션 `initialize`의 `clientInfo`를 `mcp-session-id`별 제한된 LRU에 기억, DELETE 시 삭제; 길이 제한, 제어문자 제거), `tools/call`의 `upstream_calls`(그 호출이 law.go.kr로 보낸 요청 수, 캐시 적중이면 0)를 추가. 도구 호출 래퍼가 설정한 contextvar로 `client.py` / `citation.py`에서 세고, (세션 id, JSON-RPC id)로 로거에 넘김.
- `LEXLINK_LOG_ARGUMENTS=true`는 결과 본문 없이 인자 값만 기록(OC와 oc/token/authorization 키 제거). `LEXLINK_LOG_BODIES=true`는 기존대로 둘 다 기록. 기록되는 문자열에서 환경변수 `OC` 값 자체도 마스킹.
- 모든 `tools/call` 결과(오류 포함, HTTP·stdio 공통)에 같은 값이 `result._meta["lexlink/upstream_calls"]`로 실려, MCP 트래픽만 보는 게이트웨이가 읽을 수 있음. lowlevel `CallToolRequest` 핸들러를 감싸서 구현했고 `content`, `structuredContent`, `tools/list`는 그대로.

#### 상태 표기와 오류 분류
- `eflaw_search` `nw`는 1=연혁, 2=시행예정, 3=현행(실측). 문서와 오류 문구가 2=현행, 3=시행예정으로 적혀 있어 `nw="2"`가 시행예정 행을 현행으로 오인하게 했음. `admrul_search` / `ordin_search`의 `nw` 1=현행, 2=연혁은 재측정해 그대로(3은 1과 동일 동작).
- `article_amendment_diff`: 없는 MST(업스트림 `NOT_FOUND`)는 `NOT_FOUND` 오류. "조문 신설/삭제"는 두 버전이 모두 존재하고 조문이 실제로 한쪽에 없을 때만 보고. `chain_amendment_track`은 비교 실패를 `article_diff.error`와 함께 `warnings`에도 보고.
- `*_service`(`prec`, `detc`, `expc`, `decc`, `trty`, `cgm_expc`, `special_decc`): ok 응답이어도 본문 필드가 모두 비어 있으면(예: `detc_service` id 150756, 150770) `warning: "empty_body"`, `empty_fields`, `message`, `hints`를 반환.
- 업스트림은 잘못된 `ef_yd`, 없는 id, 잘못된 `type`에도 "미신청" 페이지를 반환. 잘못된 `type`은 모든 도구에서 호출 전에 `VALIDATION_ERROR`. lawService 호출에서 이 페이지가 오면 같은 target의 목록 조회를 한 번 확인: 목록도 미신청이면 `API_NOT_SUBSCRIBED`, 목록이 정상이면 `UPSTREAM_HTML_ERROR` + `may_be_not_subscribed: true`(원인 불명: 인자 거부 또는 본문 API만 미신청; 대안 안내 유지; 오류 경로에서만 요청 1회 추가), 응답이 없으면 '확인하지 못함' 힌트가 붙은 `API_NOT_SUBSCRIBED`.
- 빈 문자열·공백 `query` / `law_name` / `situation`은 업스트림 호출 전에 `VALIDATION_ERROR`(`chain_law_system`, `legal_resolver`, `check_precedent_odds` 외 11개; 기본값이 `*`인 목록 도구 16개는 명시적 빈 값을 거부).
- `lnkLsOrdJo_search`의 `jo`는 `20`, `"0020"`, `"제20조"`, `"20의2"`, `"002002"`를 받음(`"제11조"`는 `int()` 오류였음). `jo`의 가지번호는 `jobr`로 전달하고 충돌하면 오류.
- `article_citation`: 숫자가 아닌 `mst`는 `VALIDATION_ERROR`. 「신탁법」 제46조부터 제48조 같은 범위는 시작~끝 모든 조문을 나열(`range_text`, `range_note`; 범위 사이의 가지조문은 나열하지 않음). docstring 예시 수정(제35조의5; 제37조의2는 없음), Quick Reference에 "000300" = 제3조(제300조는 "030000") 명시.
- 숫자가 아닌 `id`/`mst`는 `VALIDATION_ERROR`(기존: 500계열 "not your fault" 힌트). `admrul_search`의 `date`는 정수/문자열을 받고 잘못된 값은 구조화된 `VALIDATION_ERROR`. HTTP 모드의 OC 누락 메시지가 더 이상 `oc` 인자 전달을 안내하지 않음(HTTP에서는 무시됨).
- 리뷰 후속: id는 30자리까지 허용(행정규칙일련번호는 13자리); `cgm_expc_service` / `special_decc_service`의 "일치하는 고용노동부 법령해석이 없습니다"는 JSON·XML 모두 `NOT_FOUND`; `empty_body`는 본문 필드가 실제로 있을 때만, `type` 대소문자(`xml`) 무관, 캐시·`sections="full"`에서도 유지, `type=HTML`은 검사하지 않음; `article_amendment_diff`는 두 MST의 법령ID가 다르면 신설/삭제 판단 없이 오류(개명은 같은 ID라 영향 없음); 범위 인용은 명시 반복과 중복 제거, 범위에서 펼친 조문의 `ref_id`는 `null`; 숫자가 아닌 `jobr`는 `VALIDATION_ERROR`.
#### 동작하지 않던 필터, 크기 제어, id 충돌 (#45)
- `prec_search` / `detc_search` / `decc_search` / `special_decc_search`의 `date`는 업스트림이 무시했습니다(prec `date=20240111`: 175,598건, 필터 없음). 이제 가이드의 범위 파라미터 `D~D`(`prnc_yd` / `ed_yd` / `rsl_yd`, 측정 52 / 31 / 24 / 3건)로 보내고 `filters_applied`로 표시합니다. 명시한 범위와 `date`가 다르면 `VALIDATION_ERROR`입니다. `dpa_yd`는 동작하지만 처분일자 필드가 거의 비어 있어(decc 35,255건 중 7건, ttSpecialDecc 0건) `dpa_yd_sparse` 경고가 붙습니다.
- `nb`: 쉼표 목록은 번호가 모두 있어도 0건이라 `VALIDATION_ERROR`(번호마다 따로 호출)이고, 표시형 `대법원-2025-두-34754`(업스트림 0건)는 `2025두34754`로 변환합니다. `detc_search`의 `nb`는 문자열입니다(`2022헌마1312`, 기존 `int`로는 입력 불가). 업스트림은 `query`가 있으면(`*` 포함, 38,739건) `nb`를 무시하므로 `detc_search`는 `nb`가 있으면 `query`를 보내지 않고, 실제 질의어와 `nb`를 함께 쓰면 오류입니다. 숫자만 넣은 `nb`는 부분일치라 `nb_substring` 경고가 붙습니다.
- `expc_search`의 `inq`는 질의기관코드(숫자, 예 1290000=국방부, 132건)만 받습니다. 이름은 관련 없는 3,805건을 돌려주므로 `VALIDATION_ERROR`입니다.
- 랭킹 필드: `prec_search`는 `판례명`, `expc_search`는 `사건명`으로 재정렬해 행에 없는 키라 no-op이었습니다. 이제 `사건명` / `안건명`입니다. 명시한 `sort`는 관련도로 다시 정렬하지 않습니다.
- prec/detc/expc/decc/special_decc의 100 초과 `display`는 100으로 제한하고 `display_capped` 경고를 붙입니다(기존에는 그대로 전송, expc `display=500`은 474KB). 알 수 없는 `sort` / `search` / `gana` / `cls`(숫자 재결구분코드) / `sections` 값은 `VALIDATION_ERROR`입니다(업스트림은 무시하거나 부분 건수를 반환, 예 `cls=zz` 716건). `*_service`는 `id`와 함께 `lm`을 보내지 않고(제목이 정확하지 않으면 유효한 id도 "일치하는 … 없습니다", 중립 `notes` 항목 `lm_not_sent`), 빈 `id`는 `VALIDATION_ERROR`입니다(가이드상 `ID` 필수, lm만 보내면 0바이트 응답).
- `drlaw_search`에 `display`(최대 100)와 `page`를 추가했습니다(업스트림 지원, 전체 981행). `parse_drlaw_html`은 법령의 두 번째 이후 조문 행(rowspan 셀 없음)을 잘못 읽어 `법령명 "4"`가 나오던 문제를 고쳤습니다.
- `lsDelegated_service`에 `jo`를 추가했습니다(JSON 본문 클라이언트 측 필터, `selection`에 법령의 조문 수와 일치 수): 건축법 3.69MB -> 5KB(제2조) / 61KB(제11조). 1MB 초과 본문은 `large_response` 경고를 붙입니다. 정책 `size`를 large에서 normal로 바꿨습니다(조문별 중앙값 2.3KB, 140개 중 5개가 100KB 초과, 최대 제80조 283KB).
- `ordin_service`: 모든 ok 응답에 `resolved` 블록(자치법규명, 지자체기관명, 자치법규ID, 일련번호)을 붙입니다. 같은 숫자가 한 자치법규의 자치법규ID이자 다른 자치법규의 일련번호일 수 있기 때문입니다(`id=2116749`는 정읍시립도서관 ... 시행규칙, `mst=2116749`는 서울특별시 건축 조례). 새 옵트인 `verify_id`(기본 false)는 `mst=<id>`를 추가로 조회(요청 2회)해 `id_collision` / `id_is_serial_number`를 중립적으로 알립니다(둘 다 사실이며 본문은 id를 그대로 조회한 결과). type=HTML이면 `id_check_undetermined`입니다. 정책 `upstream_calls`는 1 유지(`verify_id` 시 2). 키는 `ordin_search`에서 가져오세요.
- `aiSearch`: docstring 기본값을 바로잡았고(display 7, 20 아님), `page` > 1은 `page_ignored` 경고를 붙이며(업스트림이 1페이지를 다시 반환), 구어 `뺑소니`가 `relevance_unverified`를 일으키지 않습니다(짧은 별칭 목록 `COLLOQUIAL_LEGAL_TERMS`). `ls_rlt_search`는 정확한 법령명만 일치함을 문서화하고 0건 응답에 힌트를 붙입니다.
- 동기 도구 함수는 이제 워커 스레드에서 실행되고(`install_threaded_tool_calls`, `tool.fn`은 동기 그대로) `ResponseCache`에 락이 있습니다. Streamable HTTP에서 `lsDelegated_service(id=001823)`(4.4-5.1초) 동안 `cache_stats` 핑 6개를 측정: 수정 전 1.56-4.07초 대기, 수정 후 0.00-0.02초.
- 동작 변경: 키워드 질의에서 `sort` 없는 `prec_search`/`expc_search`는 이제 제목 관련도로 재정렬됩니다(이전 랭킹 필드가 맞지 않아 업스트림 순서, prec는 선고일자 내림차순이었음). 유지하려면 `sort`를 지정하세요. `nb`는 업스트림에서 접두 일치입니다(`2010헌바1`은 109건, 첫 행 2010헌바125): 정확하지 않은 행은 `nb_prefix_match`로 알리고 정확한 행이 1건이면 `ranked_data`에 그 1건만 남깁니다. 공백으로 이은 여러 번호는 `VALIDATION_ERROR`입니다. `*_service`의 `lm` 안내는 경고가 아닌 중립 `notes` 항목 `lm_not_sent`입니다. `aiSearch` page>1은 모순되는 `no_more_results` 힌트를 제거합니다. OPERATIONS에 워커 40개 한계와 취소된 호출 설명을 추가했습니다.
- 테스트: `tests/test_filters_and_size.py`(50개), 픽스처 `tests/fixtures/drlaw_page_rowspan_trimmed.html`.
#### 복합 도구: 단어 일치 표시, 표본 명시, 용어 해설 제거 (이슈 #43, #31)
- `legal_resolver` / `chain_full_research`: 구어체 질의에서 `aiSearch`가 무관한 법령을 앞세웁니다(측정: 교통사고 합의금 과실비율 -> 법인세법 시행령 제61조가 1순위). `applicable_laws`의 각 항목에 `matched_query_terms`(질의 단어 중 법령명·조문제목·본문에 있는 것), `low_relevance`(질의의 핵심 단어가 하나도 없음), `upstream_rank`를 추가했습니다. 이 표시는 참고용 글자 일치 검사(`relevance_basis: "term_overlap"`)로 양방향 오류가 있을 수 있으며, 순서를 바꾸거나 결과를 빼거나 판례·인용 조회를 건너뛰는 데 쓰지 않습니다(인용은 항상 upstream 1순위 조문에 대해 실행). `low_relevance:` 경고가 그렇게 알리고, 모든 조문이 표시되면 결과에 `low_relevance: true`, 어느 조문에도 없는 질의 단어는 `query_terms_not_found`로 나옵니다.
- 단어 비교: 질의 단어 끝의 어미·조사를 자르고(이혼하고 -> 이혼, 외도를 -> 외도; `해서`, `싶어요`, `돌려줘요`만 있는 경우는 무시), 3자 이상은 끝 글자를 뗀 어간으로도(양육권 ~ 양육, 퇴직금 ~ 퇴직급여), 4자 이상은 앞뒤 절반이 모두 있으면(공정이용 ~ "공정한 이용"), 집주인/세입자/남편/아내는 법령 용어로도 일치로 봅니다. 흔한 단어(재산, 청구, 보증금, 손해배상, 합의금)는 질의에 다른 단어가 있으면 그것만으로는 일치로 치지 않습니다.
- `legal_resolver` 판례: 먼저 질의의 핵심 단어로 검색(`search_basis: "situation_terms"`, 안 나오면 가장 긴 단어로 한 번 더, 3자 단어는 끝 글자를 뗌), 3건 미만이면 법령명으로 검색(`search_basis: "law_name"`). 각 판례의 사건명에 `matched_query_terms`가 붙고, 법령명으로만 찾아 겹치는 단어가 없으면 `relevance_unverified: true`와 경고가 나옵니다. 중복 id와 사건번호는 건너뜁니다(근로기준법 퇴직금에서 2024노3424가 두 번 나옴).
- `chain_full_research`는 `related_precedents`(전에는 집주인 보증금 사례의 판례가 0건), `precedent_analysis.sample`/`statistics_note`/`uncounted_cases`, 표시를 전달하며 `api_calls_made`가 모든 요청을 셉니다.
- `check_precedent_odds`: 질의의 핵심 단어가 사건명·판시사항·판결요지에 있는 판례만 `outcome_summary`/`key_factors`에 집계합니다(본문은 쓰지 않음: 본문 검색 결과는 구조상 모든 건에 단어가 있음). 나머지는 결과 없이 `uncounted_cases`에 두고 `representative_cases`에는 집계한 판례만 넣습니다. 사건명에 핵심 단어가 있는 판례를 먼저 조회하고, 본문 조회는 집계가 top_n건이 되거나 top_n+4회 시도하면 멈춥니다. 비교할 단어가 없는 질의(ㅋㅋㅋㅋㅋ)나 관련 판례가 없는 질의는 통계를 비우고 `low_relevance:` 경고, 집계 3건 미만은 `small_sample`, 모두 '불명'이면 `outcome_unclear:` 경고. `type="HTML"`은 본문을 JSON으로 조회합니다(전에는 모든 건이 불명). `sample`/`statistics_note`는 집계가 표본에 대한 것일 뿐 승소 확률이 아님을 밝히며 퍼센트는 없습니다. 실제 질의 측정: 이혼 위자료 5건, 재산분할 기여도 5건, 유책배우자 이혼청구 5건(+미집계 1), 양육권자 변경 3건(+2), 상간녀 위자료는 찾은 1건 중 집계 0건.
- #31 `check_precedent_odds(type="XML")`에서 `holding`/`summary`/`key_factors`가 비던 문제: `strip_html`이 `<![CDATA[...]]>`를 본문과 함께 지웠습니다. 이제 CDATA를 먼저 벗기고 실제 태그만 지우므로 `a < b ... c > d` 같은 글도 남습니다.
- `simplify_article`: 설명·서버 지침·출력이 본문을 쉬운 말로 바꾸지 않으며(`text_simplified: false`, `simplified_text`는 `original_text`와 같음) 용어 해설이 없다고 밝힙니다: `term_glossary`는 항상 비어 있고(`glossary_status: "withheld"`) 용어 조회를 하지 않습니다(요청 4~22회 -> 2회). 법령용어DB가 법적 의미가 다른 쌍(배우자 -> 반려자, 피한정후견인 -> 한정치산자, 재산관리인 -> 관재인, 위법행위 -> 불법행위, 사용자 -> 경영자, 채무자 -> 부채자)을 동의어로 표시하고 관계 표시로는 정상 쌍과 가려낼 수 없어 안전한 규칙이 없습니다. `extract_legal_terms`는 단어 경계 기준입니다(지방자, 특별자, 지방자치단체인이 나오지 않음).
- `chain_dispute_prep`는 검색 메타데이터만 돌려주며(판시사항·본문 없음) 설명과 `content_note`에 그렇게 적었습니다. 같은 판결(같은 사건번호·법원·일자, 여러 id; 측정: 개인정보 유출 과징금의 2024구합70753이 두 번)은 한 번만 나옵니다(`search_modes[...].duplicates_removed`). `title_matches_query`는 같은 핵심 단어 규칙을 쓰고, 일치하지 않는 행은 `low_relevance:` 경고로 셉니다.
- `SLIM_RESPONSE`의 `chain_law_system`: 20KB 가드가 항목을 22건으로 줄였는데 안내는 80건이라고 했습니다(건축법). `delegation_tree.note`, `truncated_notes`, `truncated_fields`, `truncated_note`가 실제 표시한 건수("337건 중 22건만 표시")를 말하고 `lsDelegated_service`를 안내합니다.
- 프롬프트 `get-law-article`, `get-article-with-citations`의 `article_number`가 int 또는 str로 저장소의 jo 형식(`"35의5"`, `"제35조의5"`, `"35-5"`, `"003505"`)을 받고 `article`과 `article_branch`를 안내합니다. `analyze-law-citations`도 같은 형식을 받습니다. bool과 가지번호 0(`"35의0"`)은 거부합니다.
- 정책 메타데이터 `upstream_calls`: check_precedent_odds 7 -> 11(측정 3~11), legal_resolver 8 -> 10(측정 5~9), chain_full_research 16 -> 20(측정 13~14), simplify_article 6 -> 3(측정 2).
- 테스트: `tests/test_composite_tools.py`(실제 질의 형태: 아이 양육권, 남편이 외도를 해서 이혼하고 싶어요, 집주인 보증금, 교통사고 합의금 과실비율, 이혼 위자료). 기존 테스트 3개를 새 출력에 맞게 고쳤습니다.
#### 판례 변경 확인, 헌재 단서, 부칙 상대일
- 새 도구 `prec_status`(총 68개, #35): 이후의 대법원 전원합의체 판결이 이 판례를 변경했는지 확인합니다. 업스트림에 인용 API가 없어, 사건번호를 따옴표 구문으로 본문 검색(`prec_search query='"94므1713"' search=2`, 최신순)해 이후의 전원합의체 판결만 남기고 각각을 읽어(`prec_service`, 최대 `max_scan` 기본 5, 최대 10) 출처 판결과 원문 그대로의 인용을 근거로 돌려줍니다: 변경하는 판결의 `참조판례`에서 해당 사건 뒤의 `(변경)`/`(폐기)` 표지(`explicit_marker`) 또는 사건번호를 지목하며 변경/폐기하는 문장(`explicit_sentence`). 방향이 중요합니다(옛 판결은 자신을 변경한 판결을 거의 인용하지 않음). 사건번호 없이 "견해에 배치되는 범위 내에서 변경한다"만 있으면 `leads`(`possible_overruling_needs_review`)일 뿐입니다. 상태: `overruled_found`, `possible_overruling_needs_review`, `no_overruling_found_in_searched_set`("변경되지 않음"이라고 하지 않으며 `searched_scope`에 행 수, 읽은/못 읽은 후보를 표시). 업스트림 호출: 대상 확인 1 + 인용 목록 1~3 + `max_scan`. 실제 호출로 측정: 알려진 변경 32건(180건의 전원합의체 판결 참조판례 `(변경)` 표지에서 추출 + 94므1713 -> 2013므2250, 88다카16867 -> 2018다248909)과 대조 20건(표지 없이 전원합의체에 인용만 된 판례): 31/32가 올바른 출처 판결과 함께 `overruled_found`, 1/32(88다카16867: 변경한 판결이 표지를 달지 않음)는 단서로만 나옴, 대조 20건 중 잘못된 `overruled_found` 0건(최종 수치는 아래 리뷰 수정 항목). 한계: 31건의 정답이 도구가 읽는 것과 같은 표지 필드에서 나왔으므로 표지 해석의 정확도가 아니라 후속 판결을 찾아내는 능력을 잰 것이고, 52회 실행 중 3회는 업스트림 타임아웃으로 오류로 보고되었습니다.
- 새 도구 `law_constitutional_check`(#37): 한 조문에 대한 헌재 위헌/헌법불합치 단서. `law_as_of`는 바꾸지 않습니다(`in_force` 불변, 주의 문구가 이 도구를 안내). 사건명에 법령명과 조문이 있는 결정을 찾고(`detc_search search=2`, 100건 1쪽) `detc_service` 본문을 최대 `max_scan` 기본 6(최대 10)건 읽어 주문을 분류합니다(위헌, 헌법불합치, 한정위헌, 합헌, 각하, 기각; 여러 조항의 주문은 문장 단위로 연결). 확인: 형법 제241조(2009헌바17 위헌 2015-02-26 발견, 2007헌가17 합헌), 민법 제847조(95헌가14 헌법불합치 1997-03-27, 2012헌바357 합헌 2015), 민법 제809조(95헌가6 헌법불합치 1997-07-16, 2018헌바115 주문의 제809조 합헌과 제815조 헌법불합치를 구분), 민법 제844조(2013헌마623 헌법불합치). 한계: 사건명에 조문이 없는 결정은 놓치고, 효력 시점(소급효, 잠정적용 시한)과 이후 개정은 계산하지 않습니다.
- `law_as_of`: 부칙 상대일("공포 후 6개월이 경과한 날부터 시행")을 부칙의 공포일자로 계산해 `partial_effect.article_scan.matches[].later_dates` / `computed_from_announcement`로 보고합니다(민법 제157조·제160조: 공포 다음 날부터 기산, 기간이 지난 다음 날이 경과한 날; 공포 2021-04-20 + 6개월 = 2021-10-21). 확인한 개정 16건(스토킹범죄의 처벌 등에 관한 법률 3, 가정폭력범죄의 처벌 등에 관한 특례법 13) 모두 계산값이 `시행일자`와 같았습니다. 계산할 수 없는 날짜(대통령령으로 정하는 날, 시행일 기준 상대일, 공포 후 N개월 이내, 공포일 없음)는 그 조문에 대해 `in_force: null`, reason `ARTICLE_STAGED_DATE_UNRESOLVED`입니다. 테스트는 2023-07-11 스토킹범죄의 처벌 등에 관한 법률 개정의 실제 부칙을 씁니다.
- 2013므3963·3970(2015-06-24) 조사(#36): 검색 버그가 아닙니다. 업스트림 판례 DB에 없는 판결입니다. `nb` 변형(단독, 결합, 쉼표, 공백, ㆍ), `nb=2013므`(11건, 해당 없음), 선고일 필터(2015-06-24 57건에 므 사건 없음), `lawSearch.do` 직접 호출이 모두 0건입니다. API_REFERENCE "알려진 한계"에 `nb`의 실제 동작(접두 일치, 결합사건은 첫 번호로만 색인)과 함께 기록했습니다.
- 위 세 도구의 리뷰 수정(PR #47). `prec_status`: `94므1713`, `1994므1713`, `대법원 1995. 5. 23. 선고 94므1713 판결` 모두 조회됩니다(색인은 2000년 이전 번호를 두 자리 연도로 적으므로 두 표기를 모두 시도). 새 상태 `case_not_found`(색인에 없는 번호: 결합사건의 뒤 번호 `94므1720`, `2099다99999`, `2013므3963` — 아무것도 말할 수 없음)와 `incomplete_search`(인용 목록이 잘림, `max_scan`을 넘은 후보, 본문 미제공 또는 200이지만 해석 불가한 본문; 후보 사건번호를 표시)를 추가해 `no_overruling_found_in_searched_set`은 모두 읽은 경우만 뜻합니다. statement는 증거 항목이 아니라 판결 수를 세고, `id=abc`는 `VALIDATION_ERROR`입니다. 반대의견·별개의견·보충의견 구간의 문장은 증거가 아니고, 한 문장에 두 사건이 있으면 변경 서술을 맞는 사건에만 연결합니다. `변경함이 상당하다`·`변경하는 것이 타당하다`·`폐기된다`는 180건 전원합의체에서 0회라 정밀도를 측정할 수 없어 단서로만 냅니다(명시적 표현은 같은 사건의 표지가 있는 경우가 137문장 중 135). 다수의견의 "더 이상 유지하기 어렵다"는 단서입니다(2018다248909가 88다카16867을 다루는 방식이며 80므60 -> 2015므8351도 이렇게 찾음). 재측정: 31/32가 올바른 출처와 함께 `overruled_found`, 88다카16867은 단서, 대조 20건에서 잘못된 `overruled_found` 0건(4건은 색인에 없어 `case_not_found`, 1건은 실제 변경(80므60)이라 단서로 보고).
- `law_constitutional_check`: 법령명을 `law_search`로 공식 명칭으로 확인합니다(`가족관계등록법` 같은 약칭 가능, 확인 못 하면 `VALIDATION_ERROR`, `민법`과 `민법 시행령` 구분). 후보는 사건명만이 아니라 따옴표 구문 본문 검색(`"형법 제270조"`)에서도 모으고, 다른 조문 이름의 사건이라도 주문이나 심판대상조문에 이 조문이 있으면 포함합니다. 주문은 조문별로 나누고(`제1조는 합헌이나 제2조는 위헌`), 조문에 연결하지 못한 위헌·헌법불합치 주문은 `needs_review`이며, 목록이 잘리거나 후보를 못 읽으면 `incomplete_search`입니다. 결과마다 "현행 조문은 결정 이후 개정되었을 수 있음"을 적습니다. 8개 조문 모두에서 찾았습니다(형법 제270조 2017헌바127, 민법 제1118조 2020헌가4, 민법 제815조 2018헌바115, 가족관계등록법 제14조 2015헌마924 + 형법 제241조, 민법 제847조·제809조·제844조); 사건명만 쓰던 이전 방식은 앞의 4개를 모두 놓쳤습니다. 기본 `max_scan` 8(최대 12), 정책 통상 10회·최대 14회.
- `law_as_of`: 계산할 수 없는 부칙 날짜는 선택된 버전 자신의 개정 부칙에서 나온 경우에만 `in_force`를 null로 만듭니다. 이전 개정의 `대법원규칙으로 정하는 날`은 그 뒤 개정이 이미 시행되었으므로 주의 문구(`partial_effect.earlier_amendment_unresolved_dates`)로만 남깁니다(가족관계의 등록 등에 관한 법률 제14조·제15조의 2016 부칙이 2018-01-01과 2026-01-01에서 null로 만들던 문제; 7개 법령 13개 질의에서 이 경로의 null 0건). `공포 후 1년 6개월이 경과한 날`, `…경과한 날이 속하는 달의 1일`, `…의 다음 날`은 계산하고, 그 밖의 이어지는 말, `공포 6개월 후`, `공포한 날부터 N개월이 경과한 날`(하루 차이 여부 미확인), `공포 후 N개월 이내`는 unresolved로 둡니다. `각 호` 아래에서 조문을 지목하는 항목 줄도 평가합니다.

#### 통합 리뷰 수정
- 단어 일치(`legal_resolver`, `chain_full_research`, `check_precedent_odds`, `chain_dispute_prep`): 질의 단어는 본문 단어의 시작에서만 일치하고 단어 중간은 일치로 치지 않습니다(측정: `legal_resolver("남편 외도")`가 국외도피 안의 외도로 재산국외도피 사건을 나열). 양육권~양육, 이혼하고~이혼, 퇴직금~퇴직급여는 그대로 일치합니다. 질의 단어 하나만 공유하는 형사 사건(사건번호 도/노/고합 등)은 `relevance_unverified`(`unverified_reason: criminal_case_single_term`; 2012도14788은 남편만 일치). 인용 단계가 `low_relevance`로 표시된 1순위 조문에서 실행되면 그 조문을 밝히는 `citations_low_relevance:` 경고가 붙습니다.
- `check_precedent_odds`: 핵심 단어가 둘 이상이면 사건명 또는 판시사항에 3글자 이상 단어가 있어야 집계합니다(판결요지만으로는 안 됨). `아이 양육권`이 부당해고구제재심판정취소, 미성년자입양허가, 친생자관계부존재확인을 더 이상 집계하지 않습니다. 사건명에 질의 단어가 있는 판례를 앞으로 재정렬하며(`sample.selection`에 명시), `statistics_note`는 관련성 검사가 거칠다고 밝힙니다. 실측 재확인: 이혼 위자료 5건 집계, 재산분할 기여도 5, 유책배우자 이혼청구 5(+미집계 1), 아이 양육권 1(+8), 양육권자 변경 1(+4; 이전 3+2, 빠진 2건은 사건명·판시사항에 양육권자가 없음).
- `law_constitutional_check`: 괄호 없는 옛 전문 형식(`주           문이 사건 ...이           유`, 예: 2009헌바106)을 읽습니다. 결과가 불명으로 남은 결정은 `needs_review`(`needs_review_reason`)가 되어, 사건명이 일치하는 결정을 읽지 못했는데 `no_adverse_decision_in_searched_set`이 나오는 일이 없습니다(민법 제1008조).
- `law_as_of`: 조문을 지목한 부칙 문장의 계산하지 못하는 공포 기준 표현("공포 후 1년 6개월이 되는 날", "공포 후 1년 6개월 후", "공포한 날이 속하는 달의 다음 달 1일", "공포일부터 1년이 경과한 날", "공포한 날이 속하는 해의 다음 해 1월 1일")을 무시하지 않고 `unresolved`로 보고합니다. "공포한 날부터", "공포한 날의 다음 날부터"는 계산합니다.
- `article_amendment_diff`: 두 MST의 법령ID가 다르면 조문이 양쪽에 있어도 `VALIDATION_ERROR`입니다(개명된 법령은 법령ID가 같아 그대로 동작).
- 프롬프트 `explain-legal-document`는 `dlytrm_rlt_search` / `lstrm_rlt_search`로 법률 용어/쉬운 말 표를 만들지 않고(그 연결에는 법적 의미가 다른 쌍이 있음) `lstrm_search` 정의를 쓰며, 검증된 쉬운 말 대응이 없다고 밝힙니다.
- `prec_status`: "변경하고 있는 것이 아니다"(및 변경한/하는 것이 아니다)는 부정 표현이라 근거가 아닙니다. `prec_search nb="1994므1713"`은 찾지 못합니다(2000년 이전 사건은 두 자리 연도로 색인). 0건이면 `94므1713` 형식을 쓰라는 `nb_year_form` 힌트가 붙습니다. `simplify_article` 정책의 evidence는 `primary`(조문 원문 반환)입니다.
- 운영 참고: #46은 도구 함수를 워커 스레드에서 실행하려고 mcp SDK의 `FuncMetadata.call_fn_with_arg_validation`을 몽키패치하므로 의존성을 `mcp>=1.26.0,<1.27`로 고정합니다. 올리기 전에 이 패치를 다시 확인하세요.

#### stdio 종료 정리
- 도구 호출이 실행 중일 때 stdio를 닫으면(#46 이후 도구 함수는 워커 스레드에서 실행) 이미 닫힌 스트림에 응답을 쓰려다 반환 코드 1과 `anyio.ClosedResourceError` 트레이스백으로 끝났습니다. `lexlink.stdio_server.main`은 닫힌 스트림 오류만으로 실패한 경우를 정상 연결 종료로 처리합니다(종료 코드 0, 트레이스백 없음). 다른 오류는 그대로 전파됩니다. 테스트: `tests/test_stdio_shutdown.py`.

#### 도구 정책 메타데이터
- 모든 도구의 `tools/list` 항목에 `_meta["lexlink/policy"]`(계약 v1)가 실립니다: `version`, `category`, `evidence`(primary / derived / heuristic / none), `size`(normal / large), `upstream_calls`(호출당 law.go.kr 요청 수 통상 최대), `may_expose_credential`, 선택 `notes`. 표는 `src/lexlink/tool_policy.py`의 `TOOL_POLICIES`이며 코드 분석과 라이브 측정으로 채웠습니다. 기존 `server.tool` 래퍼로 등록합니다(FastMCP 1.26 `meta=`). 항목이 없는 도구가 있으면 `create_server()`가 실패합니다. 도구 동작, 입력 스키마, annotations는 그대로입니다. 계약: `docs/API_REFERENCE.md`, 테스트: `tests/test_tool_policy.py`(stdio와 Streamable HTTP 실제 클라이언트).

#### 개정 이력, 신구법·3단 비교, 별표, 용어사전
- 새 도구 11개(총 66개). 업스트림이 잘못된 입력을 조용히 "0건"으로 응답하므로 호출 전에 검증합니다: `oldAndNew_search` / `oldAndNew_service`(신구법 대비), `thdCmp_search` / `thdCmp_service`(3단 비교, `knd` 1 인용조문 / 2 위임조문), `lsJoHstInf_search`(날짜·기간별 조문 개정 법령), `lsHstInf_search`(특정일 변경 법령), `delHst_search`(삭제 데이터 로그), `lsAbrv_search`(법령 약칭), `licbyl_search`(별표·서식 목록), `lstrm_search` / `lstrm_service`(법령용어 사전; `lstrm_ai_search`는 연관 용어 링크용이고 정의가 없음).
- 잘못된 날짜(`20261301`), 알 수 없는 코드(`sort`, `rr_cls_cd`, `dic_knd_cd`, `search`, `gana`, `delHst`/`licbyl`의 `knd`), `A0002` 형태(A0001 헌법, A0002 법률, A0007 대통령령, A0009 총리령, A0011 부령 ...)가 아닌 법령종류 `knd`, 필수 날짜·`knd` 누락은 `VALIDATION_ERROR`(날짜·id·mst·org·nb·anc_no·trm_seqs 같은 숫자 인자의 전각 숫자 ０-９만 ASCII로 정규화하고 그 밖의 문자는 바꾸지 않음; `knd`·`search`·`rr_cls_cd`·`sort` 같은 코드 인자는 정규화하지 않고 `VALIDATION_ERROR`; `gana`는 `ga na da ra ma ba sa ah ja cha ka ta pa ha etc`; 법령종류 전체 코드표는 비공개라 형태만 검증), 없는 id/mst는 `NOT_FOUND`, 0건은 `ok` + `warning: "no_results"` + 빈 리스트. 목록 행은 항상 리스트(업스트림은 1건이면 객체). `lsJoHstInf_search` / `lsHstInf_search` / `delHst_search`의 마지막 페이지 너머는 `warning: "page_out_of_range"`와 실제 전체 건수(업스트림은 `totalCnt: 0`).
- `thdCmp_service`는 `jo` 없이는 매우 큽니다(도구 응답 기준 인용조문/위임조문: 가사소송법 89/167KB, 가족관계의 등록 등에 관한 법률 204/251KB, 민법 610/592KB; `jo` 지정 시 1~9KB). 업스트림에 조문 인자가 없어 `jo`는 JSON 본문에서 해당 조문 행만 남기며(`selection`, `ARTICLE_NOT_FOUND`), 결과에 `anchor`(업스트림이 응답한 법령)를 싣고 시행령/시행규칙 id가 모법을 반환하면 경고합니다. `SLIM_RESPONSE` 가드가 적용되며 `jo`를 안내합니다.
- `lsAbrv_search`: 업스트림은 query/display/page를 무시하고 2,714건 전체(2.3MB)를 반환하므로 필터 없는 목록을 한 번(캐시 키 하나) 가져와 등록일 범위와 법령명·약칭 필터를 적용하고 직접 페이지를 나눕니다. 불완전한 목록은 오류이며 캐시하지 않습니다.
- `lstrm_service`는 `trm_seqs`(`lstrm_search`의 법령용어ID, 쉼표 목록 가능)를 받습니다(공백·슬래시·괄호가 있는 이름은 이름 조회가 NOT_FOUND). XML을 읽습니다. JSON은 항목을 병렬 배열로 합쳐 출처/용례가 어느 항목 것인지 알 수 없습니다. `licbyl_search`는 링크와 메타데이터만 반환하며 파일 내용은 가져오지 않습니다.
- `oldAndNew_service`는 `caution`을 반환합니다: 신구법 대비표는 법제처 편집본이라 법령 조문과 다를 수 있습니다(측정: 민법 제379조, mst 284415, 원본 DRF 구조문 "연 5분" vs 구 개정본 "연 5푼"). `eflaw_service` / `law_as_of`로 확인하세요. id와 mst가 다르면 경고합니다.
- 소득세법처럼 `knd=2` 법률조문 행의 `조내용`이 장·절 제목인 본문에서 `thdCmp_service`의 `jo`는 시행령·시행규칙 하위 조문이 붙은 행을 남기고 `selection.own_text_is_heading`/경고를 달아 돌려줍니다(거짓 ARTICLE_NOT_FOUND 아님). `totalCnt`가 행 수와 다른 `lsAbrv_search`는 행을 돌려주되 경고하고 캐시하지 않습니다. `;` 없는 `&reg` 같은 엔티티는 풀지 않습니다.
- 픽스처(실제 응답을 줄인 것; OC는 공개 샘플 `OC=test`로 치환)와 오프라인 테스트: `tests/test_history_compare.py`.

#### 남은 수정과 운영 확인 (#39)
- `thdCmp_service` `jo`: 조내용이 장·절 제목이면서 위임 하위 조문이 붙은 행은 같은 조번호의 실제 조문 행이 섞여 있어도 행마다 `own_text_is_heading: true`로 표시하고, `selection.heading_rows`에 개수를, `warning`에 반환 행 중 몇 행인지 알립니다. `selection.own_text_is_heading`은 모든 행이 제목일 때만 true입니다. 제목은 제목처럼 생겨야 합니다: 단위어(편/장/절/관)에서 토큰이 끝나고(`제3장 총칙`, `제2장의2 ...`), 짧은 제목이며 문장이 아니고, 조제목이 없어야 합니다. 그래서 "제3장에 따른 ..."으로 시작하는 조제목 있는 실제 조문은 더 이상 제목으로 취급되지 않습니다.
- `lsAbrv_search`: `upstream_total_mismatch`가 `no_results` / `page_out_of_range`를 덮어쓰지 않고 " / "로 함께 표시합니다. totalCnt가 없거나 숫자가 아니면 "None" 대신 "(missing or not a number)"로 표시합니다.
- `redact_oc`: 6자 미만 OC는 ASCII 경계의 `OC` 표지 바로 뒤(`OC g4c 는`, `oc: g4c`, `(OC=g4c,`) 또는 기존처럼 `=` / `&` 뒤에서만 치환하며 옆의 한글은 보존합니다. 그 밖의 형태는 치환하지 않습니다: 표지 없는 짧은 값(`legal g4c text`), `DOC g4c`, `OC g4cx`.
- `normalize_jo`와 `linkage.normalize_jo_code`, `*_yd` 날짜 범위 검사는 하나의 공통 함수를 씁니다: 전각 숫자는 ASCII로 바꿔 검사하고 업스트림에도 ASCII로 보냅니다(예: `eflaw_search` `ef_yd="２０２００１０１~２０２４１２３１"`). 아랍-인도 숫자 등 다른 유니코드 숫자는 거절하며 `ascii_digits`와 같은 정책입니다.
- (선택적 BOM 뒤) `{` 또는 `[`로 시작하지만 해석되지 않는 JSON 본문(대개 HTTP 200으로 중간에 끊긴 응답이며 `[공지] ...` 같은 텍스트나 지나치게 깊은 중첩 포함)은 `UPSTREAM_ERROR`("invalid JSON body")이며 캐시하지 않습니다. 이전에는 `ok`로 반환되고 캐시되었습니다.
- 보이는 텍스트가 "일치하는 … 없습니다"뿐인 `lawService` HTML 페이지(예: 없는 mst의 `oldAndNew_service` `type=HTML`)는 XML과 같이 `NOT_FOUND`입니다.
- oldAndNew, thdCmp, lsJoHstInf, lsHstInf, delHst, lsAbrv, licbyl, lstrm의 XML/HTML을 raw DRF와 실제로 비교: `raw_content`는 원본과 같고, 결과 링크 안의 `OC=...&amp;`만 마스킹으로 제거됩니다. 0건 응답은 `ok` + `no_results`(XML), `lsJoHstInf` / `delHst`는 JSON·XML만, `thdCmp_service`의 `jo`는 JSON만 지원합니다(호출 전 `VALIDATION_ERROR`).
- 확인만 하고 바꾸지 않은 것(docs/OPERATIONS.md 참고): `LEXLINK_MAX_SESSIONS`의 503, 위조 `X-Forwarded-For`에서의 속도 제한 키, `LEXLINK_LOG_BODIES` 내용, 로그 보존과 파일 권한, 업스트림 500 / 타임아웃 / 빈 본문.

#### 기준일 시점 조회 (hypeproof-legal #59)
- 새 도구 `law_as_of(law_name, as_of, article?, article_branch?, as_of_end?)`: D일에 시행 중이던 법령(또는 한 조문). 법령의 (MST, 시행일) 목록에서 시행일 <= D 중 가장 늦은 것을 골라 그 개정본을 `lawService target=eflaw`(MST + efYd)로 조회한다. MST, 시행일, 공포일, 조문, 현행과의 차이, 이후/시행예정/공포 후 미시행 버전, 기간 조회(`as_of_end`), 설명문을 반환. `in_force`는 true / false / null: false의 `reason`은 `BEFORE_FIRST_ENFORCEMENT`, `BEFORE_EARLIEST_AVAILABLE_VERSION`, `AFTER_REPEAL`(`폐지제정`은 폐지 아님); null은 `NOT_CURRENT_UPSTREAM`(현행/시행예정 행도 폐지 표시도 없는 법령). 동일 명칭의 구법(다른 법령ID)은 같은 계통(같은 법령구분명이고 법률/대통령령/헌법이거나 소관부처가 같음)일 때만 사용. 조문 시행을 늦추는 부칙은 `partial_effect.article_scan`에 인용. 업스트림 실패를 "없음"으로 보고하지 않는다. 도구 수 54 -> 55.
- `eflaw_search`에 선택 인자 `nw`(1=연혁, 2=시행예정, 3=현행) 추가(기본 동작 동일). `ef_yd`는 시행일 범위 필터임을 명시.
- `law_amendment_summary`에 `date_basis`("announced" 기본 = 공포일, "effective" = 시행일이며 `date_from` 당시 시행 중이던 개정본도 항상 포함) 추가. 날짜 인자와 `chain_amendment_track`에 스키마 설명 추가.
- `eflaw_service` / `eflaw_josub`: `mst` 없이 `ef_yd`만(id + ef_yd)은 `VALIDATION_ERROR`(upstream이 무시하거나 `{}` 반환). `mst` + `ef_yd`가 있으면 `id`는 제거(id가 있으면 upstream이 현재본 반환). `ef_yd`는 int/str 모두 허용.
- 서비스 도구의 `id` / `mst` / `ef_yd` 스키마 설명에서 `law_as_of`를 안내. `article="007602"`와 충돌하는 `article_branch`는 오류.

#### 이슈 수정 (#10-#20)
- #10 `law_amendment_summary` / `chain_amendment_track`이 개정 1건만 반환: eflaw LID 이력 조회에 `nw=1,2,3`을 보냄(민법 1건 -> 37건). 버전 조회 중 업스트림 실패는 "법령을 찾을 수 없습니다" 대신 오류로 반환.
- #11 `lm`을 업스트림 `LM`으로 전송(소문자는 매칭 안 됨). `law_service`, `eflaw_service`(`lm` 파라미터 추가), `elaw_service`는 `lm`만으로 조회 가능.
- #12 `article_citation`이 "같은 법"(및 "같은 법 시행령/시행규칙")을 가장 최근에 언급된 법령의 외부 인용으로 해석. "이 법"은 내부 유지. "100% 정확" 문구 완화.
- #13 `check_precedent_odds`가 주문만으로 결과 분류(`extract_order` / `classify_order` 추가), 주문 원문을 `order`로 반환. 라벨: 파기환송, 파기자판, 파기, 상고기각, 항소기각, 항고기각, 원판결변경, 일부인용, 인용, 기각, 각하, 취소, 무죄, 유죄, 공소기각, 불명. 승소율이 아님(`outcome_note`). `extract_outcome` 제거.
- #14 `eflaw_service`는 `mst` 사용 시 `ef_yd` 또는 `id` 필수. 없으면 오해를 부르는 API_NOT_SUBSCRIBED 대신 `VALIDATION_ERROR`로 즉시 실패.
- #15 `aiSearch`, `legal_resolver`, `chain_full_research`: 어떤 결과도 질의와 글자 bigram을 공유하지 않으면 `relevance_unverified` 경고 추가(어휘 기반 힌트일 뿐, 결과는 삭제하지 않음).
- #16 `chain_law_system`: `admin_rules` 스키마를 위임 조문 트리의 위임행정규칙 항목에서 만든 `{name, id, article}`로 변경, `linked_ordinances`는 `lnkLsOrd`(실제 자치법규)와 `linked_ordinances_total` 사용. 실패는 빈 목록 대신 `warnings`로 보고.
- #17 `SLIM_RESPONSE=true`를 `server.tool` 래퍼로 중앙 제어: 20,000바이트 초과 응답은 줄이고 `truncated` / `truncated_notes`로 표시. 기본 모드는 변경 없음.
- #18 `lstrm_ai_search`, `dlytrm_search`, `ls_rlt_search`, `lstrm_rlt_jo_search` 결과 없음 안내 추가. JSON `raw_content`를 요청 페이지의 행으로 축소(`prec_search` display=5: 47KB -> 1.6KB).
- #19 기타: `id_note`에서 자치법규ID / 일련번호 구분, `committee_service` 전부 "null" 본문은 `NOT_FOUND`, `simplify_article`은 올바른 `연계용어` 단계(동의어/상위어)로 용어를 매핑하며 본문은 변경하지 않음, `drlaw_search` 파싱 행 제공, `elaw_search` 마크업 제거, HTTP 디버그 로그에 OC 미노출.
- #20 `legal_resolver` 인용은 #7 이후 정상 동작을 확인, 회귀 테스트 추가(코드 변경 없음).

#### 유휴 세션 만료
- `LEXLINK_SESSION_IDLE_TTL_SEC`(기본 3600, `0`이면 끔): Streamable HTTP 세션이 해당 시간 동안 활동이 없으면 서버가 세션을 종료(내부 앱에 직접 DELETE)하고 바인딩을 제거해 `LEXLINK_MAX_SESSIONS` 슬롯을 반환(상한 503 이후에도 새 세션 허용). 처리 중인 요청이나 열린 GET 스트림이 있는 세션은 유휴가 아님. 스윕 태스크(간격 min(ttl/4, 60)초, 앱 lifespan과 함께 시작/취소)와 유휴 세션에 요청이 올 때의 지연 만료로 처리. 먼저 `expiring`으로 표시(그동안 요청은 표준 unknown-session 404)하고, 종료가 성공(2xx/404)한 뒤에만 바인딩을 제거하며 실패하면 유지하고 다음 스윕에서 재시도. 만료된 id는 모든 토큰(소유자 포함)에게 바이트 단위로 동일한 unknown-session 404이므로 클라이언트는 새 세션을 엽니다. 인증 없음 모드에서도 동작. SSE 세션은 스트림과 함께 종료. mcp 1.26은 종료된 transport를 세션 테이블에 남기므로 보호된 `_server_instances.pop` 한 곳에서 제거(소유자 DELETE 시에도).

#### 세션 바인딩 보강
- 세션 헤더 없는 모든 Streamable HTTP 요청(메서드/쿼리 무관)은 앱 호출 전에 상한 슬롯을 예약하고(상한 시 503, 동시 요청에도 초과 없음), 응답의 `mcp-session-id`는 항상 바인딩·집계합니다. 생성 응답이 2xx가 아니면 세션을 즉시 종료·해제하며 실패 시 스위퍼가 재시도합니다(TTL 0에서도). 쿼리 `session_id`는 SSE `/messages/` 경로에서만 검사합니다. 서로 다른 세션 id를 여러 개 보내면 unknown-session 404입니다.
- 앱의 404는 더 이상 바인딩/인스턴스를 해제하지 않으며, 종료 확인 또는 소유자 DELETE 2xx 이후에만 해제합니다. 내부 DELETE의 Host는 421/404가 아닌 응답을 받은 요청에서만 저장하고 기본값은 `LEXLINK_ALLOWED_HOSTS` 첫 항목입니다. SSE 타 토큰 404는 mcp와 바이트 단위로 동일합니다(content-type 없음). 종료된 SSE 스트림 id는 모든 토큰에 404. 종료 실패는 세션별 지수 백오프(스윕 간격~15분), 경고는 한 줄(트레이스백/세션 id 없음). 세션 id를 출력하는 mcp 로거 레벨을 올렸습니다.

#### 세션 바인딩
- 순수 ASGI `SessionBindingMiddleware` 추가(순서 Auth > Logging > RateLimit > SessionBinding > app): MCP 세션(Streamable HTTP `mcp-session-id`, SSE `endpoint` 이벤트의 `session_id`)을 만든 토큰에 묶음. 다른 토큰은 존재하지 않는 세션과 같은 404를 받고 앱까지 도달하지 못하며, 소유자 DELETE/SSE 종료 시 바인딩 제거. `LEXLINK_MAX_SESSIONS`(기본 10000) 상한에서는 오래된 항목을 쫓아내지 않고(바인딩 없는 세션이 생기므로) 새 세션을 503으로 거절. 인증 없음 모드는 모든 요청이 같은 id라 효과 없음.

#### HTTP 보강
- 기본 로그에 클라이언트가 제어하는 문자열이 남지 않음: 등록된 도구만 `tool_name`, 스키마에 선언된 인자 키만 기록(나머지는 `unknown_arg_keys` 개수), 알려진 MCP 메서드만 `method`.
- `LEXLINK_LOG_BODIES`가 oc/token/authorization 계열 키를 중첩 구조와 `result` 안에서도 제거.
- `uvicorn.run(..., proxy_headers=False)`, 팩토리 명령에 `--no-proxy-headers`. 웹소켓 스코프는 1008로 종료. `LEXLINK_ALLOWED_ORIGINS`만 설정하면 기동 실패.
- 로그 보존 정리를 기록 스레드 시작 시 실행, 파일 0600/디렉터리 0700, 버려진 로그 개수 집계 및 분당 1회 경고. SSE 전송 시작 경고 및 한계 문서화. DEPLOYMENT_GUIDE 명령에 토큰/호스트/Authorization/Host 헤더 반영.

#### 보안
- HTTP/SSE 모드에 인증 추가 및 fail-closed 적용: `LEXLINK_AUTH_TOKENS="이름:토큰,..."` (Bearer, 상수 시간 비교, 401 + `WWW-Authenticate: Bearer`). 토큰이 없으면 `LEXLINK_ALLOW_NO_AUTH=true`(PlayMCP 인증 없음 등록 전용, 강한 경고 로그)가 아닌 한 기동 시 오류. HTTP 모드에서는 도구의 `oc` 인자를 무시(`params.set_ignore_oc_override`)하며 stdio는 변경 없음.
- 신규 `http_security.py`(순수 ASGI): 토큰별 동시 요청(`LEXLINK_MAX_CONCURRENCY`, 기본 8) 및 분당(`LEXLINK_RATE_LIMIT_PER_MIN`, 기본 60) 제한(429 + `Retry-After`), `LEXLINK_ALLOWED_HOSTS`/`LEXLINK_ALLOWED_ORIGINS` 기반 Host/Origin 검증(DNS 리바인딩 보호는 끄지 않음).
- 트래픽 로그는 기본적으로 개인정보 최소화(인자 키 이름만 기록, 값/결과/토큰 없음; `LEXLINK_LOG_BODIES=true`로 선택 기록, OC 마스킹), 백그라운드 스레드로 기록, `LEXLINK_LOG_RETENTION_DAYS`(기본 30) 보존 정책 적용. `X-Forwarded-For`는 `LEXLINK_TRUSTED_PROXIES`의 피어에서만 신뢰.

#### 변경
- 이미 가져온 내용을 더 이상 자르지 않음: `check_precedent_odds`(판시사항·판결요지 발췌, `key_factors`), `legal_resolver`(`article_text`, `citations`), `chain_full_research`(`representative_cases`), `chain_law_system`(위임 트리 항목·참조)이 기본적으로 전체를 반환. `compact_delegation_tree`는 `max_entries`를 지정하지 않으면 항목 상한이 없음. 예외: `simplify_article`은 업스트림 조회를 최대 20개 법률 용어로 제한(`extract_legal_terms` 상한).
- `SLIM_RESPONSE=true`는 위 압축 상한(500자, 상위 10/3건, 위임 항목 80건)도 함께 유지하므로 PlayMCP 출력은 그대로. 팬아웃 상한과 `display` 제한은 영향 없음.
- 응답 전체를 버퍼링하고 GET 스트림을 멈추게 하며 다중 값 헤더를 잃던 `RawLoggingMiddleware`(BaseHTTPMiddleware)를 모든 메시지를 즉시 전달하는 순수 ASGI `LoggingMiddleware`로 교체. `log_mcp_call`/`log_raw` 제거.
- 모듈 수준 `_server`/`_sse_app`/`app` 제거. `create_app(transport)` 사용(`create_server()` 1회 호출, `uvicorn --factory lexlink.http_server:create_app`, 워커 1개). `create_server(transport_security=None)`가 FastMCP 전송 보안 설정을 받음.
- 한국어 운영 가이드 `docs/OPERATIONS.md` 추가.

#### 수정
- `prec_service` / `detc_service` / `expc_service`: 업스트림이 "일치하는 … 없습니다"로 답하는 경우(존재하지 않는 ID, 또는 국세법령정보시스템 판례처럼 API가 본문을 제공하지 않는 경우) `status: ok` 대신 새 `NOT_FOUND` 오류를 반환. 오류는 캐시되지 않음.
- `prec_service(sections="summary")`에서 판시사항·판결요지가 모두 비어 있으면 판례내용을 포함해 반환(`sections: "summary_fallback"` 및 경고).
- `prec_search`가 국세법령정보시스템 항목에 `본문제공: "API 미제공"`을 표시. `dat_src_nm="대법원"`으로 본문 제공 출처만 검색 가능.
- `sections="summary"` 필터링이 캐시된 전체 응답을 변형하여, 이후 전체 조회가 잘린 본문을 반환하던 문제 수정.
- `check_precedent_odds`가 본문이 없는 판례를 건너뛰고 다음 후보로 넘어가며 `unavailable_cases`를 보고.
- `legal_resolver`의 인용(citations)이 항상 비어 있던 문제 수정(이미 실행 중인 FastMCP 이벤트 루프에서 코루틴 실행 실패 + 오류 은폐 + 잘못된 인용 키 사용). 이제 작업 스레드에서 실행하고 `target_law_name` / `type` 키를 읽으며, 실패 시 `warnings` 목록으로 보고(`chain_full_research`도 전달).
- `lawService.do`의 본문 없는 성공 응답(빈 본문, `{}`, 값이 모두 빈 객체)과 "일치하는 법령이 없습니다"가 `status: ok` 대신 `NOT_FOUND`를 반환. `article_amendment_diff`는 한 버전이 없어도 다른 MST를 계속 조회.
- `elaw_service`, `admrul_search`, `admrul_service`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `lsDelegated_service`가 `type`을 전달하여 캐시 키에 응답 형식이 포함됨.
- `check_precedent_odds`가 판례일련번호가 없을 때 검색 행 번호를 대신 쓰지 않음.
- 일반 `NOT_FOUND` 안내가 존재하지 않는 `<target>_search` 도구 이름을 만들지 않음.
- `article_citation`: OC가 있으면 `lawService` 1회 호출(`target=law`, `MST`, 가지번호 포함 `JO`)로 `mst`/`law_name`/조문을 검증. 법령명 불일치는 두 법령명을 담은 `VALIDATION_ERROR`, 조문 없음은 `ARTICLE_NOT_FOUND`, 업스트림 `NOT_FOUND`는 그대로 전달(모두 `success: false`). OC가 없으면 검증을 건너뛰고 `warnings`에 안내. lsiSeq 캐시 키를 `mst` 단독에서 `(mst, law_name)`으로 변경.
- 순위화(100건 over-fetch) 검색에서 2페이지 이상이 비어 있던 문제 수정. `page * display <= 100`이면 상위 100건을 받아 순위화한 뒤 요청 페이지를 잘라 반환(`elaw_search` 포함). 초과하면 순위화를 건너뛰고 `page`/`display`를 그대로 전달하며 `ranking_applied: false` 표시.
- 결과 0건 검색(`run_search`, `elaw_search`)과 빈 `legal_resolver` / `check_precedent_odds` / `chain_dispute_prep` 결과는 `status: ok`를 유지하되 `warning: "no_results"`, `message`, 한국어 `hints`(검색어 축소, 정식 명칭, 해당 도구는 `search=2` 본문 검색)를 추가.
- `extract_outcome`이 일부인용·일부기각·파기환송 등 구체적 결과를 먼저 확인하고 기각/각하/인용/취소는 주문 맥락을 요구. "일부인용"이 "인용"으로, "원심판결 인용"/"인용하지"/"인용된"이 인용으로 잡히지 않고 `불명` 처리. `check_precedent_odds`에 `outcome_note`(휴리스틱이며 인용 가능한 결과 아님) 추가.
- `ordin_search` `knd` docstring 정정: 공식 코드는 30001 조례, 30002 규칙, 30003 훈령, 30004 예규, 30006 기타, 30010 고시, 30011 의회규칙(출처: open.law.go.kr ordinListGuide). 1/2/3은 유효하지 않음.

#### 변경 (동작)
- 검색 응답의 `ranked_data`에서 각 행의 `id`(키가 아닌 업스트림 행 번호 1, 2, 3)를 `rank`로 이름 변경. `raw_content`는 그대로이며, 유지되는 경우 새 `id_note`가 `id`가 행 번호임을 안내. service 호출에는 판례일련번호·법령ID·법령일련번호(MST) 등을 사용.

#### 문서
- `docs/ISSUES.md`에 크기 제어 옵션이 없는 `*_service` 도구를 정리하고, 해당 도구 docstring에 응답이 클 수 있다는 경고를 추가.
- 문서 정리 및 구조 개편: README/README_kr은 개요와 빠른 시작만 남김. `docs/API_REFERENCE.md`는 서버에서 생성한 도구 목록(55개)으로 시작하며 파생 도구, 응답 크기, 알려진 한계 절을 추가. `docs/DEPLOYMENT_GUIDE.md`를 `docs/OPERATIONS.md`로 통합. `docs/DEVELOPMENT.md`와 `docs/README.md`(목차) 신설. `ROADMAP.md`, `STATUS.md`, `ISSUES.md`, 점검 체크리스트는 `docs/archive/`로 이동. AGENTS.md와 `.env.example` 정정(프롬프트 9개, `law_as_of`, 서버는 `.env`를 읽지 않음, 사용하지 않는 `LOG_LEVEL` 제거).

#### 보안
- 업스트림 응답 본문(`판례상세링크` 등), 오류 메시지, 디버그/요청 로그에서 OC 인증값을 제거(로그에는 `has_oc` 플래그만 기록). `httpx` 로거는 WARNING 이상으로 제한.
- OC 제거를 값과 무관한 구조 기반으로 확장(숨김 `name="OC"` 폼 필드, `OC = '...'` / `"OC":"..."` 할당). 짧은 값은 따옴표/`=`/`&`로 구분된 경우만 치환. 도구 오류 메시지와 로그도 마스킹(`logger.exception` 제거).

---

### v2.2.0 (2026-10-25)

#### 수정 (P0)
- `cgm_expc_search` / `cgm_expc_service`: 업스트림 target 이름이 뒤집혀 있었음(`cgmExpcMoel` → `moelCgmExpc`). 39개 부처 전부 빈 결과를 반환하던 문제 수정.
- 지식베이스 연계 도구(`lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`)가 `lawService.do`가 아닌 `lawSearch.do`를 호출해 결과가 없던 문제 수정. 이제 `query`/`mst`와 선택 인자 `trm_rlt_cd`를 받으며, `jo_rlt_lstrm_search`는 `jo`가 필수.
- `ordinLsCon_search`가 존재하지 않는 target을 사용하던 문제 수정. `query`→lnkOrd, `law_id`→lnkLsOrd, `org`→lnkOrg 세 가지 모드로 재설계.

#### 수정 (P1)
- `special_decc_search`가 `display`를 무시하고 100건(약 59KB)을 반환하던 문제 수정.
- `jo` 인자가 `35`, `35의5`, `제35조의5`, `003505`를 모두 받아 6자리로 정규화. 조문이 없으면 `ARTICLE_NOT_FOUND` 반환.
- 업스트림 HTML/빈 본문 응답을 `status: ok`로 통과시키지 않고 구조화 오류(`API_NOT_SUBSCRIBED`, `EMPTY_RESPONSE`, `UPSTREAM_HTML_ERROR`)로 반환.
- 리소스 `lexlink://law/{name}`이 URL 디코딩과 약칭(자통법 등) 해석을 수행.
- `serverInfo.version`이 mcp 라이브러리 버전 대신 LexLink 버전을 표시.
- 캐시 키에 응답 형식을 포함(JSON 본문이 XML 요청에 반환되던 문제 수정).
- 부처명 기획재정부 → 재정경제부 변경(기존 이름은 별칭으로 유지). 재정경제부·국세청은 목록 API만 제공.

#### 이번 릴리스에 포함 예정 (병합 중)
- `law_amendment_summary`가 `law_search`의 현행 법령 목록 대신 법령ID로 필터링한 `eflaw_search` 결과로 개정 이력을 구성.
- `simplify_article`, `article_amendment_diff`, `chain_amendment_track`이 제목만이 아니라 신규 `article_text.py`로 항/호/목을 포함한 조문 전문을 추출.
- 시행예정 버전보다 현행 버전을 우선 선택.
- 판례 도구가 본문 검색(`search=2`)으로 폴백.
- 고정된 `date_to="20261231"` 기본값을 현재 연도 말일 계산값으로 교체.

#### 인프라
- 신규 모듈: `agency_codes.py`, `linkage.py`, `article_text.py`
- `tests/` 디렉터리 추적 시작(오프라인 테스트 122개 이상)
- 점검 문서: `docs/AUDIT_CHECKLIST_2026-10-25.md`

---

### v2.1.0 (2026-03-30)

#### 추가
- **지능형 캐싱** (`cache.py`): 의미론적 쿼리 정규화를 포함한 도구별 TTL 캐싱. 검색 결과 1시간, 조문 24시간, AI 검색 30분 캐싱. [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)에서 영감.
- **법령약칭 해석** (`resolver.py`): 한국 법령 약칭 자동 해석 (자통법→자본시장과 금융투자업에 관한 법률). 52개 기본 별칭 + API 응답으로부터 동적 학습. [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)에서 영감.
- **Phase 9: 체인 도구** (5개 신규 도구): 한 번의 호출로 다단계 조사 워크플로 실행. [korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)에서 영감.
  - chain_full_research: 완전한 법령 조사 (법령 + 판례 분석 + 해석례)
  - chain_amendment_track: 개정 이력 + 조문별 개정 비교
  - chain_dispute_prep: 4개 데이터베이스에서 모든 판례 조회
  - chain_law_system: 전체 법령 체계 (위임 체계 + 행정규칙 + 자치법규)
  - cache_stats: 캐시 및 법령약칭 해석기 성능 모니터링

#### 인프라
- 신규 모듈: `src/lexlink/cache.py` (~183줄)
- 신규 모듈: `src/lexlink/resolver.py` (~225줄)
- `run_search` 및 `run_service` 헬퍼에 캐싱 통합
- `run_search`에 법령약칭 해석 통합
- 총 도구 수: 54개 (기존 49개)

---

### v2.0.0 - 2026-03-30
**주요 릴리스: Phase 7 도구, JSON 기본 형식, sections 파라미터**

- 18개의 Phase 7 도구 추가 (자치법규, 조약, 법령정보 지식베이스, 위원회 결정문, 중앙부처 해석, 특별행정심판)
- JSON이 기본 응답 형식으로 변경 (기존: XML)
- 판례 서비스 도구에 `sections="summary"` 파라미터 추가
- 공통 로직을 `_helpers.py`로 리팩토링
- 총 도구 수: 44개 (기존 26개)

---

### v1.5.2 - 2026-03-02
**수정: slim_response() 재설계 — 안전 가드 + 필드 제거 폐지**

- **버그 수정 (빈 응답):** `slim_response()`가 `ranked_data` 없이도 `raw_content`를 무조건 제거하여, 랭킹 체인 실패 시 PlayMCP에서 빈 응답 `{status, request_id, upstream_type}` 반환
- **버그 수정 (aiSearch 과대):** `list_keys` 화이트리스트에 `법령조문` 누락, `aiSearch` 필드 필터링이 무시되어 응답 ~46KB 유지
- **재설계:** 모든 필드 필터링 및 트렁케이션 로직 제거. `slim_response()`는 이제 `ranked_data`가 존재할 때만 `raw_content`(중복 raw XML)를 제거
  - **근거:** 실제 API 테스트 결과 검색 도구는 이미 식별자 위주의 소형 데이터 반환 (~5-13KB). 기존 필드 필터링은 이미 작은 응답에서 유용한 필드(사건종류명, 상세링크 등)를 제거하고 있었음
  - 서비스 도구(`_service`)는 `ranked_data`를 설정하지 않으므로 `raw_content` 올바르게 보존 (본문 자체가 응답)
- **aiSearch 기본 display:** 20 → 7로 변경하여 20KB 이내 유지 (조문내용 ~600자/항목 × 7 = ~15KB)
- **검증:** 모든 검색 도구 20KB 미만; 서비스 도구는 전체 텍스트 보존

### v1.5.1 - 2026-03-01
**수정: 안티봇 우회 및 법령ID 내장**

- **안티봇 우회:**
  - law.go.kr가 클라우드 서버 IP(GCP, AWS 등)에서 API 데이터 대신 JavaScript 리다이렉트(`window.location.assign()`) HTML 페이지를 반환하는 문제
  - `client.py`에 JS 리다이렉트를 감지하고 따라가는 `_follow_antibot()` 메서드 추가 (최대 3홉)
  - 두 가지 알려진 JS 패턴을 처리하는 `_parse_antibot_url()` 파서 추가:
    - 패턴 A (문자열 결합): `x={t:'...', h:'...', o:'...'}; return x.t+x.h+x.o`
    - 패턴 B (부분 문자열): `x={o:'...', c:N}; z=M; return o.substr(0,c)+o.substr(c+z)`
  - httpx 클라이언트에 `follow_redirects=True` 활성화 (안티봇 토큰 URL이 HTTP 302 반환)
- **SERVER_INSTRUCTIONS에 법령ID 내장:**
  - MCP 리소스(`lexlink://laws/frequently-used`)가 PlayMCP, Smithery 프록시 클라이언트에서 LLM에 전달되지 않는 문제
  - 20개 검증된 법령ID 매핑을 `SERVER_INSTRUCTIONS`에 직접 내장하여 클라이언트 리소스 지원 여부와 무관하게 LLM이 주요 법령의 검색 단계를 건너뛸 수 있도록 함
  - 모든 20개 ID를 law.go.kr 실시간 API로 검증 (2026-03-01)
- **영향:** 안티봇 보호를 통과하여 API 호출 가능; 모든 MCP 클라이언트에서 주요 법령 조회 지원

### v1.5.0 - 2026-02-28
**리팩토링: Smithery 의존성 제거**

- **제거:** `smithery` 패키지 의존성 및 8개 전이 의존성 (art, rich, typer 등)
- **제거:** `config.py` (`LexLinkConfig` 스키마), `smithery.yaml`
- **단순화:** OC 해석 3단계 (도구 인자 > 세션 설정 > 환경변수) → 2단계 (도구 인자 > 환경변수)
- **단순화:** `create_server()`에서 `session_config` 매개변수 제거
- **단순화:** `http_server.py`에서 `SmitheryFastMCP` 래퍼 해제 불필요
- **추가:** `stdio_server.py` 진입점 (`smithery.cli.start:main` 대체)
- **업데이트:** `_get_client()`가 `LEXLINK_BASE_URL`, `LEXLINK_TIMEOUT` 환경변수 사용
- **스크립트:** `dev`, `start`, `playground` 제거; stdio 전송용 `stdio` 추가
- **영향:** 의존성 트리 정리, 코드베이스 단순화 (26개 도구에서 ~80줄 제거)

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
