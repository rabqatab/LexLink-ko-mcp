# LexLink API 레퍼런스

> **목적:** (1) LexLink 도구 목록과 인자, (2) 법제처 Open API 195종 카탈로그와 LexLink 도구의 대응.
> **Source:** https://open.law.go.kr/LSO/openApi/guideList.do (카탈로그는 2026-10-25 점검 기준)
> **도구 목록 기준:** v2.2.0 + CHANGELOG Unreleased, 서버에서 직접 생성 (아래 "LexLink 도구 목록")

목차: [도구 목록](#lexlink-도구-목록) / [공통 규칙](#공통-규칙) / [파생 도구](#lexlink-파생-도구) / [알려진 한계](#알려진-한계) / 1~16 업스트림 API 카탈로그 / Appendix A~D

---

## LexLink 도구 목록

도구 55개, 프롬프트 9개, 리소스 2개. 아래 표는 서버의 `list_tools()`에서 생성했습니다(필수 인자, 선택 인자와 기본값). 모든 도구는 선택 인자 `oc`를 받지만 HTTP 모드에서는 무시됩니다. 같은 모양으로 직접 확인하려면 [DEVELOPMENT.md](DEVELOPMENT.md#adding-a-tool)의 스니펫을 쓰세요.

### 법령 (Laws)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `eflaw_search` | query | display=20, page=1, type=JSON, sort, ef_yd, org, knd, nw |
| `law_search` | query | display=20, page=1, type=JSON, sort, date, org, knd |
| `eflaw_service` | - | id, mst, ef_yd, jo, chr_cls_cd, lm, type=JSON |
| `law_service` | - | id, mst, lm, ld, ln, jo, lang, type=JSON |
| `eflaw_josub` | - | id, mst, ef_yd, jo, hang, ho, mok, type=JSON |
| `law_josub` | - | id, mst, jo, hang, ho, mok, type=JSON |
| `law_as_of` | law_name, as_of | article, article_branch=0, as_of_end, type=JSON |
| `elaw_search` | - | query=*, display=20, page=1, type=JSON, sort, ef_yd, org, knd |
| `elaw_service` | - | id, mst, lm, ld, ln, type=JSON |

### 행정규칙 · 자치법규 · 연계 (Admin rules, ordinances, linkage)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `admrul_search` | - | query=*, display=20, page=1, type=JSON, nw=1, search=1, org, knd, date, prml_yd, mod_yd, sort |
| `admrul_service` | - | id, lid, lm, type=JSON |
| `ordin_search` | - | query=*, display=20, page=1, type=JSON, nw=1, search=1, sort, date, ef_yd, anc_yd, anc_no, org, sborg, knd, rr_cls_cd, ordin_fd, gana |
| `ordin_service` | - | id, mst, type=JSON |
| `ordinLsCon_search` | - | query, law_id, org, display=20, page=1, sort, type=JSON |
| `lnkLs_search` | - | query=*, display=20, page=1, type=JSON, sort |
| `lnkLsOrdJo_search` | - | query=*, display=20, page=1, type=JSON, knd, jo, jobr, sort |
| `lnkDep_search` | org | display=20, page=1, type=JSON, sort |
| `drlaw_search` | - | - |
| `lsDelegated_service` | - | id, mst, type=JSON |

### 판례 · 결정례 · 해석례 (Case law)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `prec_search` | - | query=*, display=20, page=1, type=JSON, search, sort, org, curt, jo, gana, date, prnc_yd, nb, dat_src_nm, pop_yn |
| `prec_service` | id | lm, sections, type=JSON |
| `detc_search` | - | query=*, display=20, page=1, type=JSON, search, gana, sort, date, ed_yd, nb, pop_yn |
| `detc_service` | id | lm, sections, type=JSON |
| `expc_search` | - | query=*, display=20, page=1, type=JSON, search=1, inq, rpl, gana, itmno, reg_yd, expl_yd, sort, pop_yn |
| `expc_service` | id | lm, sections, type=JSON |
| `decc_search` | - | query=*, display=20, page=1, type=JSON, search=1, cls, gana, date, dpa_yd, rsl_yd, sort, pop_yn |
| `decc_service` | id | lm, sections, type=JSON |
| `committee_search` | committee | query=*, display=20, page=1, type=JSON, search, sort, gana |
| `committee_service` | committee, id | type=JSON |
| `cgm_expc_search` | ministry | query=*, display=20, page=1, type=JSON, search, sort, gana |
| `cgm_expc_service` | ministry, id | type=JSON |
| `special_decc_search` | tribunal | query=*, display=20, page=1, type=JSON, search, sort, gana, cls, date, dpa_yd, rsl_yd |
| `special_decc_service` | tribunal, id | type=JSON |

### 조약 (Treaties)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `trty_search` | - | query=*, display=20, page=1, type=JSON, search, sort, gana, eft_yd, conc_yd, cls, nat_cd |
| `trty_service` | id | type=JSON |

### AI 검색 · 지식베이스 (AI search, knowledge base)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `aiSearch` | query | search=0, display=7, page=1, type=JSON |
| `aiRltLs_search` | query | search=0, type=JSON |
| `lstrm_ai_search` | - | query=*, display=20, page=1, type=JSON |
| `dlytrm_search` | - | query=*, display=20, page=1, type=JSON |
| `lstrm_rlt_search` | - | query, mst, trm_rlt_cd, type=JSON |
| `dlytrm_rlt_search` | - | query, mst, trm_rlt_cd, type=JSON |
| `lstrm_rlt_jo_search` | - | query, mst, type=JSON |
| `jo_rlt_lstrm_search` | jo | query, law_id, type=JSON |
| `ls_rlt_search` | - | query=*, display=20, page=1, type=JSON |

### 분석 도구 (Analysis)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `article_citation` | mst, law_name, article | article_branch=0 |
| `check_precedent_odds` | query | display=20, top_n=5, type=JSON |
| `legal_resolver` | situation | display=5, type=JSON |
| `simplify_article` | law_name, article | article_branch=0, type=JSON |
| `law_amendment_summary` | law_name | date_from=20100101, date_to, type=JSON, date_basis=announced |
| `article_amendment_diff` | mst_old, mst_new, article | article_branch=0, type=JSON |

### 체인 · 운영 (Chains, ops)

| Tool | 필수 인자 | 선택 인자 (기본값) |
|---|---|---|
| `chain_full_research` | query | display=5, type=JSON |
| `chain_amendment_track` | law_name | article=0, date_from=20200101, date_to, article_branch=0, type=JSON |
| `chain_dispute_prep` | query | display=5, type=JSON |
| `chain_law_system` | law_name | type=JSON |
| `cache_stats` | - | - |

프롬프트: `search-korean-law`, `get-law-article`, `get-article-with-citations`, `analyze-law-citations`, `search-admin-rules`, `tool-selection-guide`, `analyze-legal-situation`, `explain-legal-document`, `check-legal-precedent`.

리소스: `lexlink://laws/frequently-used`(정적), `lexlink://law/{name}`(템플릿; 예: `lexlink://law/자통법`).

### 업스트림 API와의 대응

| 구분 | 도구 수 | 비고 |
|---|---|---|
| 업스트림 API를 그대로 감싼 도구 | 43 | `committee_*`(위원회 12개), `cgm_expc_*`(부처 39개), `special_decc_*`(심판원 4개)는 인자로 대상을 고르는 도구 |
| LexLink 파생 도구 | 12 | `law_as_of`, `article_citation`, `check_precedent_odds`, `legal_resolver`, `simplify_article`, `law_amendment_summary`, `article_amendment_diff`, `chain_*` 4개, `cache_stats` |

업스트림 카탈로그 195종 중 이 도구들이 다루지 않는 API는 각 절에 `NOT IMPLEMENTED`로 표시했습니다.

> 모든 업스트림 target 이름·엔드포인트는 2026-10-25 점검에서 직접 호출로 재검증했습니다(점검 기록: [archive/AUDIT_CHECKLIST_2026-10-25.md](archive/AUDIT_CHECKLIST_2026-10-25.md)). 미구현 API 중 JSON 동작을 확인한 목록은 Appendix D를 보세요.

---

## Response Format Support

- JSON이 기본값입니다(`type="JSON"`, v2.0.0부터).
- `type="XML"`, `type="HTML"`도 선택할 수 있습니다(HTML은 일부 엔드포인트만).
- 캐시 키에 응답 형식이 포함됩니다.

---

## 공통 규칙

- 모든 엔드포인트는 **HTTP GET**
- request parameters의 OC parameter는 test 시 **your_oc**로 사용할 것
- **Response format:** Use `type=JSON` (default) - JSON is the default format as of v2.0.0; XML and HTML also supported
- **Base URL:** `http://www.law.go.kr/DRF/`
- **List APIs:** `lawSearch.do?target=<target>`
- **Content APIs:** `lawService.do?target=<target>`

---

## LexLink 파생 도구

업스트림 API 하나에 대응하지 않고 여러 호출이나 HTML 파싱으로 만든 도구입니다. 동작은 도구 설명과 CHANGELOG(Unreleased 포함)에 근거하며, 오프라인 테스트가 있습니다.

| 도구 | 동작 |
|---|---|
| `law_as_of` | 기준일 D에 시행 중이던 개정본을 골라 조문을 반환 (1.2.3절) |
| `law_amendment_summary` | 법령의 개정 이력. `date_from`/`date_to`는 기본으로 공포일 기준, `date_basis="effective"`면 시행일 기준(`date_from` 당시 시행 중이던 개정본 포함) |
| `article_amendment_diff` | 두 MST의 한 조문(항/호/목 포함)을 줄 단위로 비교 |
| `check_precedent_odds` | 판례의 주문만으로 결과를 분류한 분포. 라벨: 파기환송, 파기자판, 파기, 상고기각, 항소기각, 항고기각, 원판결변경, 일부인용, 인용, 기각, 각하, 취소, 무죄, 유죄, 공소기각, 불명. 승소율이 아님(`outcome_note`). 본문이 없는 판례는 건너뛰고 `unavailable_cases`로 보고 |
| `legal_resolver` | 상황 설명에서 법령, 판례, 해석례, 인용을 한 번에 조회. 인용 실패는 `warnings` |
| `simplify_article` | 조문(항/호/목 포함)과 법제처 용어 DB의 동의어 연결(`term_glossary`). 본문은 바꾸지 않음(`simplified_text`는 `original_text`와 같음). 용어 조회는 최대 20개 |
| `article_citation` | 15장 |
| `chain_full_research` | AI 검색, 법령, 판례 결과 분석, 해석례, 인용을 한 번에 |
| `chain_amendment_track` | 개정 이력과 조문 비교 |
| `chain_dispute_prep` | 판례, 헌재결정례, 법령해석례, 행정심판례를 한 번에 |
| `chain_law_system` | 법령 체계: 위임 트리, `admin_rules`(`{name, id, article}`, 위임행정규칙 항목에서 추출), `linked_ordinances`(`lnkLsOrd` 기준)와 `linked_ordinances_total`. 실패는 빈 목록 대신 `warnings` |
| `cache_stats` | 캐시와 resolver 통계 |

검색 결과가 0건이면 `status: ok`에 `warning: "no_results"`와 한국어 `hints`가 붙습니다. `aiSearch`, `legal_resolver`, `chain_full_research`는 질의와 겹치는 글자가 없으면 `relevance_unverified` 경고를 붙입니다(결과는 지우지 않음).

### 응답 크기

- 기본: 이미 가져온 내용은 자르지 않습니다. JSON `raw_content`는 요청한 페이지의 행만 담습니다.
- `SLIM_RESPONSE=true`: `ranked_data`가 있으면 `raw_content`를 지우고, 압축 상한(발췌 500자, 상위 10/3건, 위임 항목 80건)을 유지하며, 20,000바이트를 넘는 결과는 줄이고 `truncated`, `truncated_notes`(그리고 `truncated_fields`)로 표시합니다. 이 모드에서는 `sections="full"` 전문을 받을 수 없습니다.
- `jo`, `page`/`display`, `sections="summary"`로 나누어 조회하세요.

---

## 알려진 한계

2026-10-31 기준 코드에서 확인한 것만 적었습니다.

- **알 수 없는 인자는 무시됩니다.** 존재하지 않는 인자(`bogus_param`)를 넘겨도 오류가 없고 기본값으로 실행됩니다(`cache_stats(bogus_param=1)`로 확인). 인자 이름을 틀리면 조용히 다른 결과가 나올 수 있습니다.
- **일부 `*_service`에는 크기 제어 옵션이 없습니다**: `elaw_service`, `admrul_service`, `lsDelegated_service`, `ordin_service`, `trty_service`, `committee_service`, `cgm_expc_service`, `special_decc_service` (도구 설명에 같은 경고가 있음). 실제 크기는 법령마다 다릅니다. `eflaw_service`/`law_service`는 `jo` 없이 호출하면 법령 전체를 받습니다.
- **`article_citation`**: "제88조 내지 제93조" 같은 범위는 한 개의 HTML 링크라 첫 조문만 추출될 수 있습니다. 삭제되었거나 개정으로 사라진 조문을 가리키는 인용도 그대로 추출됩니다. 외부 법령은 이름 텍스트만 주므로 MST가 필요하면 `eflaw_search`를 따로 호출해야 합니다. "같은 법"과 조문 나열은 휴리스틱으로 해석합니다.
- **계정 단위 API 신청**: OC마다 신청한 API 범위가 다릅니다. 신청하지 않은 API는 `API_NOT_SUBSCRIBED` 오류가 됩니다(예: 현행법령 시행일 본문 `eflaw`는 `law_service`/`eflaw_josub`으로 대신할 수 있음).
- **서버 IP 등록**: law.go.kr은 OC와 호출 IP를 함께 검증합니다. 등록되지 않은 IP에서는 "사용자 정보 검증에 실패하였습니다" 오류가 납니다([OPERATIONS.md](OPERATIONS.md)).
- **`simplify_article`**: 본문을 쉬운 말로 바꾸지 않습니다. 법제처 용어 DB에 연결이 있는 용어만 `term_glossary`에 나오며, 연결이 법적 의미와 다를 수 있습니다.
- **`check_precedent_odds`**: 판례 주문의 분포이며 승소율이나 결과 예측이 아닙니다.
- **프롬프트/지침 준수는 모델마다 다릅니다.** 서버 지침(`SERVER_INSTRUCTIONS`)을 모든 LLM이 따르는 것은 아닙니다. 모델별 준수율 수치(과거 시험)는 [archive/ISSUES.md](archive/ISSUES.md)에 있으며 현재 버전에서 다시 측정하지 않았습니다.
- **HTTP 서버**: 단일 프로세스 전제, SSE 전송의 로깅/동시성 한계 등은 [OPERATIONS.md](OPERATIONS.md)의 "알려진 한계"를 보세요.

---

# 1. 법령 (Law) APIs — 26 APIs

## 1.1 본문 APIs (6 implemented)

### 1.1.1 현행법령(시행일) 목록 조회 — `eflaw_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=eflaw`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID (g4c@korea.kr → g4c) |
| target | string: eflaw(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태 HTML/XML/JSON (생략시 기본값: XML) |
| search | int | 검색범위 (기본: 1 법령명) 2: 본문검색 |
| query | string | 법령명에서 검색을 원하는 질의 |
| nw | int | 1: 연혁, 2: 시행예정, 3: 현행 (LID 지정 시 실측: nw=1은 연혁 행만, nw=2는 시행예정만, nw=3은 현행만; 도구에서 생략하면 현행만). 복수: nw=1,2,3. 주의: 현재 도구 설명(코드)은 2=현행, 3=시행예정으로 적혀 있어 실측과 다름 |
| LID | string | 법령ID (LID=830) |
| display | int | 검색된 결과 개수 (default=20, max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| sort | string | 정렬옵션 (기본: lasc). ldes/dasc/ddes/nasc/ndes/efasc/efdes |
| efYd | string | 시행일자 범위 검색 (20090101~20090130) |
| date | string | 공포일자 검색 |
| ancYd | string | 공포일자 범위 검색 (20090101~20090130) |
| ancNo | string | 공포번호 범위 검색 (306~400) |
| rrClsCd | string | 법령 제개정 종류 (300201-제정 등) |
| nb | int | 법령의 공포번호 검색 |
| org | string | 소관부처별 검색 (소관부처코드 제공) |
| knd | string | 법령종류 (코드제공) |
| gana | string | 사전식 검색 (ga,na,da…,etc) |
| popYn | string | 상세화면 팝업창 여부 (popYn=Y) |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&query=자동차관리법
```

**Response Fields:**
| 필드 | 값 | 설명 |
|------|-----|------|
| target | string | 검색서비스 대상 |
| 키워드 | string | 검색어 |
| section | string | 검색범위 |
| totalCnt | int | 검색건수 |
| page | int | 결과페이지번호 |
| law id | int | 결과 번호 |
| 법령일련번호 | int | 법령일련번호 |
| 현행연혁코드 | string | 현행연혁코드 |
| 법령명한글 | string | 법령명한글 |
| 법령약칭명 | string | 법령약칭명 |
| 법령ID | int | 법령ID |
| 공포일자 | int | 공포일자 |
| 공포번호 | int | 공포번호 |
| 제개정구분명 | string | 제개정구분명 |
| 소관부처코드 | string | 소관부처코드 |
| 소관부처명 | string | 소관부처명 |
| 법령구분명 | string | 법령구분명 |
| 시행일자 | int | 시행일자 |
| 법령상세링크 | string | 법령상세링크 |

---

### 1.1.2 현행법령(시행일) 본문 조회 — `eflaw_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=eflaw`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: eflaw(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char | 법령 ID (ID 또는 MST 중 하나는 반드시 입력) |
| MST | char | 법령 마스터 번호 (lsi_seq 값) |
| efYd | int(필수) | 법령의 시행일자 (ID 입력시에는 무시) |
| JO | int | 조번호 6자리숫자 (000200: 2조, 001002: 10조의2) |
| chrClsCd | char | 원문/한글 여부 (010202: 한글, 010201: 원문) |

> **LexLink `jo` 정규화 (v2.2.0):** `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`은 `35`, `35의5`, `제35조의5`, `35-5`, `003505`를 모두 받아 업스트림용 6자리 코드(`003505`)로 변환한다. 형식이 잘못되면 `VALIDATION_ERROR`, 해당 조문이 응답에 없으면 `ARTICLE_NOT_FOUND`.
> **`ef_yd` 규칙 (LexLink 도구, Unreleased):** `ef_yd`는 해당 MST 자신의 시행일을 고르는 개정본 선택자다. `mst` 없이 `id` + `ef_yd`만 주면 `VALIDATION_ERROR`(업스트림이 무시하거나 `{}`를 돌려줌), `mst` + `ef_yd`면 `id`는 보내지 않는다(`id`를 같이 보내면 업스트림이 현재본을 반환). `mst`를 쓸 때는 `ef_yd` 또는 `id`가 필요하다. 특정 날짜에 시행 중이던 본문은 `law_as_of`를 쓴다(1.2.3절). `ef_yd`는 정수/문자열 모두 허용. `lm`은 업스트림에 대문자 `LM`으로 전송되며 `lm`만으로 조회할 수 있다.
> **계정 신청 주의:** `eflaw` **본문**(`lawService.do?target=eflaw`)은 OC에 해당 API가 신청돼 있지 않으면 "미신청된 목록/본문에 대한 접근입니다" HTML을 반환한다 → LexLink는 `API_NOT_SUBSCRIBED` 오류로 변환하고 `law_service`/`eflaw_josub`을 대안으로 안내한다 (Appendix C).

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflaw&ID=1747&type=HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflaw&MST=166520&efYd=20151007&type=XML
```

---

### 1.1.3 현행법령(공포일) 목록 조회 — `law_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=law`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: law(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태 HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 법령명) 2: 본문검색 |
| query | string | 법령명에서 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20, max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| sort | string | 정렬옵션 (기본: lasc). ldes/dasc/ddes/nasc/ndes/efasc/efdes |
| date | int | 법령의 공포일자 검색 |
| efYd | string | 시행일자 범위 검색 |
| ancYd | string | 공포일자 범위 검색 |
| org | string | 소관부처별 검색 |
| knd | string | 법령종류 |
| gana | string | 사전식 검색 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&query=자동차관리법
```

---

### 1.1.4 현행법령(공포일) 본문 조회 — `law_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=law`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: law(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char | 법령 ID (ID 또는 MST 중 하나는 반드시 입력) |
| MST | char | 법령 마스터 번호 (lsi_seq 값) |
| LM | string | 법령의 법령명 |
| LD | int | 법령의 공포일자 |
| LN | int | 법령의 공포번호 |
| JO | int | 조번호 6자리숫자 |
| LANG | char | 원문/한글 여부 (KO: 한글, ORI: 원문) |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&ID=009682&type=HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&MST=261457&type=XML
```

---

### 1.1.5 법령 연혁 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lsHistory`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lsHistory(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태 HTML |
| query | string | 법령명에서 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20 max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| sort | string | 정렬옵션 (기본: lasc) |
| efYd | string | 시행일자 범위 검색 (20090101~20090130) |
| date | string | 공포일자 검색 |
| ancYd | string | 공포일자 범위 검색 |
| ancNo | string | 공포번호 범위 검색 |
| rrClsCd | string | 법령 제개정 종류 |
| org | string | 소관부처별 검색 |
| knd | string | 법령종류 |
| lsChapNo | string | 법령분류 (01-제1편 ... 44-제44편) |
| gana | string | 사전식 검색 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lsHistory&type=HTML&query=자동차관리법
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lsHistory&type=HTML&org=1741000
```

---

### 1.1.6 법령 연혁 본문 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lsHistory`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lsHistory(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML |
| ID | char | 법령 ID (ID 또는 MST 중 하나는 반드시 입력) |
| MST | char | 법령 마스터 번호 |
| LM | string | 법령의 법령명 |
| LD | int | 법령의 공포일자 |
| LN | int | 법령의 공포번호 |
| chrClsCd | char | 원문/한글 여부 (010202: 한글, 010201: 원문) |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=lsHistory&MST=9094&type=HTML
```

---

## 1.2 조항호목 APIs (2 implemented)

### 1.2.1 현행법령(시행일) 조항호목 조회 — `eflaw_josub` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=eflawjosub`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: eflawjosub(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char | 법령 ID (ID 또는 MST 중 하나는 반드시 입력) |
| MST | char | 법령 마스터 번호 |
| efYd | int(필수) | 법령의 시행일자 |
| JO | char(필수) | 조 번호 6자리 (000200: 제2조, 001002: 제10조의2) |
| HANG | char | 항 번호 6자리 (000200: 제2항) |
| HO | char | 호 번호 6자리 |
| MOK | char | 목 한자리 문자 (가,나,다,라…) UTF-8 인코딩 필요 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflawjosub&type=XML&MST=193412&efYd=20171019&JO=000300&HANG=000100&HO=000200&MOK=다
```

---

### 1.2.2 현행법령(공포일) 조항호목 조회 — `law_josub` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lawjosub`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lawjosub(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char | 법령 ID |
| MST | char | 법령 마스터 번호 |
| JO | char(필수) | 조 번호 6자리 |
| HANG | char | 항 번호 6자리 |
| HO | char | 호 번호 6자리 |
| MOK | char | 목 한자리 문자 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=lawjosub&type=XML&ID=001823&JO=000300&HANG=000100&HO=000200&MOK=다
```

---

## 1.2.3 기준일 시점 조회 — `law_as_of` ✅ IMPLEMENTED (LexLink 파생 도구)

법제처 DRF에는 "D일에 시행 중이던 법령" 조회가 없다. `eflaw_search`의 `ef_yd`는 시행일 범위 필터, `eflaw_service`/`eflaw_josub`의
`ef_yd`는 해당 MST 자신의 시행일을 지정하는 개정본 선택자이다. `law_as_of(law_name, as_of, article?, article_branch?, as_of_end?)`는
`lawSearch target=eflaw`(LID, nw=1,2,3)로 (MST, 시행일) 목록을 만들고 시행일 <= D 중 가장 늦은 것을 골라
`lawService target=eflaw`(MST + efYd)로 그 개정본의 조문을 가져온다.

| `in_force` | `reason` | 의미 |
|---|---|---|
| `true` | - | 기준일에 시행 중인 개정본(MST, 시행일, 공포일, 조문). 부칙의 조문별 시행일은 `partial_effect.article_scan`에 인용 |
| `false` | `BEFORE_FIRST_ENFORCEMENT` | 최초 시행 전 (동일 명칭 다른 법령ID가 없을 때만) |
| `false` | `BEFORE_EARLIEST_AVAILABLE_VERSION` | 조회된 연혁 이전: 시행 여부 확인 불가 (동일 명칭 법령ID 존재, 연혁 누락, 조회 실패 등) |
| `false` | `AFTER_REPEAL` | 폐지(`폐지`/`타법폐지`/`일괄폐지`) 이후. `폐지제정`은 폐지가 아님 |
| `null` | `NOT_CURRENT_UPSTREAM` | 업스트림에 현행/시행예정 버전이 없고 폐지 표시도 없는 법령(한시법 종료 등)의 마지막 버전 이후: 시행 중이었는지 알 수 없음 |

오류는 `status: error` + `error_code` (VALIDATION_ERROR, ARTICLE_NOT_FOUND, 업스트림 코드). 업스트림 실패는 "없음"으로 보고하지 않는다.
동일 명칭의 구법(다른 법령ID)은 법령구분이 같고 (법률/대통령령/헌법이거나 소관부처가 같을 때)에만 대체한다.

---

## 1.3 영문법령 APIs (2 implemented)

### 1.3.1 영문법령 목록 조회 — `elaw_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=elaw`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: elaw(필수) | 서비스 대상 |
| type | char | 출력 형태 HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 법령명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 (default=*) |
| display | int | 검색된 결과 개수 (default=20, max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| sort | string | 정렬옵션 |
| date | int | 공포일자 검색 |
| efYd | string | 시행일자 범위 검색 |
| org | string | 소관부처별 검색 |
| knd | string | 법령종류 |
| gana | string | 사전식 검색 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=XML&query=insurance
```

---

### 1.3.2 영문법령 본문 조회 — `elaw_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=elaw`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: elaw(필수) | 서비스 대상 |
| type | char | 출력 형태: HTML/XML/JSON |
| ID | char | 법령 ID |
| MST | char | 법령 마스터 번호 |
| LM | string | 법령명 |
| LD | int | 공포일자 |
| LN | int | 공포번호 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=elaw&ID=000744&type=HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=elaw&MST=127280&type=XML
```

---

## 1.4 이력 APIs (3 not implemented)

### 1.4.1 법령 변경이력 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lsHstInf`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lsHstInf(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태 HTML/XML/JSON |
| regDt | int(필수) | 법령 변경일 검색 (20150101) |
| org | string | 소관부처별 검색 |
| display | int | 검색된 결과 개수 (default=20 max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?target=lsHstInf&OC=test&regDt=20170726&type=HTML
http://www.law.go.kr/DRF/lawSearch.do?target=lsHstInf&OC=test&regDt=20170726&type=XML
```

**Response Fields:**
| 필드 | 값 | 설명 |
|------|-----|------|
| target | string | 검색서비스 대상 |
| totalCnt | int | 검색건수 |
| page | int | 현재 페이지번호 |
| law id | int | 검색 결과 순번 |
| 법령일련번호 | int | 법령일련번호 |
| 현행연혁코드 | string | 현행연혁코드 |
| 법령명한글 | string | 법령명한글 |
| 법령ID | int | 법령ID |
| 공포일자 | int | 공포일자 |
| 공포번호 | int | 공포번호 |
| 제개정구분명 | string | 제개정구분명 |
| 소관부처코드 | string | 소관부처코드 |
| 소관부처명 | string | 소관부처명 |
| 법령구분명 | string | 법령구분명 |
| 시행일자 | int | 시행일자 |
| 자법타법여부 | string | 자법타법여부 |
| 법령상세링크 | string | 법령상세링크 |

---

### 1.4.2 일자별 조문 개정 이력 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=dayjoRvs`

---

### 1.4.3 조문별 변경 이력 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=joChg`

---

## 1.5 연계 APIs (5 implemented)

### 1.5.1 법령 자치법규 연계 목록 조회 — `lnkLs_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkLs`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lnkLs(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| query | string | 법령명에서 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20, max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| sort | string | 정렬옵션 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLs&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLs&type=XML&query=자동차관리법
```

---

### 1.5.2 연계 법령별 조례 조문 목록 조회 — `lnkLsOrdJo_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkLsOrdJo`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lnkLsOrdJo(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| query | string | 법령명에서 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 |
| page | int | 검색 결과 페이지 |
| sort | string | 정렬옵션 |
| knd | string | 법령종류 (코드제공) |
| JO | int | 조번호 4자리숫자 (0023: 23조) |
| JOBR | int | 조가지번호 2자리숫자 (02: 2) |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=XML&knd=002118&JO=0020
```

---

### 1.5.3 연계 법령 소관부처별 목록 조회 — `lnkDep_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkDep`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lnkDep(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| display | int | 검색된 결과 개수 |
| page | int | 검색 결과 페이지 |
| org | string(필수) | 소관부처별 검색 |
| sort | string | 정렬옵션 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkDep&org=1400000&type=XML
```

---

### 1.5.4 법령-자치법규 연계현황 조회 — `drlaw_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=drlaw`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: drlaw(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: **HTML만 지원** |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=drlaw&type=HTML
```

---

### 1.5.5 위임법령 조회 — `lsDelegated_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lsDelegated`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: lsDelegated(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: XML/JSON (**HTML 미지원**) |
| ID | char | 법령 ID |
| MST | char | 법령 마스터 번호 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=lsDelegated&type=XML&ID=000900
```

---

## 1.6 부가서비스 APIs (8 not implemented)

### 1.6.1 법령 체계도 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=stmd`

### 1.6.2 법령 체계도 본문 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=stmd`

### 1.6.3 신구법 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=oldAndNew`

### 1.6.4 신구법 본문 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=oldAndNew`

### 1.6.5 3단 비교 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=thdCmp`

### 1.6.6 3단 비교 본문 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=thdCmp`

### 1.6.7 법률명 약칭 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lsAbrv`

### 1.6.8 삭제 데이터 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=datDelHst`

### 1.6.9 한눈보기 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=oneView`

### 1.6.10 한눈보기 본문 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=oneView`

---

# 2. 행정규칙 (Administrative Rules) APIs — 4 APIs

## 2.1 행정규칙 목록 조회 — `admrul_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=admrul`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: admrul(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| nw | int | (1: 현행, 2: 연혁, 기본값: 현행) |
| search | int | 검색범위 (기본: 1 행정규칙명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20, max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| org | string | 소관부처별 검색 |
| knd | string | 행정규칙 종류별 (1=훈령/2=예규/3=고시/4=공고/5=지침/6=기타) |
| gana | string | 사전식 검색 |
| sort | string | 정렬옵션 |
| date | int | 발령일자 |
| prmlYd | string | 발령일자 기간검색 |
| modYd | string | 수정일자 기간검색 |
| nb | int | 발령번호 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=admrul&query=학교&type=HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=admrul&date=20250501&type=XML
```

---

## 2.2 행정규칙 본문 조회 — `admrul_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=admrul`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: admrul(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char | 행정규칙 일련번호 |
| LID | char | 행정규칙 ID |
| LM | string | 행정규칙명 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=admrul&ID=62505&type=HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=admrul&ID=10000005747&type=XML
```

---

## 2.3 행정규칙 신구법 비교 목록 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=admrulOldAndNew`

## 2.4 행정규칙 신구법 비교 본문 조회 — NOT IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=admrulOldAndNew`

---

# 3. 자치법규 (Local Ordinances) APIs — 3 APIs

## 3.1 자치법규 목록 조회 — `ordin_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=ordin`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: ordin(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태 HTML/XML/JSON |
| nw | int | (1: 현행, 2: 연혁, 기본값: 현행) |
| search | int | 검색범위 (기본: 1 자치법규명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 (defalut=*) |
| display | int | 검색된 결과 개수 (default=20 max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| sort | string | 정렬옵션 |
| date | int | 공포일자 검색 |
| efYd | string | 시행일자 범위 검색 |
| ancYd | string | 공포일자 범위 검색 |
| ancNo | string | 공포번호 범위 검색 |
| nb | int | 공포번호 검색 |
| org | string | 지자체별 도·특별시·광역시 검색 (ex. 서울특별시: org=6110000) |
| sborg | string | 지자체별 시·군·구 검색 (필수값: org) |
| knd | string | 법령종류 (30001-조례/30002-규칙/30003-훈령/30004-예규/30006-기타/30010-고시/30011-의회규칙) |
| rrClsCd | string | 제개정 종류 |
| ordinFd | int | 분류코드별 검색 |
| lsChapNo | string | 법령분야별 검색 |
| gana | string | 사전식 검색 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=ordin&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=ordin&query=청소년&type=JSON
```

**Response Fields:**
| 필드 | 값 | 설명 |
|------|-----|------|
| 자치법규일련번호 | int | 자치법규일련번호 |
| 자치법규명 | string | 자치법규명 |
| 자치법규ID | int | 자치법규ID |
| 공포일자 | string | 공포일자 |
| 공포번호 | string | 공포번호 |
| 제개정구분명 | string | 제개정구분명 |
| 지자체기관명 | string | 지자체기관명 |
| 자치법규종류 | string | 자치법규종류 |
| 시행일자 | string | 시행일자 |
| 자치법규상세링크 | string | 자치법규상세링크 |
| 자치법규분야명 | string | 자치법규분야명 |

---

## 3.2 자치법규 본문 조회 — `ordin_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=ordin`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: ordin(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태 HTML/XML/JSON |
| ID | char | 자치법규 ID (ID 또는 MST 중 하나 필수) |
| MST | char | 자치법규 일련번호 |

LexLink 인자: `id`, `mst`, `oc`, `type` (기본 JSON). 본문이 크다(예: mst=2171833 → 72KB).

**Sample URL:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=ordin&MST=2171833&type=JSON
```

---

## 3.3 자치법규 기준 법령 연계 관련 목록 조회 — `ordinLsCon_search` ✅ IMPLEMENTED (redesigned v2.2.0)
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkOrd | lnkLsOrd | lnkOrg`

> 이전 버전은 존재하지 않는 target `ordinLsCon`을 호출해 항상 빈 응답(`raw_content: ""`)을 받았다. 업스트림 가이드의 실제 target은 아래 3종이며, LexLink는 **한 도구에서 정확히 하나의 모드 인자**만 받도록 구현했다. 0개 또는 2개 이상이면 `VALIDATION_ERROR`.

| LexLink 인자 | 업스트림 target | 업스트림 파라미터 | 설명 |
|--------------|-----------------|-------------------|------|
| `query` | `lnkOrd` | `query` | 조례명 검색 (예: "주차장") |
| `law_id` | `lnkLsOrd` | `knd` = 법령ID | 해당 법령을 근거로 한 자치법규 (예: 001823) |
| `org` | `lnkOrg` | `org` | 지자체 코드별 (예: 3270000 부산 동구). 항목에 연계 법령ID/법령명한글 포함 |

공통 파라미터: `OC`, `type`, `display` (default 20, max 100), `page`, `sort` (lasc/ldes, dasc/ddes, nasc/ndes, efasc/efdes — `lnkOrd` 문서 기준).

**Response:** 루트 `OrdinSearch` (org 모드는 `lnkOrgSearch`), 리스트 키 `law`. 항목: 자치법규ID, 자치법규일련번호, 자치법규명, 자치법규종류, 공포일자, 공포번호, 시행일자, 제개정구분명. 본문은 `ordin_service(id=자치법규ID)`.

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkOrd&query=주차장&type=JSON&display=2
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrd&knd=001823&type=JSON&display=2
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkOrg&org=3270000&type=JSON&display=2
```

---

# 4. 판례·결정례·해석례 (Case Law) APIs — 8 APIs (ALL IMPLEMENTED)

## 4.1 판례 목록 조회 — `prec_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=prec`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: prec(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 판례명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20, max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| org | string | 법원종류 (대법원:400201, 하위법원:400202) |
| curt | string | 법원명 (대법원, 서울고등법원 등) |
| JO | string | 참조법령명 (형법, 민법 등) |
| gana | string | 사전식 검색 |
| sort | string | 정렬옵션 (기본: ddes) |
| date | int | 선고일자 |
| prncYd | string | 선고일자 검색 |
| nb | string | 사건번호 |
| datSrcNm | string | 데이터출처명 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=XML&query=담보권
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=HTML&query=담보권&curt=대법원
```

---

## 4.2 판례 본문 조회 — `prec_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=prec`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: prec(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON (* 국세청 판례는 HTML만 가능) |
| ID | char(필수) | 판례 일련번호 |
| LM | string | 판례명 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=prec&ID=228541&type=HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=prec&ID=228541&type=XML
```

---

## 4.3 헌재결정례 목록 조회 — `detc_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=detc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: detc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 헌재결정례명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 |
| page | int | 검색 결과 페이지 |
| gana | string | 사전식 검색 |
| sort | string | 정렬옵션 |
| date | int | 종국일자 |
| edYd | string | 종국일자 기간 검색 |
| nb | int | 사건번호 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=detc&type=XML&query=벌금
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=detc&type=HTML&date=20150210
```

---

## 4.4 헌재결정례 본문 조회 — `detc_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=detc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: detc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char(필수) | 헌재결정례 일련번호 |
| LM | string | 헌재결정례명 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=detc&ID=58386&type=HTML
```

---

## 4.5 법령해석례 목록 조회 — `expc_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=expc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: expc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 법령해석례명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 |
| page | int | 검색 결과 페이지 |
| inq | string | 질의기관 |
| rpl | int | 회신기관 |
| gana | string | 사전식 검색 |
| itmno | int | 안건번호 (13-0217 → 130217) |
| regYd | string | 등록일자 검색 |
| explYd | string | 해석일자 검색 |
| sort | string | 정렬옵션 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=expc&type=XML&query=임차
```

---

## 4.6 법령해석례 본문 조회 — `expc_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=expc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: expc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | int(필수) | 법령해석례 일련번호 |
| LM | string | 법령해석례명 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=expc&ID=334617&type=HTML
```

---

## 4.7 행정심판례 목록 조회 — `decc_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=decc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: decc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 행정심판례명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 |
| page | int | 검색 결과 페이지 |
| cls | string | 재결례유형 |
| gana | string | 사전식 검색 |
| date | int | 의결일자 |
| dpaYd | string | 처분일자 검색 |
| rslYd | string | 의결일자 검색 |
| sort | string | 정렬옵션 |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=decc&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=decc&type=XML&gana=ga
```

---

## 4.8 행정심판례 본문 조회 — `decc_service` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=decc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: decc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| ID | char(필수) | 행정심판례 일련번호 |
| LM | string | 행정심판례명 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawService.do?OC=test&target=decc&ID=243263&type=HTML
```

---

# 5. 위원회 결정문 (Committee Decisions) APIs — 24 APIs (2 parametric tools implemented)

## 5.1 개인정보보호위원회 결정문 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=ppc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string(필수) | 서비스 대상 (개인정보보호위원회: ppc) |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (1: 안건명, 2: 본문검색) |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20 max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| gana | string | 사전식 검색 |
| sort | string | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes) |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=ppc&type=HTML
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=ppc&type=XML
```

**Response Fields:**
| 필드 | 값 | 설명 |
|------|-----|------|
| target | string | 검색서비스 대상 |
| 키워드 | string | 검색 단어 |
| section | string | 검색범위 |
| totalCnt | int | 검색 건수 |
| page | int | 현재 페이지번호 |
| 기관명 | string | 위원회명 |
| ppc id | int | 검색 결과 순번 |
| 결정문일련번호 | int | 결정문 일련번호 |
| 안건명 | string | 안건명 |
| 의안번호 | string | 의안번호 |
| 회의종류 | string | 회의종류 |
| 결정구분 | string | 결정구분 |
| 의결일 | string | 의결일 |
| 결정문상세링크 | string | 결정문 상세링크 |

---

## 5.2-5.24 Other Committee Decision APIs

All 12 committees follow the same API pattern:

| Committee | target (목록) | target (본문) |
|-----------|---------------|---------------|
| 개인정보보호위원회 | ppc | ppc |
| 고용보험심사위원회 | eiac | eiac |
| 공정거래위원회 | ftc | ftc |
| 국민권익위원회 | acr | acr |
| 금융위원회 | fsc | fsc |
| 노동위원회 | nlrc | nlrc |
| 방송미디어통신위원회 | kcc | kcc |
| 산업재해보상보험재심사위원회 | iaciac | iaciac |
| 중앙토지수용위원회 | oclt | oclt |
| 중앙환경분쟁조정위원회 | ecc | ecc |
| 증권선물위원회 | sfc | sfc |
| 국가인권위원회 | nhrck | nhrck |

---

# 6. 조약 (Treaties) APIs — 2 APIs (ALL IMPLEMENTED)

## 6.1 조약 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=trty`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: trty(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 조약명) 2: 조약본문 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20 max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| gana | string | 사전식 검색 |
| eftYd | string | 발효일자 검색 (20090101~20090130) |
| concYd | string | 체결일자 검색 (20090101~20090130) |
| cls | int | 1: 양자조약, 2: 다자조약 |
| natCd | int | 국가코드 |
| sort | string | 정렬옵션 (lasc/ldes/dasc/ddes/nasc/ndes/rasc/rdes) |
| popYn | string | 상세화면 팝업창 여부 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=trty&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=trty&type=XML&cls=2
```

**Response Fields:**
| 필드 | 값 | 설명 |
|------|-----|------|
| target | string | 검색 대상 |
| 키워드 | string | 키워드 |
| section | string | 검색범위 |
| totalCnt | int | 검색결과갯수 |
| page | int | 출력페이지 |
| trty id | int | 검색결과번호 |
| 조약일련번호 | int | 조약일련번호 |
| 조약명 | string | 조약명 |
| 조약구분코드 | string | 조약구분코드 |
| 조약구분명 | string | 조약구분명 |
| 발효일자 | string | 발효일자 |
| 서명일자 | string | 서명일자 |
| 관보게제일자 | string | 관보게제일자 |
| 조약번호 | int | 조약번호 |
| 국가번호 | int | 국가번호 |
| 조약상세링크 | string | 조약상세링크 |

---

## 6.2 조약 본문 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=trty`

---

# 7. 별표·서식 (Tables & Forms) APIs — 3 APIs (NOT IMPLEMENTED)

## 7.1 법령 별표·서식 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lsByl`

## 7.2 행정규칙 별표·서식 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=admrulByl`

## 7.3 자치법규 별표·서식 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=ordinByl`

---

# 8. 학칙·공단·공공기관 APIs — 2 APIs (NOT IMPLEMENTED)

## 8.1 학칙·공단·공공기관 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=schlPubRul`

## 8.2 학칙·공단·공공기관 본문 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=schlPubRul`

---

# 9. 법령용어 (Legal Terms) APIs — 2 APIs (NOT IMPLEMENTED)

## 9.1 법령 용어 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lsTrm`

## 9.2 법령 용어 본문 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lsTrm`

---

# 10. 모바일 (Mobile) APIs — 22 APIs (NOT IMPLEMENTED)

> **Note:** Mobile APIs mirror the main APIs with mobile-optimized responses. Not implemented due to redundancy.

| API | target |
|-----|--------|
| 법령 목록 조회 | mobLs |
| 법령 본문 조회 | mobLs |
| 행정규칙 목록 조회 | mobAdmrul |
| 행정규칙 본문 조회 | mobAdmrul |
| 자치법규 목록 조회 | mobOrdin |
| 자치법규 본문 조회 | mobOrdin |
| 판례 목록 조회 | mobPrec |
| 판례 본문 조회 | mobPrec |
| 헌재결정례 목록 조회 | mobDetc |
| 헌재결정례 본문 조회 | mobDetc |
| 법령해석례 목록 조회 | mobExpc |
| 법령해석례 본문 조회 | mobExpc |
| 행정심판례 목록 조회 | mobDecc |
| 행정심판례 본문 조회 | mobDecc |
| 조약 목록 조회 | mobTrty |
| 조약 본문 조회 | mobTrty |
| 법령 별표·서식 목록 조회 | mobLsByl |
| 행정규칙 별표·서식 목록 조회 | mobAdmrulByl |
| 자치법규 별표·서식 목록 조회 | mobOrdinByl |
| 법령 용어 목록 조회 | mobLsTrm |

---

# 11. 맞춤형 (Customized) APIs — 6 APIs (NOT IMPLEMENTED)

| API | target |
|-----|--------|
| 맞춤형 법령 목록 조회 | custLs |
| 맞춤형 법령 조문 목록 조회 | custLsJo |
| 맞춤형 행정규칙 목록 조회 | custAdmrul |
| 맞춤형 행정규칙 조문 목록 조회 | custAdmrulJo |
| 맞춤형 자치법규 목록 조회 | custOrdin |
| 맞춤형 자치법규 조문 목록 조회 | custOrdinJo |

---

# 12. 법령정보 지식베이스 (Knowledge Base) APIs — 9 APIs (ALL IMPLEMENTED)

## 12.1 법령용어 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lstrmAI`

## 12.2 일상용어 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=dlytrm`

## 12.3 법령용어-일상용어 연계 조회 — `lstrm_rlt_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lstrmRlt` (v2.2.0: **lawService.do**, 이전엔 lawSearch.do라 0-byte 응답)

| LexLink 인자 | 업스트림 | 설명 |
|--------------|----------|------|
| `query` / `mst` | `query` / `MST` | 법령용어명 또는 용어 일련번호 (둘 중 하나) |
| `trm_rlt_cd` | `trmRltCd` | 140301 동의어, … 140305 연관어 (선택) |

`display`/`page`는 업스트림에 없다. 응답 루트 `lstrmRltService`.

## 12.4 일상용어-법령용어 연계 조회 — `dlytrm_rlt_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=dlytrmRlt` (v2.2.0: lawService.do)

인자는 12.3과 동일 (`query` 또는 `mst`, 선택 `trm_rlt_cd`). 응답 루트 `dlytrmRltService`.

## 12.5 법령용어-조문 연계 조회 — `lstrm_rlt_jo_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lstrmRltJo` (v2.2.0: lawService.do)

인자: `query` 또는 `mst`. 응답 루트 `lstrmRltJoService`. `display`/`page` 없음.

## 12.6 조문-법령용어 연계 조회 — `jo_rlt_lstrm_search` ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=joRltLstrm` (v2.2.0: lawService.do)

| LexLink 인자 | 업스트림 | 설명 |
|--------------|----------|------|
| `jo` (필수) | `JO` | 6자리 조문코드. `35`, `35의5` 등은 자동 정규화 |
| `query` 또는 `law_id` | `query` / `ID` | 법령명 또는 법령ID (둘 중 하나) |

응답 루트 `joRltLstrmService`. 예: `lawService.do?target=joRltLstrm&query=저작권법&JO=003505`.

## 12.7 관련법령 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lsRlt`

## 12.8 지능형 법령검색 시스템 검색 API 조회 — aiSearch ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=aiSearch`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string(필수) | 서비스 대상 (aiSearch) |
| type | char(필수) | 출력 형태: XML only (JSON not supported) |
| search | int | 검색범위 법령분류 (0:법령조문, 1:법령 별표·서식, 2:행정규칙 조문, 3:행정규칙 별표·서식) |
| query | string | 검색을 원하는 질의 (natural language supported) |
| display | int | 검색된 결과 개수 (default=20) |
| page | int | 검색 결과 페이지 (default=1) |

**Key Feature:** Returns full article text (조문내용) - more comprehensive than eflaw_search.

**Sample URLs:**
```
https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=aiSearch&type=XML&search=0&query=뺑소니
```

## 12.9 지능형 법령검색 시스템 연관법령 API 조회 — aiRltLs_search ✅ IMPLEMENTED
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=aiRltLs`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string(필수) | 서비스 대상 (aiRltLs) |
| type | char(필수) | 출력 형태: XML/JSON |
| search | int | 검색범위 법령분류 (0:법령조문, 1:행정규칙조문) |
| query | string | 법령명에서 검색을 원하는 질의 |

**Key Feature:** Find semantically related laws (e.g., "민법" → 상법, 의료법, 소송촉진법)

---

# 13. 중앙부처 1차 해석 (Ministry Interpretations) APIs — 76 APIs (2 parametric tools implemented, v2.2.0 fixed)

39 ministries / 76 APIs (37개 부처: 목록+본문, **재정경제부·국세청: 목록만**) follow the same pattern:

**Endpoint Pattern:**
- 목록 조회: `GET http://www.law.go.kr/DRF/lawSearch.do?target={code}CgmExpc`
- 본문 조회: `GET http://www.law.go.kr/DRF/lawService.do?target={code}CgmExpc` (ID 필수)

> v2.2.0: target 형식은 `{code}CgmExpc` (소문자 코드, 예 `moelCgmExpc`). 이전 `cgmExpc{Code}`는 모든 부처에서 빈 응답이었다. 응답 루트 `CgmExpc`, 리스트 키 `cgmExpc`, 제목 필드 `안건명`. 목록 전용 부처(재정경제부, 국세청)에 `cgm_expc_service`를 호출하면 `VALIDATION_ERROR`.

| Ministry | target code |
|----------|-------------|
| 고용노동부 | Moel |
| 국토교통부 | Molit |
| 재정경제부 (구 기획재정부, 별칭 허용) | Moef (목록만) |
| 해양수산부 | Mof |
| 행정안전부 | Mois |
| 기후에너지환경부 | Me |
| 관세청 | Kcs |
| 국세청 | Nts (목록만) |
| 교육부 | Moe |
| 과학기술정보통신부 | Msit |
| 국가보훈부 | Mpva |
| 국방부 | Mnd |
| 농림축산식품부 | Mafra |
| 문화체육관광부 | Mcst |
| 법무부 | Moj |
| 보건복지부 | Mohw |
| 산업통상부 | Motie |
| 성평등가족부 | Mogef |
| 외교부 | Mofa |
| 중소벤처기업부 | Mss |
| 통일부 | Mou |
| 법제처 | Moleg |
| 식품의약품안전처 | Mfds |
| 인사혁신처 | Mpm |
| 기상청 | Kma |
| 국가유산청 | Khs |
| 농촌진흥청 | Rda |
| 경찰청 | Npa |
| 방위사업청 | Dapa |
| 병무청 | Mma |
| 산림청 | Kfs |
| 소방청 | Nfa |
| 재외동포청 | Oka |
| 조달청 | Pps |
| 질병관리청 | Kdca |
| 국가데이터처 | Kostat |
| 지식재산처 | Kipo |
| 해양경찰청 | Kcg |
| 행정중심복합도시건설청 | Naacc |

**Example (고용노동부):**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=moelCgmExpc&type=XML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=moelCgmExpc&ID=123&type=XML
```

---

# 14. 특별행정심판 (Special Administrative Appeals) APIs — 8 APIs (2 parametric tools implemented)

> v2.2.0: `special_decc_search`는 응답 루트 `Decc`/리스트 키 `decc`를 인식해 `display`를 실제로 적용한다 (이전: 100건·59KB 원본 반환).

## 14.1 조세심판원 특별행정심판재결례 목록 조회
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=ttSpecialDecc`

| 요청변수 | 값 | 설명 |
|----------|-----|------|
| OC | string(필수) | 사용자 이메일의 ID |
| target | string: ttSpecialDecc(필수) | 서비스 대상 |
| type | char(필수) | 출력 형태: HTML/XML/JSON |
| search | int | 검색범위 (기본: 1 특별행정심판재결례명) 2: 본문검색 |
| query | string | 검색을 원하는 질의 |
| display | int | 검색된 결과 개수 (default=20 max=100) |
| page | int | 검색 결과 페이지 (default=1) |
| cls | string | 재결례유형 |
| gana | string | 사전식 검색 |
| date | int | 의결일자 |
| dpaYd | string | 처분일자 검색 |
| rslYd | string | 의결일자 검색 |
| sort | string | 정렬옵션 |
| popYn | string | 상세화면 팝업창 여부 |
| fields | string | 응답항목 옵션 |

**Sample URLs:**
```
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=ttSpecialDecc&type=XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=ttSpecialDecc&type=XML&gana=ga
```

**Response Fields:**
| 필드 | 값 | 설명 |
|------|-----|------|
| target | string | 검색 대상 |
| 키워드 | string | 키워드 |
| section | string | 검색범위 |
| totalCnt | int | 검색결과갯수 |
| page | int | 출력페이지 |
| decc id | int | 검색결과번호 |
| 특별행정심판재결례일련번호 | int | 일련번호 |
| 사건명 | string | 사건명 |
| 청구번호 | string | 청구번호 |
| 처분일자 | string | 처분일자 |
| 의결일자 | string | 의결일자 |
| 처분청 | string | 처분청 |
| 재결청 | int | 재결청 |
| 재결구분명 | string | 재결구분명 |
| 재결구분코드 | string | 재결구분코드 |
| 데이터기준일시 | string | 데이터기준일시 |
| 행정심판재결례상세링크 | string | 상세링크 |

---

## 14.2-14.8 Other Special Administrative Appeal APIs

| Organization | target (목록) | target (본문) |
|--------------|---------------|---------------|
| 조세심판원 | ttSpecialDecc | ttSpecialDecc |
| 해양안전심판원 | kmstSpecialDecc | kmstSpecialDecc |
| 국민권익위원회 | acrSpecialDecc | acrSpecialDecc |
| 인사혁신처 소청심사위원회 | adapSpecialDecc | adapSpecialDecc |

---

# 15. Phase 4: Article Citation Extraction — 1 API (IMPLEMENTED)

## 15.1 조문 인용 추출 API — `article_citation` ✅ IMPLEMENTED

**Method**: HTML Parsing (law.go.kr)
**Purpose**: Extract all legal citations referenced by a specific law article
**Implementation**: `src/lexlink/citation.py`

> ⚠️ This is a **custom tool** using HTML parsing, NOT an official API.

### Technical Approach

Unlike the XML-based tools, this tool parses HTML from law.go.kr and reads the hyperlinked citations. No LLM is involved, so there is no LLM cost. Accuracy is not guaranteed: "같은 법" and article lists are resolved heuristically (see 알려진 한계), so check the article text when it matters.

With an OC, `mst` / `law_name` / `article` are verified with one `lawService` call first: a law-name mismatch gives `VALIDATION_ERROR`, a missing article gives `ARTICLE_NOT_FOUND`. Without an OC the check is skipped and `warnings` says so.

### Request Parameters
| 요청변수 | 값 | 설명 |
|----------|-----|------|
| mst | string(필수) | 법령일련번호 (eflaw_search 결과에서 획득) |
| law_name | string(필수) | 법령명 (예: "건축법") |
| article | int(필수) | 조문 번호 (예: 3 for 제3조) |
| article_branch | int | 조문 가지번호 (예: 2 for 제3조의2, default: 0) |
| oc | string | 선택. 있으면 위 검증에 사용 (HTTP 모드에서는 서버 OC) |

### Sample Usage (MCP Tool)
```python
# Step 1: Search for the law to get MST
eflaw_search(query="건축법")
# Returns: { "법령일련번호": "268611", "법령명한글": "건축법", ... }

# Step 2: Extract citations from article
article_citation(
    mst="268611",
    law_name="건축법",
    article=3
)
```

### Response Fields
| 필드 | 값 | 설명 |
|------|-----|------|
| success | bool | 성공 여부 |
| law_id | string | MST (법령일련번호, lsiSeq) |
| law_name | string | 법령명 |
| article | string | 조문 표시 (예: "제3조", "제3조의2") |
| citation_count | int | 총 인용 개수 |
| internal_count | int | 내부 인용 개수 (같은 법령 내) |
| external_count | int | 외부 인용 개수 (다른 법령) |
| citations | array | 인용 목록 |

### Citation Object
| 필드 | 값 | 설명 |
|------|-----|------|
| type | string | "internal" | "external" |
| target_law_name | string | 대상 법령명 (예: "「신탁법」") |
| target_article | int | 대상 조번호 |
| target_article_branch | int | 대상 조가지번호 (optional) |
| target_paragraph | int | 대상 항번호 (optional) |
| target_item | int | 대상 호번호 (optional) |
| raw_text | string | 원문 텍스트 |

### Sample Response (illustrative values)
```json
{
    "success": true,
    "law_id": "268611",
    "law_name": "건축법",
    "article": "제3조",
    "citation_count": 12,
    "internal_count": 4,
    "external_count": 8,
    "citations": [
        {
            "type": "external",
            "target_law_name": "「국토의 계획 및 이용에 관한 법률」",
            "target_article": 56,
            "target_paragraph": 1,
            "raw_text": "「국토의 계획 및 이용에 관한 법률」 제56조제1항"
        },
        {
            "type": "internal",
            "target_article": 51,
            "raw_text": "제51조"
        }
    ]
}
```

---

# 16. 사전컨설팅 의견서 (Pre-consulting Opinions) APIs — 2 APIs (NOT IMPLEMENTED, NEW)

감사원 사전컨설팅 의견서. 2026-10-25 가이드에서 신규 확인 (191 → 195).

| 구분 | Endpoint |
|------|----------|
| 목록 | `GET http://www.law.go.kr/DRF/lawSearch.do?target=baiPvcs` |
| 본문 | `GET http://www.law.go.kr/DRF/lawService.do?target=baiPvcs` |

직접 호출 확인: `type=JSON` 정상 (151건, `search=2` 본문검색 지원, 응답 루트 `BaiPvcs`). 도구 추가 후보이나 PlayMCP 컨텍스트 비용 때문에 미정.

---

# Appendix A: 제개정 종류 코드표

| 코드 | 구분명 |
|------|--------|
| 300201 | 제정 |
| 300202 | 일부개정 |
| 300203 | 전부개정 |
| 300204 | 폐지 |
| 300205 | 폐지제정 |
| 300206 | 일괄개정 |
| 300207 | 일괄폐지 |
| 300208 | 기타 |
| 300209 | 타법개정 |
| 300210 | 타법폐지 |

---

# Appendix B: 정렬 옵션 (Sort Options)

| 코드 | 설명 |
|------|------|
| lasc | 법령명 오름차순 (기본값) |
| ldes | 법령명 내림차순 |
| dasc | 공포일자/의결일자 오름차순 |
| ddes | 공포일자/의결일자 내림차순 |
| nasc | 공포번호/사건번호 오름차순 |
| ndes | 공포번호/사건번호 내림차순 |
| efasc | 시행일자 오름차순 |
| efdes | 시행일자 내림차순 |
| rasc | 관보게재일 오름차순 (조약) |
| rdes | 관보게재일 내림차순 (조약) |

---

# Appendix C: LexLink 구조화 오류 코드

모든 도구 오류는 `status: "error"`, `error_code`, `message`, `hints[]`, `request_id` 형태로 반환된다.

| error_code | 의미 | 처리 |
|------------|------|------|
| `VALIDATION_ERROR` | 인자 형식·범위·조합 오류 (잘못된 `jo`, `ordinLsCon_search` 모드 인자 0/2개 이상, 목록 전용 부처의 `cgm_expc_service` 등) | 힌트의 유효값 확인 |
| `TIMEOUT` | law.go.kr 요청 시간 초과 | 재시도 |
| `UPSTREAM_ERROR` | law.go.kr가 오류 응답 반환 | 메시지 확인 (IP/OC 등록 등) |
| `INTERNAL_ERROR` | 예상치 못한 서버 오류 | 정상 운영에서는 발생하지 않아야 함 |
| `ARTICLE_NOT_FOUND` | 요청한 조문(`jo`)이 응답에 없음 | 조문 번호·법령 버전 확인 |
| `NOT_FOUND` | 업스트림이 "일치하는 … 없습니다"로 답했거나 본문이 비어 있음 (`prec_service`/`detc_service`/`expc_service`의 없는 ID, `lawService.do`의 빈 본문 등). 오류는 캐시되지 않음 | ID·검색어 확인 |
| `EMPTY_RESPONSE` | HTTP 200이지만 0-byte 본문. 대개 잘못된 target/엔드포인트 | target·엔드포인트 점검 (코드 버그 신호) |
| `API_NOT_SUBSCRIBED` | "미신청된 목록/본문에 대한 접근입니다" — OC 계정이 해당 API 종류를 open.law.go.kr에서 신청하지 않음. `eflaw` 본문이면 `law_service`/`eflaw_josub` 대안 안내 | open.law.go.kr에서 API 신청 추가 |
| `UPSTREAM_HTML_ERROR` | JSON/XML을 요청했는데 HTML 또는 `error500` 페이지가 반환됨 | 재시도, 지속되면 `type=HTML` 가능 여부 확인 |

앞의 세 종류(EMPTY_RESPONSE, API_NOT_SUBSCRIBED, UPSTREAM_HTML_ERROR)는 `client.py`에서 감지하며, 이전에는 `status: ok`로 통과했다.

---

# Appendix D: 미구현 API 중 JSON 동작 확인 목록 (2026-10-25)

| target | 분류 | 확인 결과 |
|--------|------|-----------|
| `lsStmd` | 법령 체계도 목록 | JSON 정상 (root `LsStmdSearch`) |
| `oldAndNew` | 신구법 목록 | JSON 정상 (root `OldAndNewLawSearch`) |
| `thdCmp` | 3단 비교 목록 | JSON 정상 (root `thdCmpLawSearch`) |
| `licbyl` | 법령 별표·서식 목록 | JSON 정상 (root `licBylSearch`) |
| `lstrm` | 법령용어 목록 (비AI) | JSON 정상 (root `LsTrmSearch`) |
| `pi` | 학칙·공단·공공기관 목록 | JSON 정상 (root `AdmRulSearch`) |
| `lsHstInf` | 법령 변경이력 (regDt) | JSON 정상 (root `LawSearch`) |
| `lsJoHstInf` | 조문별 변경 이력 (`lawService.do`, ID+JO) | JSON 정상 |
| `lnkOrd` / `lnkLsOrd` / `lnkOrg` | 자치법규 기준 연계 | JSON 정상 (v2.2.0부터 `ordinLsCon_search`로 구현) |
| `baiPvcs` | 감사원 사전컨설팅 의견서 | JSON 정상 (Section 16) |
| `lsAbrv` | 법률명 약칭 | JSON 정상이나 query/display 무시, 2,714건 전체(2.3MB) 반환 |
| `lsHistory` | 법령 연혁 목록/본문 | **HTML 전용** (type=JSON/XML도 HTML 반환) |

미확인: `admrulOldAndNew`, `oneView`, `datDelHst`, `admrulByl`, `ordinByl`, `lsDayJoRvs`, 모바일 22종, 맞춤형 6종.

---

Catalog of the 195 APIs in the law.go.kr Open API guide (2026-10-25), plus the LexLink-derived tools above.
