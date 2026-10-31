# LexLink 점검 체크리스트 (2026-10-25)

> **Archived 2026-10-31.** Historical record, not maintained. Counts, issue status and deployment details may be out of date. Current docs: [docs index](../README.md), [API reference](../API_REFERENCE.md), [CHANGELOG](../../CHANGELOG.md).


코드 수정 전 현황 파악용 문서. 54개 도구를 실제 호출해 동작을 확인하고, 법제처 Open API 가이드(open.law.go.kr) 목록과 대조했다.

## 0. 점검 방법

| 항목 | 내용 |
|---|---|
| 점검 대상 서버 | 원격 `https://lexlink-ko-mcp.ngrok.io/mcp` (Claude Code `lexlink` MCP). 로컬 코드(main, `711b8a4`)와 도구 목록 54개 동일 |
| 호출 방식 | Claude Code MCP 도구 호출 49종 + `mcp` 파이썬 클라이언트로 prompts/resources/인자 처리 확인 |
| 업스트림 직접 확인 | 이 Mac(공인 IP 등록됨)에서 `https://www.law.go.kr/DRF/lawSearch.do`, `lawService.do`를 urllib로 직접 호출해 target 이름·엔드포인트 가설 검증 (부록 A) |
| 가이드 대조 | `open.law.go.kr/LSO/openApi/guideList.do`의 `openApiGuide('…')` 195개 ID 추출 → `docs/API_REFERENCE.md`(191개 카탈로그)와 비교 |
| 미점검 | PlayMCP(HTTP/SSE) 경유 24KB 제한 동작, `raw_logger`/`log_processor`, 캐시 TTL 만료 동작 |

범례: ✅ 정상 · ⚠️ 동작하나 문제 있음 · ❌ 기능 불능 · ⏭ 미점검

## 1. 저장소·배포 상태

- [x] **버전 불일치**: `pyproject.toml` 2.1.0, `src/lexlink/__init__.py` `__version__ = "1.5.2"`. MCP `serverInfo.version`은 `1.26.0`(mcp 라이브러리 버전)으로 노출됨 → LexLink 버전을 명시하도록 수정.
- [x] **tests/ 디렉터리 없음**: `pyproject.toml`에 pytest 설정과 README에 테스트 개수가 있지만 저장소에 `tests/`가 없다(별도 repo로 분리된 것인지 확인).
- [x] **캐시 키에 type 누락** — 수정됨(v2.2.0)
- [ ] **문서 드리프트**: `AGENTS.md`는 "XML-only responses, JSON format is broken"이라 하지만 v2.0.0부터 JSON이 기본. `API_REFERENCE.md` 3.1~3.3 자치법규가 "NOT IMPLEMENTED"로 남아 있음(실제 구현됨). 중앙부처 해석 64개 → 현재 76개.
- [ ] **OC 계정 신청 범위**: `lawService.do?target=eflaw`(현행법령 시행일 **본문**)는 "미신청된 목록/본문에 대한 접근입니다" HTML 반환. 목록(`eflaw` search)·조항호목(`eflawjosub`)·공포일 본문(`law`)은 정상. open.law.go.kr에서 해당 API 신청 추가 필요(코드 문제 아님).
- [ ] **IP 등록 의존**: 업스트림은 OC에 등록된 IP에서만 응답. 로컬 실행용 `.mcp.json`(상위 폴더)에 `lexlink-local` 등록돼 있음.
- [ ] **캐시 포화**: `cache_stats` 기준 entries 500/500(max), hit rate 8.6%. 상한·TTL·eviction 정책 재검토.
- [ ] **알 수 없는 인자 무시**: 존재하지 않는 인자(`bogus_param`, `start_date`)를 넘겨도 오류 없이 기본값으로 실행됨. LLM이 인자 이름을 틀려도 조용히 다른 결과를 돌려주므로 strict 검증 또는 경고 반환 검토.

## 2. 도구별 동작 점검표 (54개)

### 2.1 법령 (Phase 1·2)

| 도구 | 상태 | 테스트 입력 | 관찰 |
|---|---|---|---|
| eflaw_search | ✅ | query=저작권법 | 시행예정·연혁 포함 138건, 정렬 정상 |
| law_search | ✅ | query=저작권법 | 현행 3건(법·시행령·시행규칙). 접두 매칭이라 하위법령이 섞임 |
| eflaw_service | ❌ | mst=283335 (jo 유무 모두) | 업스트림 "미신청" HTML을 `status: ok`, `raw_content`에 그대로 반환. ①계정 신청 ②오류 감지 둘 다 필요 |
| law_service | ✅ | mst=283335 | 267KB (PlayMCP 24KB 초과, Issue #7) |
| eflaw_josub | ✅ | mst=283335, jo=003505 | 정상. 단 jo는 6자리 코드만 인식 |
| law_josub | ⚠️ | jo=35 / jo=35의5 / jo=003505 | 35·"35의5"는 오류 없이 `기본정보`만 또는 `{}` 반환. `validation.format_article_number`가 있으나 입력 정규화에 쓰이지 않음 |
| elaw_search | ⚠️ | query=Copyright Act | `법령명영문`에 `<strong class="tbl_tx_type">` 하이라이트 태그 잔존 |
| elaw_service | ✅ | mst=283335 | 290KB |
| admrul_search | ✅ | query=저작권 | 8건 |
| admrul_service | ✅ | id=2100000195427 | 약 15KB, 조문·별표·부칙 정상 |
| lnkLs_search | ✅ | query=건축법 | 3건 |
| lnkLsOrdJo_search | ✅ | query=건축법 | 11,969건 중 3건 |
| lnkDep_search | ✅ | org=1400000 | 1,161건 |
| drlaw_search | ⚠️ | (없음) | 업스트림이 HTML 전용. 46KB HTML 그대로 반환(파싱 없음) |
| lsDelegated_service | ✅ | mst=283335 | 168KB |

### 2.2 판례·결정례·해석례·인용·AI 검색 (Phase 3·4·5)

| 도구 | 상태 | 테스트 입력 | 관찰 |
|---|---|---|---|
| prec_search | ✅ | query=공정이용, search=2 | 본문 검색 1,631건. 기본 search=1(사건명)이라 주제어 검색은 0건이 됨 → 설명·기본값 재검토 |
| prec_service | ✅ | id=67870, sections=summary | 요약 모드 정상 |
| detc_search | ✅ | query=저작권 | 22건. 일부 `종국일자: "0"`(업스트림 데이터) |
| detc_service | ✅ | id=34068, summary | 판시사항·결정요지 빈값(업스트림) |
| expc_search / expc_service | ✅ | 저작권 / id=339879 | 정상 |
| decc_search / decc_service | ✅ | 저작권 / id=4977 | 본문 루트 키가 `PrecService`(업스트림 명칭) |
| article_citation | ✅ | 저작권법 제35조의5 | 2건 추출, 10.2초 소요. 범위 인용("제23조부터 제35조의4")은 첫 조문만(알려진 제한) |
| aiSearch | ⚠️ | 공정이용·정보분석·AI 학습 | 목표 조문(제35조의5)은 찾지만 국가데이터처 직제 시행규칙 등 무관 조문이 상위에 섞임 |
| aiRltLs_search | ✅ | query=저작권법 | 10건 |

### 2.3 자치법규·조약·지식베이스·위원회·부처해석·특별행정심판 (Phase 7)

| 도구 | 상태 | 테스트 입력 | 관찰 |
|---|---|---|---|
| ordin_search | ✅ | 서울특별시 주차장 | 95건. 0건일 때는 `ranked_data` 없이 `raw_content`만 반환(응답 형태 불일치) |
| ordin_service | ✅ | mst=2171833 | 72KB |
| ordinLsCon_search | ❌ | query=서울특별시 주차장 설치 및 관리 조례 | `raw_content: ""`. **target `ordinLsCon`은 업스트림에 없음**. 가이드상 자치법규 기준 연계 API는 `lnkOrd`(조례명), `lnkLsOrd`(knd=법령ID), `lnkOrg`(org=지자체코드) 3종. 직접 호출로 `lnkOrd`·`lnkLsOrd` 정상 확인 |
| trty_search / trty_service | ✅ | 저작권 / id=2157 | 정상 |
| lstrm_ai_search | ✅ | query=공정이용 | 2건 |
| dlytrm_search | ✅ | query=월세 | 15건 |
| lstrm_rlt_search | ❌ | query=임대차, query=1470403 | `raw_content: ""`. **업스트림은 `lawService.do`(query 또는 MST)**인데 LexLink는 `run_search`→`lawSearch.do`로 호출. 직접 호출 시 `lawService.do?target=lstrmRlt&query=공정한이용` 정상(root `lstrmRltService`) |
| dlytrm_rlt_search | ❌ | query=월세, 154361 | 동일 원인. `lawService.do?target=dlytrmRlt&query=월세` 정상(4.7KB) |
| lstrm_rlt_jo_search | ❌ | query=임대차 | 동일 원인. `lawService.do?target=lstrmRltJo&query=…` 정상 |
| jo_rlt_lstrm_search | ❌ | query=저작권법, 000798 | 동일 원인 + 필수 인자 `JO`(6자리) 없음. `lawService.do?target=joRltLstrm&query=저작권법&JO=003505` 정상(7KB) |
| ls_rlt_search | ✅ | query=저작권법 | 관련법령 4건 |
| committee_search | ✅ | 공정거래위원회/담합, 방송미디어통신위원회 | 정상. 잘못된 위원회명은 VALIDATION_ERROR로 유효값 안내 ✅ |
| committee_service | ✅ | 공정거래위원회, id=9721 | 정상 |
| cgm_expc_search | ❌ | 고용노동부/퇴직금, 기획재정부, 지식재산처, 법제처 | 전부 `raw_content: ""`. **target 명명 오류**: 코드는 `cgmExpc{Code}`(예 `cgmExpcMoel`), 업스트림은 `{code}CgmExpc`(예 `moelCgmExpc`, `kipoCgmExpc`). 직접 호출로 확인(806건/1,013건) |
| cgm_expc_service | ❌(추정) | — | 같은 `cgmExpc{Code}` 패턴 사용. 본문 가이드 target도 `moelCgmExpc`(`lawService.do`, ID 필수). 수정 후 검증 필요 |
| special_decc_search | ⚠️ | 조세심판원/양도소득세, display=3 | 59KB·100건 반환. over-fetch 100건 후 재랭킹하려 하나 응답 루트 `Decc`/리스트 키 `decc`를 `item_category="ttSpecialDecc"`로 찾지 못해 `ranked_data` 생성 실패 → display 미적용 원본 반환. 업스트림은 display=3을 정상 반영 |
| special_decc_service | ✅ | 조세심판원, id=105794 | 정상 |

### 2.4 법률 추론 도구 (Phase 8)

| 도구 | 상태 | 테스트 입력 | 관찰 |
|---|---|---|---|
| check_precedent_odds | ⚠️ | 저작권 공정이용 인정 / 저작권법위반 | 주제어는 0건(사건명 검색). 사건명 일치 시 동작하나 outcome 대부분 "불명", key_factors에 `<br/>` 잔존 |
| legal_resolver | ✅ | 회사 내부 업무용 복사 | 제30조·제31조·판례 3건 제시. 품질 양호 |
| simplify_article | ❌ | 저작권법 제35조의5 | `original_text: "{}"`, `simplified_text: "{}"`. 원인 ①`mst`로 시행예정 버전(291259) 선택 ②조문 텍스트 추출이 `조문내용` 키만 보는데 JSON에서 `조문내용`은 제목("제35조의5(저작물의 공정한 이용)")이고 본문은 `항`/`호` 중첩 구조 |
| law_amendment_summary | ❌ | 저작권법, 민법 | **개정 이력이 아니라 `law_search`(현행법령 목록) 결과를 revision으로 나열**. 저작권법 → 법·시행령·시행규칙 현행 3건이 "3회 개정"으로 표시, 2026-04-28(법률 21595)·2026-10-20(법률 22092) 개정 누락. 날짜 인자는 정상 동작(이전 점검 때 인자명 오기였음) |
| article_amendment_diff | ❌ | mst 270165→283335, 제35조의5 | old `{}`, new는 제목만. simplify_article과 같은 추출 로직 결함 |

### 2.5 체인 도구·캐시 (Phase 9)

| 도구 | 상태 | 테스트 입력 | 관찰 |
|---|---|---|---|
| chain_full_research | ⚠️ | 저작권 공정이용 | 조문 2건 정상, 판례 0건(사건명 검색 의존), 해석례 0건 |
| chain_amendment_track | ❌ | 저작권법 제35조 | law_amendment_summary 결함 상속. 시행규칙(20260507) 제35조와 법률 제35조를 비교해 JSON 원문 라인을 diff로 출력 |
| chain_dispute_prep | ⚠️ | 저작권 침해 | 판례 2건만. 헌재·행정심판·특별행정심판 0건(사건명 검색) |
| chain_law_system | ⚠️ | 저작권법 | 동작. `delegation_tree_raw`가 잘린 JSON 문자열, 시행예정 MST(291259) 선택, `linked_ordinances` 빈값, 행정규칙 1건만 |
| cache_stats | ✅ | — | 정상 |

### 2.6 Prompts / Resources

| 항목 | 상태 | 관찰 |
|---|---|---|
| prompts 9종 | ✅ | 목록 정상. `tool-selection-guide`, `search-korean-law`, `check-legal-precedent` get_prompt 확인 |
| `lexlink://laws/frequently-used` | ✅ | 20개 법령 매핑 반환 |
| `lexlink://law/{name}` | ❌ | `저작권법`, `자통법` 모두 not_found. 메시지에 `%EC%A0%80…`가 그대로 보임 → URL 디코딩 누락. seed alias(자통법)도 resolver를 거치지 않음 |

## 3. 수정 항목 체크리스트 (우선순위)

### P0 — 기능 불능

- [x] **cgm_expc_search / cgm_expc_service target 수정**: `f"cgmExpc{code}"` → `f"{code.lower()}CgmExpc"` (예 `moelCgmExpc`). 검증: 39개 부처 각 1회 호출해 totalCnt>0 확인. 재정경제부·국세청은 업스트림에 **본문(Info) API가 없음** → service 호출 시 안내 오류.
- [x] **지식베이스 연계 4종 엔드포인트 변경**: `lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`를 `run_service`(lawService.do)로 전환. 인자: `query` 또는 `MST`(용어 일련번호), `trmRltCd`(140301~140305). `jo_rlt_lstrm_search`는 `query`/`ID` + 필수 `JO`(6자리). 응답 루트 `*Service`.
- [x] **ordinLsCon_search 재설계**: target을 `lnkOrd`(조례명 검색), `lnkLsOrd`(knd=법령ID), `lnkOrg`(org=지자체코드)로 분리하거나 모드 인자 추가. 응답 루트 `OrdinSearch`, 리스트 키 `law`.
- [ ] **law_amendment_summary 데이터 소스 교체**: `law_search` 대신 ①`eflaw_search`(연혁·시행예정 포함, 법령ID로 필터) 또는 ②`lsHstInf`(regDt별 변경이력, JSON 정상) 또는 ③`lsJoHstInf`(조문별 변경 이력, `lawService.do?target=lsJoHstInf&ID=&JO=`, JSON 정상) 사용. 동일 법령ID로 한정해 시행령·시행규칙 혼입 제거. (진행 중, 패키지 C)
- [ ] **조문 텍스트 추출 공통화**: `simplify_article`, `article_amendment_diff`, `chain_amendment_track`이 쓰는 `_find_text`를 `조문내용` + `항`(`항내용`) + `호`(`호내용`) + `목`을 순서대로 이어 붙이는 함수로 교체. 현행(`현행연혁코드 == "현행"`) MST를 우선 선택. (진행 중, 패키지 C)
- [ ] **chain_amendment_track**: 위 두 항목 수정 후 같은 법령ID의 인접 두 버전만 비교하도록 재검증. (진행 중, 패키지 C)

### P1 — 품질·안정성

- [x] **special_decc_search 랭킹 실패**: `extract_items_list`가 루트 `Decc`/키 `decc`를 찾도록 매핑 추가, 실패 시에도 `display` 만큼만 잘라 반환하는 fallback.
- [x] **jo 입력 정규화**: `law_josub`/`eflaw_josub`(및 `jo` 받는 모든 도구)에서 `35`, `35의5`, `제35조의5`, `(35,5)`를 `003505`로 변환(`format_article_number` 재사용). 조문이 비어 있으면 힌트 포함 오류 반환.
- [x] **업스트림 HTML 오류 감지**: `client.py`에 "미신청된 목록/본문에 대한 접근입니다" 패턴 추가 → 구조화 오류(코드 예: `API_NOT_SUBSCRIBED`)와 신청 안내. 현재는 `status: ok`로 통과.
- [ ] **판례 계열 도구의 검색 범위**: `check_precedent_odds`, `chain_full_research`, `chain_dispute_prep`가 `search=2`(본문) 또는 사건명→본문 폴백을 쓰도록 변경. 도구 설명에 "기본은 사건명 검색"을 명시. (진행 중, 패키지 C)
- [x] **resource template 디코딩**: `lexlink://law/{name}`에서 `urllib.parse.unquote` 적용, resolver alias(자통법 등) 조회 후 캐시 미스 시 안내.
- [ ] **시행예정 MST 선택 로직**: `simplify_article`, `chain_law_system` 등 내부에서 첫 검색 결과(시행예정)를 집는 곳을 현행 우선으로 통일. (진행 중, 패키지 C)
- [ ] **하드코딩 기본값 `date_to="20261231"`**: `law_amendment_summary`, `chain_amendment_track` → 호출 시점 기준 연말/오늘로 계산. (진행 중, 패키지 C)
- [x] **서버 버전 노출**: `__version__` 2.1.0으로 맞추고 FastMCP `serverInfo.version`에 반영.
- [ ] **대용량 응답 정책(Issue #7)**: law_service 267KB, elaw_service 290KB, lsDelegated_service 168KB, ordin_service 72KB, special_decc_search 59KB. SLIM 모드에서의 처리 방침 결정(조건부 등록, 섹션 선택 인자 `sections`를 법령 본문에도 확장 등).
- [x] **cgm_expc 부처명 갱신**: `MINISTRY_CODES`·SERVER_INSTRUCTIONS·도구 설명의 "기획재정부" → "재정경제부"(코드 Moef 유지). 가이드 기준 39개 부처명 재대조.

### P2 — 정리

- [ ] elaw_search `법령명영문` HTML 태그 제거.
- [ ] aiSearch 랭킹: 질의 법령명과 다른 법령(직제 규칙 등) 감점 또는 법령명 필터 인자 추가.
- [ ] check_precedent_odds `<br/>` 정리, outcome 분류 규칙 보강.
- [ ] 0건 응답 형태 통일(`ranked_data`에 빈 리스트와 totalCnt 포함).
- [ ] drlaw_search HTML 표 파싱(소관부처·법령·조문·지자체별 건수) 또는 HTML 전용임을 설명에 명시.
- [ ] 문서 갱신: AGENTS.md(JSON 기본), API_REFERENCE.md(자치법규 구현 반영, 195개 카탈로그, 중앙부처 76개), STATUS/ISSUES(본 점검 결과 반영).
- [ ] 캐시 상한 500 재검토.

## 4. 업스트림(법제처 Open API) 변경 대조

가이드 목록 195개 ID(`openApiGuide` 기준) vs `API_REFERENCE.md` 191개.

### 4.1 신규·변경 확인

- [ ] **신규 분류 "사전컨설팅 의견서"**: `baiPvcs`(감사원 사전컨설팅 의견서 목록/본문). `lawSearch.do?target=baiPvcs&type=JSON` 정상(151건, search=2 본문검색 지원, 응답 루트 `BaiPvcs`). 도구 추가 후보.
- [ ] **부처 명칭 변경 반영**: 가이드 기준 재정경제부(Moef), 기후에너지환경부(Me), 산업통상부(Motie), 성평등가족부(Mogef), 국가데이터처(Kostat), 지식재산처(Kipo), 국가유산청(Khs), 방송미디어통신위원회(kcc). 코드는 기획재정부만 구명칭.
- [ ] **중앙부처 해석 76개 API(39부처)**: 재정경제부·국세청은 목록만 제공(본문 없음).
- [ ] **위원회 12개, 특별행정심판 4개 기관**: 코드 매핑과 일치.
- [ ] 가이드 페이지에 NEW 표시·공지사항 섹션은 없음 → 주기적으로 ID 목록 diff로 감지해야 함(부록 B 스크립트).

### 4.2 미구현 API 중 JSON 동작을 직접 확인한 것 (도구 추가 후보)

| target | 분류 | 확인 결과 |
|---|---|---|
| `lsStmd` | 법령 체계도 목록 | JSON 정상(root `LsStmdSearch`) |
| `oldAndNew` | 신구법 목록 | JSON 정상(root `OldAndNewLawSearch`) |
| `thdCmp` | 3단 비교 목록 | JSON 정상(root `thdCmpLawSearch`) |
| `licbyl` | 법령 별표·서식 목록 | JSON 정상(root `licBylSearch`) |
| `lstrm` | 법령용어 목록(비AI) | JSON 정상(root `LsTrmSearch`) |
| `pi` | 학칙·공단·공공기관 목록 | JSON 정상(root `AdmRulSearch`, section `schlPubRulNm`) |
| `lsHstInf` | 법령 변경이력(regDt) | JSON 정상(root `LawSearch`) |
| `lsJoHstInf` | 조문별 변경 이력(lawService, ID+JO) | JSON 정상 → article_amendment_diff 개선에 활용 |
| `lnkOrd` / `lnkLsOrd` / `lnkOrg` | 자치법규 기준 연계 | JSON 정상 |
| `lsAbrv` | 법률명 약칭 | JSON 정상이나 query/display 무시, 2,714건 전체(2.3MB) 반환 → resolver seed 자동 갱신용으로만 적합 |
| `lsHistory` | 법령 연혁 목록/본문 | **HTML 전용**(type=JSON/XML도 HTML 반환) |

미확인: `admrulOldAndNew`, `oneView`, `datDelHst`, `admrulByl`, `ordinByl`, `lsDayJoRvs`, 모바일 22종, 맞춤형 6종.

## 5. 코드 작업 전 결정이 필요한 사항

- [ ] eflaw 본문 API를 open.law.go.kr에서 추가 신청할지(신청하면 `eflaw_service` 정상화).
- [ ] 지식베이스 연계 4종의 인터페이스: `query`만 유지할지, `mst`/`trm_rlt_cd`/`jo` 인자를 노출할지.
- [ ] `ordinLsCon_search`를 3개 도구로 분리할지 하나로 둘지.
- [ ] 신규 도구 범위: `baiPvcs`(신규 분류), `lsStmd`/`oldAndNew`/`thdCmp`(부가서비스), `licbyl`, `lstrm`, `pi` 중 어디까지 넣을지(도구 수 증가는 PlayMCP 컨텍스트 비용과 상충).
- [ ] 판례 검색 기본값을 사건명(1)에서 본문(2)으로 바꿀지, 아니면 폴백만 추가할지.
- [ ] 알 수 없는 인자에 대해 오류를 낼지(strict) 경고만 낼지.

## 부록 A. 업스트림 직접 확인 방법

등록된 IP에서 다음 형태로 호출한다(한글 query는 반드시 percent-encoding; curl에 한글을 그대로 넣으면 `{}`가 돌아온다).

```python
import urllib.request, urllib.parse
OC = "<OC>"
def call(ep, **p):
    url = f"https://www.law.go.kr/DRF/{ep}?" + urllib.parse.urlencode({"OC": OC, **p})
    return urllib.request.urlopen(url, timeout=40).read().decode("utf-8", "replace")

call("lawSearch.do",  target="moelCgmExpc", type="JSON", query="퇴직", display=2)   # 부처 해석 목록
call("lawService.do", target="lstrmRlt",    type="JSON", query="공정한이용")        # 용어 연계
call("lawService.do", target="joRltLstrm",  type="JSON", query="저작권법", JO="003505")
call("lawSearch.do",  target="lnkOrd",      type="JSON", query="주차장", display=2)
call("lawService.do", target="lsJoHstInf",  type="JSON", ID="000798", JO="003505")
call("lawSearch.do",  target="baiPvcs",     type="JSON", query="계약", search=2, display=2)
```

응답이 0바이트면 target 이름이 틀린 것, `{}`면 인코딩 또는 필수 인자 누락, HTML이면 미신청/HTML 전용/인증 실패 중 하나다.

## 부록 B. 가이드 ID 목록 추출

```bash
curl -s "https://open.law.go.kr/LSO/openApi/guideList.do" \
 | grep -o "openApiGuide('[A-Za-z0-9_]*')" | sort -u > guide_ids_$(date +%F).txt
# 이전 목록과 diff 하여 신규 API 감지
```

2026-10-25 기준 195개. 신규로 확인된 것은 `baiPvcsListGuide`, `baiPvcsInfoGuide`.

## 6. 진행 상황 (2026-10-25 저녁)

- A/B/D 패키지 병합 완료 (v2.2.0). C 패키지(개정 이력·조문 텍스트 추출·판례 검색 범위·시행예정 MST·`date_to` 기본값)는 진행 중.
- 미착수: 대용량 응답 정책(결정 필요), 캐시 상한 재검토, P2 전체.
- 신규 후속 과제: non-SLIM 모드에서 모든 검색 도구가 100건 over-fetch를 `raw_content`에 노출함(display=2에도 약 60KB). `enforce_display`를 `run_search`로 일반화해야 한다.
