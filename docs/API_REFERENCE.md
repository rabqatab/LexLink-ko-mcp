
# 국가법령정보 공동활용 Open API — MCP용 사양서 (LLM-Friendly Markdown)

> **목적:** LLM/에이전트가 그대로 ingest / parse / convert 할 수 있도록 통일된 포맷의 스펙 제공
> **범위:** All 23 implemented MCP tools across Phases 1, 2, and 3
> **Status:** ✅ All 23 APIs implemented and validated (100%)

**Implementation Summary:**
- **Phase 1 (6 tools):** Current laws by effective/announcement date + article/paragraph queries
- **Phase 2 (9 tools):** English laws, administrative rules, law-ordinance linkage, delegated laws
- **Phase 3 (8 tools):** Court precedents, Constitutional Court decisions, legal interpretations, administrative appeals

---

## ⚠️ Known API Provider Issues

**JSON Format Not Supported** (Verified 2025-11-07)
- ❌ **JSON format does NOT work** - All APIs return HTML error pages when \`type=JSON\` is requested
- ✅ **XML format WORKS** - Confirmed working on all endpoints
- ✅ **HTML format WORKS** - Confirmed working
- 📄 **See:** \`reference/07_api_provider_issues.md\` for full details

**Use XML format for all requests** until the API provider fixes JSON support.

---

## 공통 규칙
- 모든 엔드포인트는 **HTTP GET**
- 요청 파라미터는 **snake_case**로 재기술(원문도 병기)
- 스키마는 **YAML 블록**으로 제공 (LLM 파싱 친화)
- 샘플 URL은 **코드블록**으로 제공
- 응답 스키마는 **필드명 통일**(가능한 한 중복/동의어 정규화)
- request parameters의 OC parameter는 test 시 **ddongle0205**로 사용할 것
- **Response format:** Use \`type=XML\` (default) - JSON is documented but not supported by API

---

# Phase 1: Core Law APIs (6 tools)

## 1) 현행법령(시행일) 목록 조회 API
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=eflaw`

### Request Parameters
```yaml
# 원문 파라미터 → snake_case 재기술
oc: string (required)            # OC: 사용자 이메일 ID (g4c@korea.kr → g4c)
target: "eflaw" (required)       # target: eflaw
type: HTML | XML | JSON          # type (default XML)
search: int                      # search: 1=법령명(기본), 2=본문검색
query: string                    # query: 검색어 (예: "자동차")
nw: [1|2|3|csv]                  # nw: 1=연혁, 2=시행예정, 3=현행 (복수 가능: 1,2,3)
lid: string                      # LID: 법령ID
display: int                     # display: default 20, max 100
page: int                        # page: default 1
sort: string                     # sort: lasc|ldes|dasc|ddes|nasc|ndes|efasc|efdes
ef_yd: string                    # efYd: 시행일자 범위 (YYYYMMDD~YYYYMMDD)
date: string                     # date: 공포일자
anc_yd: string                   # ancYd: 공포일자 범위
anc_no: string                   # ancNo: 공포번호 범위
rr_cls_cd: string                # rrClsCd: 제개정 종류 코드
nb: int                          # nb: 공포번호
org: string                      # org: 소관부처 코드
knd: string                      # knd: 법령 종류
gana: string                     # gana: 사전식 검색 (ga,na,da…)
pop_yn: "Y" | "N"                # popYn: 팝업 여부
```

### Sample URLs
```text
1) XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=XML

2) HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=HTML

3) JSON
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=JSON

4) 검색: 자동차관리법
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&query=자동차관리법

5) 공포일자 내림차순
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=XML&sort=ddes

6) 국토교통부 소관
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=XML&org=1613000

7) LID=830
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=eflaw&type=XML&LID=830
```

### Response Schema (normalized)
```yaml
target: string
keyword: string
section: string
total_count: int
page: int
law_id: int                  # 결과 번호(리스트 내 식별자)
law_seq: int                 # 법령일련번호
status_code: string          # 현행연혁코드
law_name_kr: string          # 법령명(한글)
law_abbrev_name: string      # 약칭
law_id_num: int              # 법령ID
announce_date: int           # 공포일자 (YYYYMMDD)
announce_no: int             # 공포번호
revision_type: string        # 제개정구분명
ministry_code: string        # 소관부처코드
ministry_name: string        # 소관부처명
law_type: string             # 법령구분명
joint_regu_flag: string      # 공동부령구분
joint_regu_announce_no: string  # 공동부령 공포번호
effective_date: int          # 시행일자 (YYYYMMDD)
sub_law_flag: string         # 자법/타법 여부
law_detail_link: string      # 상세링크
```

---

## 2) 현행법령(시행일) 본문 조회 API
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=eflaw`

### Request Parameters
```yaml
oc: string (required)
target: "eflaw" (required)
type: HTML | XML | JSON
id: string                     # ID (법령ID) 또는 mst 중 하나 필수
mst: string                    # MST (lsi_seq)
ef_yd: int                     # 시행일자 (ID 사용시 미사용)
jo: string                     # 조번호 6자리(예: 000200, 001002)
chr_cls_cd: "010202" | "010201"  # 한글/원문 (기본 한글; 010202=한글, 010201=원문)
```

### Sample URLs
```text
1) ID 기반 HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflaw&ID=1747&type=HTML

2) MST + 시행일자 XML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflaw&MST=166520&efYd=20151007&type=XML

3) 특정 조만 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflaw&MST=166520&efYd=20151007&JO=000300&type=XML

4) ID 기반 JSON
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflaw&ID=1747&type=JSON
```

### Response Schema (normalized; 반복 배열 포함)
```yaml
law_id: int
announce_date: int
announce_no: int
language: string
law_category: string
law_category_code: string
law_name_kr: string
law_name_chn: string
law_name_abbrev: string
chapter_seq: int
ministry_code: int
ministry_name: string
phone: string
effective_date: int
revision_type: string
article_effective_date_str: string
appendix_effective_date_str: string
appendix_edit_flag: string
official_law_flag: string
department_name: string
department_contact: string
joint_regu_flag: string
joint_regu_code: string
joint_regu_announce_no: string

articles:                    # 반복 구조
  - article_no: int
    article_branch_no: int
    is_article: string
    article_title: string
    article_effective_date: int
    article_revision_type: string
    article_move_prev: int
    article_move_next: int
    article_changed_flag: string
    article_content: string
    paragraphs:
      - paragraph_no: int
        paragraph_content: string
        items:
          - item_no: int
            item_content: string
            subitems:
              - subitem_no: string
                subitem_content: string
```

---

## 3) 현행법령(공포일) 목록 조회 API
**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=law`

### Request Parameters
```yaml
oc: string (required)
target: "law" (required)
type: HTML | XML | JSON
search: int
query: string
display: int
page: int
sort: string
date: int
ef_yd: string
anc_yd: string
anc_no: string
rr_cls_cd: string
nb: int
org: string
knd: string
ls_chap_no: string
gana: string
pop_yn: "Y" | "N"
```

### Sample URLs
```text
1) XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML

2) HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=HTML

3) JSON
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=JSON

4) 검색: 자동차관리법
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=XML&query=자동차관리법
```

### Response Schema (normalized)
```yaml
target: string
keyword: string
section: string
total_count: int
page: int
law_id: int
law_seq: int
status_code: string
law_name_kr: string
law_abbrev_name: string
law_id_num: int
announce_date: int
announce_no: int
revision_type: string
ministry_name: string
ministry_code: int
law_type: string
joint_regu_flag: string
joint_regu_announce_no: string
effective_date: int
sub_law_flag: string
law_detail_link: string
```

---

## 4) 현행법령(공포일) 본문 조회 API
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=law`

### Request Parameters
```yaml
oc: string (required)
target: "law" (required)
type: HTML | XML | JSON
id: string
mst: string
lm: string
ld: int
ln: int
jo: string
lang: "KO" | "ORI"
```

### Sample URLs
```text
1) ID HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&ID=009682&type=HTML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&MST=261457&type=HTML

2) XML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&ID=009682&type=XML
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&MST=261457&type=XML

3) JSON
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&ID=009682&type=JSON
http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&MST=261457&type=JSON
```

### Response Schema (normalized; 반복 배열 포함)
```yaml
law_id: int
announce_date: int
announce_no: int
language: string
law_category: string
law_category_code: string
law_name_kr: string
law_name_chn: string
law_name_abbrev: string
title_changed_flag: string
is_korean_law: string
chapter_seq: int
ministry_code: int
ministry_name: string
phone: string
effective_date: int
revision_type: string
appendix_edit_flag: string
official_law_flag: string
department_name: string
department_contact: string
joint_regu_flag: string
joint_regu_code: string
joint_regu_announce_no: string

articles:
  - article_no: int
    article_branch_no: int
    is_article: string
    article_title: string
    article_effective_date: string
    article_move_prev: int
    article_move_next: int
    article_changed_flag: string
    article_content: string
    paragraphs:
      - paragraph_no: int
        paragraph_content: string
        items:
          - item_no: int
            item_content: string
            subitems:
              - subitem_no: string
                subitem_content: string
```

---

## 5) 현행법령(시행일) 본문 조항·항·호·목 조회 API
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=eflawjosub`

### Request Parameters
```yaml
oc: string (required)
target: "eflawjosub" (required)
type: HTML | XML | JSON
id: string
mst: string
ef_yd: int                # 시행일자
jo: string                # 조 (6자리)
hang: string              # 항 (6자리)
ho: string                # 호 (6자리)
mok: string               # 목 (UTF-8 인코딩 필요)
```

### Sample URLs
```text
http://www.law.go.kr/DRF/lawService.do?OC=test&target=eflawjosub&type=XML&MST=193412&efYd=20171019&JO=000300&HANG=000100&HO=000200&MOK=다
```

### Response Schema (normalized)
```yaml
law_key: int
law_id: int
announce_date: int
announce_no: int
language: string
law_category: string
law_category_code: string
law_name_kr: string
law_name_chn: string
law_name_en: string
chapter_seq: int
ministry_code: int
ministry_name: string
phone: string
effective_date: int
revision_type: string
proposal_type: string
decision_type: string
apply_start_date: string
apply_end_date: string
previous_law_name: string
article_effective_date_str: string
appendix_effective_date_str: string
appendix_edit_flag: string
official_law_flag: string

article_no: int
is_article: string
article_title: string
article_effective_date: string
article_move_prev: int
article_move_next: int
article_changed_flag: string
article_content: string

paragraph_no: int
paragraph_content: string

item_no: int
item_content: string

subitem_no: string
subitem_content: string
```

---

## 6) 현행법령(공포일) 본문 조항·항·호·목 조회 API
**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lawjosub`

### Request Parameters
```yaml
oc: string (required)
target: "lawjosub" (required)
type: HTML | XML | JSON
id: string
mst: string
jo: string
hang: string
ho: string
mok: string
```

### Sample URLs
```text
http://www.law.go.kr/DRF/lawService.do?OC=test&target=lawjosub&type=XML&ID=001823&JO=000300&HANG=000100&HO=000200&MOK=다
```

### Response Schema (normalized)
```yaml
law_key: int
law_id: int
announce_date: int
announce_no: int
language: string
law_name_kr: string
law_name_chn: string
law_category_code: string
law_category_name: string
title_changed_flag: string
is_korean_law: string
chapter_seq: int
ministry_code: int
ministry_name: string
phone: string
effective_date: int
revision_type: string
proposal_type: string
decision_type: string
previous_law_name: string
article_effective_date: string
article_effective_date_str: string
appendix_effective_date_str: string
appendix_edit_flag: string
official_law_flag: string
edited_by_effective_date_flag: string

article_no: int
is_article: string
article_title: string
article_effective_date: string
article_move_prev: int
article_move_next: int
article_changed_flag: string
article_content: string

paragraph_no: int
paragraph_content: string

item_no: int
item_content: string

subitem_no: string
subitem_content: string
```


## X) 영문법령 목록 조회 API (elaw)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=elaw`

### Request Parameters
```yaml
# 원문 파라미터 → snake_case 재기술
oc: string (required)                  # OC: 사용자 이메일 ID (예: g4c@korea.kr → g4c)
target: "elaw" (required)              # target: elaw
type: HTML | XML | JSON                # type: 출력형식 (기본 XML)
search: int                            # search: 1=법령명(기본), 2=본문검색
query: string                          # query: 검색어(default=*)
display: int                           # display: 결과 개수 (default 20, max 100)
page: int                              # page: 페이지 번호 (default 1)
sort: string                           # sort: lasc|ldes|dasc|ddes|nasc|ndes|efasc|efdes
date: int                              # date: 공포일자
ef_yd: string                          # efYd: 시행일자 범위 (예: 20090101~20090130)
anc_yd: string                         # ancYd: 공포일자 범위
anc_no: string                         # ancNo: 공포번호 범위 (예: 306~400)
rr_cls_cd: string                      # rrClsCd: 제개정 종류 코드
nb: int                                # nb: 공포번호 검색
org: string                            # org: 소관부처 코드
knd: string                            # knd: 법령종류 코드
gana: string                           # gana: 사전식 검색 (ga,na,da…)
pop_yn: "Y" | "N"                      # popYn: 팝업 여부
```

### Sample URLs
```text
1) XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=XML

2) HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=HTML

3) JSON
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=JSON

4) 검색어 예시 (가정폭력방지)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=XML&query=가정폭력방지

5) 검색어 예시 (insurance)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=elaw&type=XML&query=insurance
```

### Response Schema (normalized)
```yaml
target: string                 # 검색서비스 대상
keyword: string                # 검색어
section: string                # 검색범위
total_count: int               # 검색건수
page: int                      # 페이지 번호
law_id: int                    # 결과 번호
law_seq_no: int                # 법령일련번호
history_code: string           # 현행연혁코드
law_name_kr: string            # 법령명(한글)
law_name_en: string            # 법령명(영문)
law_no: int                    # 법령ID
announce_date: int             # 공포일자
announce_no: int               # 공포번호
revision_type: string          # 제개정구분명
ministry_name: string          # 소관부처명
law_type: string               # 법령구분명
effective_date: int            # 시행일자
parent_child_flag: string      # 자법/타법 여부
detail_link: string            # 법령 상세 링크
```

## X) 영문법령 본문 조회 API (elaw)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=elaw`

### Request Parameters
```yaml
# 원문 파라미터 → snake_case 재기술
oc: string (required)                # OC: 사용자 이메일 ID (예: g4c@korea.kr → g4c)
target: "elaw" (required)            # target: elaw
id: string                           # ID: 법령 ID (ID 또는 MST 중 하나 필수)
mst: string                          # MST: 법령 마스터 번호(lsi_seq)
lm: string                           # LM: 법령명 (법령명 입력 시 해당 법령 링크)
ld: int                              # LD: 공포일자
ln: int                              # LN: 공포번호
type: HTML | XML | JSON              # type: 출력 형식
```

### Sample URLs
```text
1) 법령 ID HTML 조회 (표준시에 관한 법률)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=elaw&ID=000744&type=HTML

2) 법령 마스터 번호 XML 조회 (상호저축은행법 시행령)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=elaw&MST=127280&type=XML

3) 법령 마스터 번호 JSON 조회 (상호저축은행법 시행령)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=elaw&MST=127280&type=JSON
```





## X) 법령-자치법규 연계 목록 조회 API (lnkLs)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkLs`

### Request Parameters
```yaml
oc: string (required)                # OC: 사용자 이메일 ID
target: "lnkLs" (required)           # target: lnkLs
type: HTML | XML | JSON (required)   # type: 출력형식
query: string                        # query: 검색어
display: int                         # display: 결과 개수 (default 20, max 100)
page: int                            # page: 페이지 번호 (default 1)
sort: string                         # sort: lasc|ldes|dasc|ddes|nasc|ndes
pop_yn: "Y" | "N"                    # popYn: 팝업 여부
```

### Sample URLs
```text
1) XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLs&type=XML

2) HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLs&type=HTML

3) JSON
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLs&type=JSON

4) 검색어 예시: 자동차관리법
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLs&type=XML&query=자동차관리법
```

### Response Schema (normalized)
```yaml
target: string
keyword: string
section: string
total_count: int
page: int
law_id: int
law_seq_no: int                # 법령일련번호
law_name_kr: string           # 법령명(한글)
law_no: int                   # 법령ID
announce_date: int            # 공포일자
announce_no: int              # 공포번호
revision_type: string         # 제개정구분명
law_type: string              # 법령구분명
effective_date: int           # 시행일자
```

---

## X) 연계 법령별 조례 조문 목록 조회 API (lnkLsOrdJo)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkLsOrdJo`

### Request Parameters
```yaml
oc: string (required)                    # OC
target: "lnkLsOrdJo" (required)          # target
type: HTML | XML | JSON (required)       # type
query: string                             # query
display: int                              # display: default 20, max 100
page: int                                 # page
sort: string                              # sort: lasc|ldes|dasc|ddes|nasc|ndes
knd: string                               # knd: 법령종류 코드
jo: int                                   # JO: 조번호 (4자리, 예: 0020)
jobr: int                                 # JOBR: 조가지번호 (2자리, 예: 02)
pop_yn: "Y" | "N"                         # popYn
```

### Sample URLs
```text
1) XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=XML

2) HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=HTML

3) JSON
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=JSON

4) 법령 검색: 건축법 시행령
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=XML&knd=002118

5) 조문 검색: 건축법 시행령 제20조
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkLsOrdJo&type=XML&knd=002118&JO=0020
```

### Response Schema (normalized)
```yaml
target: string
keyword: string
section: string
total_count: int
page: int
law_id: int
law_name_kr: string                # 법령명
law_no: int                        # 법령ID
law_article_no: string             # 법령 조번호

 ordinance_seq_no: int            # 자치법규 일련번호
 ordinance_name: string            # 자치법규명
 ordinance_article_no: string      # 자치법규 조번호
 ordinance_id: int                 # 자치법규ID
 ordinance_announce_date: int      # 공포일자
 ordinance_announce_no: int        # 공포번호
 ordinance_revision_type: string   # 제개정구분명
 ordinance_type: string            # 자치법규종류
 ordinance_effective_date: int     # 시행일자
```

---

## X) 연계 법령 소관부처별 목록 조회 API (lnkDep)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=lnkDep`

### Request Parameters
```yaml
oc: string (required)                 # OC
target: "lnkDep" (required)           # target
type: HTML | XML | JSON (required)    # type
display: int                          # display: default 20, max 100
page: int                             # page
org: string                           # org: 소관부처 코드
sort: string                          # sort: lasc|ldes|dasc|ddes|nasc|ndes
pop_yn: "Y" | "N"                     # popYn
```

### Sample URLs
```text
1) XML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkDep&org=1400000&type=XML

2) HTML
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkDep&org=1400000&type=HTML

3) JSON
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=lnkDep&org=1400000&type=JSON
```

### Response Schema (normalized)
```yaml
target: string
section: string
total_count: int
page: int
law_id: int
law_name_kr: string                    # 법령명
law_no: int                            # 법령ID

 ordinance_seq_no: int                # 자치법규 일련번호
 ordinance_name: string                # 자치법규명
 ordinance_id: int                     # 자치법규ID
 ordinance_announce_date: int          # 공포일자
 ordinance_announce_no: int            # 공포번호
 ordinance_revision_type: string       # 제개정구분명
 ordinance_type: string                # 자치법규종류
 ordinance_effective_date: int         # 시행일자
```


## X) 법령-자치법규 연계현황 조회 API (drlaw)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=drlaw`

### Request Parameters
```yaml
oc: string (required)                # OC: 사용자 이메일 ID
target: "drlaw" (required)           # target: drlaw
type: HTML (required)                # type: HTML 출력만 지원
```

### Sample URLs
```text
1) 연계현황 조회 (HTML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=drlaw&type=HTML
```

### Response Schema
```yaml
# ⚠️ 공식 스펙에 출력 필드 정보가 제공되지 않음
# API provider documentation does not define response fields for this endpoint.
```



## X) 위임 법령 조회 API (lsDelegated)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=lsDelegated`

### Request Parameters
```yaml
oc: string (required)                 # OC: 사용자 이메일 ID (예: g4c@korea.kr → g4c)
target: "lsDelegated" (required)      # target: lsDelegated
type: XML | JSON (required)           # type: 출력 형식
id: string                            # ID: 법령 ID (ID 또는 MST 중 하나는 필수)
mst: string                           # MST: 법령 마스터 번호(lsi_seq)
```

### Sample URLs
```text
1) XML (초·중등교육법)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=lsDelegated&type=XML&ID=000900

2) JSON (초·중등교육법)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=lsDelegated&type=JSON&ID=000900
```

### Response Schema (normalized)
```yaml
# 법령 기본 정보
law_seq_no: int                      # 법령일련번호
law_name_kr: string                  # 법령명
law_no: int                          # 법령ID
announce_date: int                   # 공포일자 (YYYYMMDD)
announce_no: int                     # 공포번호
ministry_code: int                   # 소관부처코드
phone: string                        # 전화번호
effective_date: int                  # 시행일자 (YYYYMMDD)

# 위임 근거 조문
article_no: string                   # 조문번호
article_title: string                # 조문제목
delegation_type: string              # 위임구분 (위임된 법령의 종류)

# 위임된 "법령" 상세 (자법/타법 등 상위 법령)
delegated_law_seq_no: string         # 위임법령일련번호
delegated_law_title: string          # 위임법령제목
delegated_law_article_no: string     # 위임법령조문번호
delegated_law_article_branch_no: string  # 위임법령조문가지번호
delegated_law_article_title: string  # 위임법령조문제목
delegated_law_link_text: string      # 링크텍스트 (위임된 법령에 대한 링크 텍스트)
delegated_law_line_text: string      # 라인텍스트 (링크텍스트 포함 조문내용)
delegated_law_hierarchy: string      # 조항호목 (링크/라인텍스트 포함 계층 문자열)

# 위임된 "행정규칙" 상세
delegated_rule_seq_no: string        # 위임행정규칙일련번호
delegated_rule_title: string         # 위임행정규칙제목
delegated_rule_link_text: string     # 링크텍스트
delegated_rule_line_text: string     # 라인텍스트
delegated_rule_hierarchy: string     # 조항호목

# 위임된 "자치법규" 상세
delegated_ordinance_seq_no: string   # 위임자치법규일련번호
delegated_ordinance_title: string    # 위임자치법규제목
delegated_ordinance_link_text: string  # 링크텍스트
delegated_ordinance_line_text: string  # 라인텍스트
delegated_ordinance_hierarchy: string  # 조항호목
```


## X) 행정규칙 목록 조회 API (admrul)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=admrul`

### Request Parameters
```yaml
oc: string (required)                     # OC: 사용자 이메일 ID (예: g4c@korea.kr → g4c)
target: "admrul" (required)               # target: admrul
type: HTML | XML | JSON (required)        # type: 출력 형식
nw: int                                   # nw: 1=현행, 2=연혁 (default=1)
search: int                               # search: 1=행정규칙명(기본), 2=본문검색
query: string                             # query: 검색어 (예: "자동차")
display: int                              # display: 결과 개수 (default 20, max 100)
page: int                                 # page: 결과 페이지 (default 1)
org: string                               # org: 소관부처 코드
knd: string                               # knd: 1=훈령, 2=예규, 3=고시, 4=공고, 5=지침, 6=기타
gana: string                              # gana: 사전식 검색 (ga, na, da, …)
sort: string                              # sort: lasc|ldes|dasc|ddes|nasc|ndes|efasc|efdes
date: int                                 # date: 발령일자(YYYYMMDD)
prml_yd: string                           # prmlYd: 발령일자 기간 (YYYYMMDD~YYYYMMDD)
mod_yd: string                            # modYd: 수정일자 기간 (YYYYMMDD~YYYYMMDD)
nb: int                                   # nb: 발령번호 (예: 제2023-8호 → 20238)
pop_yn: "Y" | "N"                         # popYn: 팝업 여부
```

### Sample URLs
```text
1) HTML 목록 조회 (키워드=학교)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=admrul&query=학교&type=HTML

2) XML 목록 조회 (발령일자=2025-05-01)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=admrul&date=20250501&type=XML

3) JSON 목록 조회 (발령일자=2025-05-01)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=admrul&date=20250501&type=JSON
```

### Response Schema (normalized)
```yaml
target: string                     # 검색 서비스 대상
keyword: string                    # 검색어
section: string                    # 검색 범위
total_count: int                   # 검색 건수
page: int                          # 결과 페이지 번호
admrul_id: int                     # 결과 번호 (row id)

rule_seq_no: int                   # 행정규칙 일련번호
rule_name: string                  # 행정규칙명
rule_type: string                  # 행정규칙 종류
promulgation_date: int             # 발령일자 (YYYYMMDD)
promulgation_no: int               # 발령번호
ministry_name: string              # 소관부처명
current_history_flag: string       # 현행/연혁 구분
revision_code: string              # 제개정 구분 코드
revision_name: string              # 제개정 구분명
rule_id: int                       # 행정규칙ID
rule_detail_link: string           # 행정규칙 상세 링크
effective_date: int                # 시행일자 (YYYYMMDD)
created_date: int                  # 생성일자 (YYYYMMDD)
```



## X) 행정규칙 본문 조회 API (admrul)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=admrul`

### Request Parameters
```yaml
oc: string (required)                 # OC: 사용자 이메일 ID (예: g4c@korea.kr → g4c)
target: "admrul" (required)           # target: admrul
type: HTML | XML | JSON (required)    # type: 출력 형식
id: string                            # ID: 행정규칙 일련번호
lid: string                           # LID: 행정규칙 ID
lm: string                            # LM: 행정규칙명 (정확 매칭 검색)
```

### Sample URLs
```text
1) HTML 상세조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=admrul&ID=62505&type=HTML

2) XML 상세조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=admrul&ID=10000005747&type=XML

3) JSON 상세조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=admrul&ID=2000000091702&type=JSON
```

### Response Schema (normalized)
```yaml
# 기본 정보
rule_seq_no: int                      # 행정규칙일련번호
rule_name: string                     # 행정규칙명
rule_type: string                     # 행정규칙종류
rule_type_code: string                # 행정규칙종류코드
promulgation_date: int                # 발령일자 (YYYYMMDD)
promulgation_no: string               # 발령번호 (예: 제2023-8호 → 문자열 권장)
revision_name: string                 # 제개정구분명
revision_code: string                 # 제개정구분코드
article_format_flag: string           # 조문형식여부 (Y/N 등)
rule_id: int                          # 행정규칙ID
ministry_name: string                 # 소관부처명
ministry_code: string                 # 소관부처코드
parent_ministry_name: string          # 상위부처명
dept_org_code: string                 # 담당부서기관코드
dept_org_name: string                 # 담당부서기관명
manager_name: string                  # 담당자명
phone: string                         # 전화번호
current_flag: string                  # 현행여부 (Y/N 등)
effective_date: string                # 시행일자 (YYYYMMDD)
created_date: string                  # 생성일자 (YYYYMMDD)

# 본문/부칙
article_content: string               # 조문내용
addendum: string                      # 부칙
addendum_announce_date: int           # 부칙공포일자 (YYYYMMDD)
addendum_announce_no: int             # 부칙공포번호
addendum_content: string              # 부칙내용

# 별표(annex)
annex: string                         # 별표
annex_no: int                         # 별표번호
annex_branch_no: int                  # 별표가지번호
annex_type: string                    # 별표구분
annex_title: string                   # 별표제목
annex_form_file_link: string          # 별표서식파일링크
annex_form_pdf_link: string           # 별표서식PDF파일링크
annex_content: string                 # 별표내용
```

---

# Phase 3: Case Law & Legal Research APIs (8 tools)


## X) 판례 목록 조회 API (prec)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=prec`

### Request Parameters
```yaml
oc: string (required)                     # OC: 사용자 이메일 ID
target: "prec" (required)                 # target: prec
type: HTML | XML | JSON (required)        # type: 출력 형식

search: int                               # search: 1=판례명(기본), 2=본문검색
query: string                             # query: 검색어 (예: "자동차")
display: int                              # display: 결과 개수 (default 20, max 100)
page: int                                 # page: 결과 페이지 (default 1)

org: string                               # org: 법원종류코드 (대법원:400201, 하위법원:400202)
curt: string                              # curt: 법원명 (대법원, 서울고등법원 등)
jo: string                                # JO: 참조법령명 (형법, 민법 등)
gana: string                              # gana: 사전식 검색 (ga, na, da, …)

sort: string                              # sort: lasc|ldes|dasc|ddes|nasc|ndes
date: int                                 # date: 선고일자 (YYYYMMDD)
prnc_yd: string                           # prncYd: 선고일자 기간 (YYYYMMDD~YYYYMMDD)
nb: string                                # nb: 사건번호 (콤마로 여러 개 전달 가능)
dat_src_nm: string                        # datSrcNm: 데이터출처명
                                          # (국세법령정보시스템, 근로복지공단산재판례, 대법원)
pop_yn: "Y" | "N"                         # popYn: 팝업 여부
```

### Sample URLs
```text
1) 사건명에 '담보권'이 들어가는 판례 목록 (XML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=XML&query=담보권

2) 사건명에 '담보권' + 법원이 '대법원'인 판례 목록 (HTML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=HTML&query=담보권&curt=대법원

3) 사건번호가 '2009느합133,2010느합21' 인 판례 목록 (HTML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=HTML&nb=2009느합133,2010느합21

4) 데이터출처가 근로복지공단산재판례인 판례 목록 (JSON)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&type=JSON&datSrcNm=근로복지공단산재판례
```

### Response Schema (normalized)
```yaml
target: string                       # 검색 대상
promulgation_no: string              # 공포번호 (원문 필드명 그대로 존재)
keyword: string                      # 검색어
section: string                      # 검색범위 (EvtNm=판례명, bdyText=본문)
total_count: int                     # 검색결과갯수
page: int                            # 출력페이지
prec_id: int                         # 검색결과번호

precedent_seq_no: int                # 판례일련번호
case_name: string                    # 사건명
case_no: string                      # 사건번호
decision_date: string                # 선고일자 (YYYYMMDD 또는 YYYY-MM-DD)
court_name: string                   # 법원명
court_type_code: int                 # 법원종류코드 (대법원:400201, 하위법원:400202)
case_type_name: string               # 사건종류명
case_type_code: int                  # 사건종류코드
judgment_type: string                # 판결유형
decision: string                     # 선고 (예: "상고기각" 등)
data_source_name: string             # 데이터출처명
precedent_detail_link: string        # 판례상세링크
```

----


## X) 판례 본문 조회 API (prec)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=prec`

### Request Parameters
```yaml
oc: string (required)                    # OC: 사용자 이메일 ID
target: "prec" (required)                # target: prec
type: HTML | XML | JSON (required)       # type: 출력 형식
                                         #   * 국세청 판례 본문 조회는 HTML만 가능

id: string (required)                    # ID: 판례 일련번호
lm: string                               # LM: 판례명
```

### Sample URLs
```text
1) 판례일련번호 228541 HTML 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=prec&ID=228541&type=HTML

2) 판례일련번호 228541 XML 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=prec&ID=228541&type=XML

3) 판례일련번호 228541 JSON 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=prec&ID=228541&type=JSON
```

### Response Schema (normalized)
```yaml
precedent_info_seq_no: int          # 판례정보일련번호
case_name: string                   # 사건명
case_no: string                     # 사건번호
decision_date: int                  # 선고일자 (YYYYMMDD)
decision: string                    # 선고 (예: 상고기각 등)
court_name: string                  # 법원명
court_type_code: int                # 법원종류코드 (대법원:400201, 하위법원:400202)
case_type_name: string              # 사건종류명
case_type_code: int                 # 사건종류코드
judgment_type: string               # 판결유형
issues: string                      # 판시사항
summary: string                     # 판결요지
referenced_articles: string         # 참조조문
referenced_precedents: string       # 참조판례
content: string                     # 판례내용 (전체 본문)
```


---


## X) 헌재결정례 목록 조회 API (detc)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=detc`

### Request Parameters
```yaml
oc: string (required)                     # OC: 사용자 이메일 ID
target: "detc" (required)                 # target: detc
type: HTML | XML | JSON (required)        # type: 출력 형식

search: int                               # search: 1=헌재결정례명(기본), 2=본문검색
query: string                             # query: 검색어
display: int                              # display: 결과 개수 (default 20, max 100)
page: int                                 # page: 페이지 번호 (default 1)

gana: string                              # gana: 사전식 검색 (ga, na, da, …)

sort: string                              # sort: lasc|ldes|dasc|ddes|nasc|ndes|efasc|efdes
date: int                                 # date: 종국일자
ed_yd: string                             # edYd: 종국일자 기간 검색 (YYYYMMDD~YYYYMMDD)
nb: int                                   # nb: 사건번호

pop_yn: "Y" | "N"                         # popYn: 팝업 여부
```

### Sample URLs
```text
1) 사건명에 '벌금' 포함 (XML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=detc&type=XML&query=벌금

2) 종국일자 = 2015-02-10 (HTML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=detc&type=HTML&date=20150210

3) 사건명에 '자동차' 포함 (XML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=detc&type=XML&query=자동차

4) 사건명에 '자동차' 포함 (JSON)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=detc&type=JSON&query=자동차
```

### Response Schema (normalized)
```yaml
target: string                         # 검색 대상
keyword: string                        # 검색 키워드
section: string                        # 검색범위 (EvtNm=헌재결정례명, bdyText=본문)
total_count: int                       # 검색결과 갯수
page: int                              # 페이지 번호
detc_id: int                           # 검색결과번호

decision_seq_no: int                   # 헌재결정례일련번호
final_date: string                     # 종국일자 (YYYYMMDD 또는 YYYY-MM-DD)
case_no: string                        # 사건번호
case_name: string                      # 사건명
decision_detail_link: string           # 헌재결정례 상세링크
```

---

헌재결정례 본문 조회 API
- 요청 URL : http://www.law.go.kr/DRF/lawService.do?target=detc
요청 변수 (request parameter)
요청변수	값	설명
OC	string(필수)	사용자 이메일의 ID(g4c@korea.kr일경우 OC값=g4c)
target	string : detc(필수)	서비스 대상
type	char(필수)	출력 형태 : HTML/XML/JSON
ID	char(필수)	헌재결정례 일련번호
LM	string	헌재결정례명
샘플 URL
1. 헌재결정례 일련번호가 58386인 헌재결정례 HTML 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=detc&ID=58386&type=HTML
2. 자동차관리법제26조등위헌확인등 헌재결정례 XML 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=detc&ID=127830&LM=자동차관리법제26조등위헌확인등&type=XML
3. 헌재결정례 일련번호가 58400인 헌재결정례 JSON 조회
http://www.law.go.kr/DRF/lawService.do?OC=test&target=detc&ID=58400&type=JSON
출력 결과 필드(response field)
필드	값	설명
헌재결정례일련번호	int	헌재결정례일련번호
종국일자	int	종국일자
사건번호	string	사건번호
사건명	string	사건명
사건종류명	string	사건종류명
사건종류코드	int	사건종류코드
재판부구분코드	int	재판부구분코드(전원재판부:430201, 지정재판부:430202)
판시사항	string	판시사항
결정요지	string	결정요지
전문	string	전문
참조조문	string	참조조문
참조판례	string	참조판례
심판대상조문	string	심판대상조문


---


## X) 법령해석례 목록 조회 API (expc)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=expc`

### Request Parameters
```yaml
oc: string (required)                     # OC: 사용자 이메일 ID
target: "expc" (required)                 # target: expc
type: HTML | XML | JSON (required)        # type: 출력 형식

search: int                               # search: 1=법령해석례명(기본), 2=본문검색
query: string                             # query: 검색어
display: int                              # display: 결과 개수 (default 20, max 100)
page: int                                 # page: 결과 페이지 (default 1)

inq: string                               # inq: 질의기관
rpl: int                                  # rpl: 회신기관
gana: string                              # gana: 사전식 검색 (ga, na, da, …)

itmno: int                                # itmno: 안건번호 (예: 13-0217 → 130217)
reg_yd: string                            # regYd: 등록일자 기간 (YYYYMMDD~YYYYMMDD)
expl_yd: string                           # explYd: 해석일자 기간 (YYYYMMDD~YYYYMMDD)

sort: string                              # sort: lasc|ldes|dasc|ddes|nasc|ndes
pop_yn: "Y" | "N"                         # popYn: 팝업 여부
```

### Sample URLs
```text
1) 안건명에 '임차' 포함 (XML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=expc&type=XML&query=임차

2) 안건명에 '주차' 포함 (HTML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=expc&type=HTML&query=주차

3) 안건명에 '자동차' 포함 (JSON)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=expc&type=JSON&query=자동차
```

### Response Schema (normalized)
```yaml
target: string                           # 검색 대상
keyword: string                          # 키워드
section: string                          # 검색범위 (lawNm=법령해석례명, bdyText=본문)
total_count: int                         # 검색결과갯수
page: int                                # 출력페이지
expc_id: int                             # 검색결과번호

interpretation_seq_no: int               # 법령해석례일련번호
item_name: string                        # 안건명
item_no: string                          # 안건번호

inquiry_org_code: int                    # 질의기관코드
inquiry_org_name: string                 # 질의기관명
reply_org_code: string                   # 회신기관코드
reply_org_name: string                   # 회신기관명
reply_date: string                       # 회신일자 (YYYYMMDD 등)

interpretation_detail_link: string       # 법령해석례 상세링크
```


---


## X) 법령해석례 본문 조회 API (expc)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=expc`

### Request Parameters
```yaml
oc: string (required)                 # OC: 사용자 이메일 ID
target: "expc" (required)             # target: expc
type: HTML | XML | JSON (required)    # type: 출력 형식

id: int (required)                    # ID: 법령해석례 일련번호
lm: string                            # LM: 법령해석례명
```

### Sample URLs
```text
1) 법령해석례일련번호 333827 (HTML)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=expc&ID=334617&type=HTML

2) 여성가족부 - 건강가정기본법 제35조 제2항 관련 (XML)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=expc&ID=315191&LM=여성가족부 - 건강가정기본법 제35조 제2항 관련&type=XML

3) 법령해석례일련번호 330471 (JSON)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=expc&ID=330471&type=JSON
```

### Response Schema (normalized)
```yaml
interpretation_seq_no: int        # 법령해석례일련번호
item_name: string                 # 안건명
item_no: string                   # 안건번호
interpretation_date: int          # 해석일자 (YYYYMMDD)

interpretation_org_code: int      # 해석기관코드
interpretation_org_name: string   # 해석기관명
inquiry_org_code: int             # 질의기관코드
inquiry_org_name: string          # 질의기관명

managing_org_code: int            # 관리기관코드
registered_datetime: int          # 등록일시 (YYYYMMDDhhmmss 등)

question_summary: string          # 질의요지
answer: string                    # 회답
reason: string                    # 이유
```

---


## X) 행정심판례 목록 조회 API (decc)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawSearch.do?target=decc`

### Request Parameters
```yaml
oc: string (required)                     # OC: 사용자 이메일 ID
target: "decc" (required)                 # target: decc
type: HTML | XML | JSON (required)        # type: 출력 형식

search: int                               # search: 1=행정심판례명(기본), 2=본문검색
query: string                             # query: 검색어
display: int                              # display: 결과 개수 (default 20, max 100)
page: int                                 # page: 결과 페이지 (default 1)

cls: string                               # cls: 재결례유형 (재결구분코드와 연동)
gana: string                              # gana: 사전식 검색 (ga, na, da, …)

date: int                                 # date: 의결일자 (YYYYMMDD)
dpa_yd: string                            # dpaYd: 처분일자 기간 (YYYYMMDD~YYYYMMDD)
rsl_yd: string                            # rslYd: 의결일자 기간 (YYYYMMDD~YYYYMMDD)

sort: string                              # sort: lasc|ldes|dasc|ddes|nasc|ndes
pop_yn: "Y" | "N"                         # popYn: 팝업 여부
```

### Sample URLs
```text
1) 행정심판재결례 목록 (XML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=decc&type=XML

2) 행정심판재결례 목록 (HTML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=decc&type=HTML

3) 행정심판재결례 목록 (JSON)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=decc&type=JSON

4) 'ㄱ'으로 시작하는 재결례 목록 (XML)
http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=decc&type=XML&gana=ga
```

### Response Schema (normalized)
```yaml
target: string                           # 검색 대상
keyword: string                          # 키워드
section: string                          # 검색범위 (EvtNm=재결례명, bdyText=본문)
total_count: int                         # 검색결과갯수
page: int                                # 출력페이지
decc_id: int                             # 검색결과번호

decision_seq_no: int                     # 행정심판재결례일련번호
case_name: string                        # 사건명
case_no: string                          # 사건번호
disposition_date: string                 # 처분일자
resolution_date: string                  # 의결일자
disposition_agency: string               # 처분청
decision_agency: int                     # 재결청
decision_type_name: string               # 재결구분명
decision_type_code: string               # 재결구분코드

admin_decision_detail_link: string       # 행정심판례상세링크
```

---

## X) 행정심판례 본문 조회 API (decc)

**Endpoint**: `GET http://www.law.go.kr/DRF/lawService.do?target=decc`

### Request Parameters
```yaml
oc: string (required)                 # OC: 사용자 이메일 ID
target: "decc" (required)             # target: decc
type: HTML | XML | JSON (required)    # type: 출력 형식

id: string (required)                 # ID: 행정심판례 일련번호
lm: string                            # LM: 행정심판례명
```

### Sample URLs
```text
1) 행정심판례 일련번호 243263 (HTML)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=decc&ID=243263&type=HTML

2) 특정 사건명 조회 (XML)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=decc&ID=245011&LM=과징금 부과처분 취소청구&type=XML

3) 행정심판례 일련번호 223311 (JSON)
http://www.law.go.kr/DRF/lawService.do?OC=test&target=decc&ID=223311&type=JSON
```

### Response Schema (normalized)
```yaml
admin_decision_seq_no: int            # 행정심판례일련번호
case_name: string                     # 사건명
case_no: string                       # 사건번호

disposition_date: int                 # 처분일자 (YYYYMMDD)
resolution_date: int                  # 의결일자 (YYYYMMDD)

disposition_agency: string            # 처분청
decision_agency: string               # 재결청

decision_type_name: string            # 재결례유형명
decision_type_code: int               # 재결례유형코드

order: string                         # 주문
claim_summary: string                 # 청구취지
reason: string                         # 이유
decision_summary: string              # 재결요지
```