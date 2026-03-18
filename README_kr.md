<div align="center">
  <img src="assets/LexLink_logo.png" alt="LexLink Logo" width="200"/>
  <h1>LexLink - 대한민국 법령정보 MCP 서버</h1>
</div>

**🌐 Read this in other languages:** [English](README.md) | **한국어**

[![Kakao PlayMCP 10 3rd Prize](https://img.shields.io/badge/Kakao_PlayMCP_10-3rd_Prize_🏆-CD7F32)](https://playmcp.kakao.com/)
[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink는 대한민국 국가법령정보 API ([open.law.go.kr](https://open.law.go.kr/))를 AI 에이전트와 LLM 애플리케이션에 제공하는 MCP (Model Context Protocol) 서버입니다. AI 시스템이 표준화된 MCP 도구를 통해 한국 법령 정보를 검색, 조회, 분석할 수 있도록 지원합니다.

## 주요 기능

- **26개의 MCP 도구 + 2개의 MCP 리소스**로 포괄적인 한국 법령 정보 접근
  - 한국 법령 검색 및 조회 (시행일 & 공포일 기준)
  - 영문 번역 법령 검색 및 조회
  - 행정규칙 검색 및 조회 (훈령, 예규, 고시, 공고, 지침)
  - 특정 조항, 항, 호목 조회
  - 법령-자치법규 연계 정보
  - 위임법령 정보
  - **Phase 3 - 판례 및 법령연구**
    - 법원 판례 (판례)
    - 헌법재판소 결정례 (헌재결정례)
    - 법령해석례 (법령해석례)
    - 행정심판 재결례 (행정심판례)
  - **Phase 4 - 조문 인용 추출**
    - 법령 조문에서 인용된 법률 추출 (100% 정확도)
  - **신규: Phase 5 - AI 기반 검색**
    - 자연어 쿼리를 위한 의미론적 검색 (aiSearch)
    - 연관 법령 탐색 (aiRltLs_search)
  - **MCP 리소스 - 법령 ID 캐시**
    - 자주 사용되는 ~20개 법령명과 안정적인 법령ID 매핑 캐시
    - 한글 법령명 또는 약칭으로 조회 (`lexlink://law/{name}`)
    - 동적 캐싱: 검색 결과가 자동으로 캐시에 추가
- **100% 의미론적 검증** - 26개 도구 모두 실제 법령 데이터 반환 확인
- **오류 처리** - 해결 방법이 포함된 실행 가능한 오류 메시지
- **한글 텍스트 지원** - UTF-8 인코딩으로 한글 문자 정확히 처리
- **응답 형식** - HTML, XML 지원 (다양한 형식 지원)

## 프로젝트 상태

🎉 **프로덕션 준비 완료 - Phase 5 완성!**

| 지표 | 상태 |
|--------|--------|
| **구현된 도구** | 26/26 (100%) ✅ |
| **의미론적 검증** | 26/26 (100%) ✅ |
| **MCP 프롬프트** | 6/6 (100%) ✅ |
| **MCP 리소스** | 2개 (정적 1 + 템플릿 1) ✅ |
| **API 커버리지** | 150개 이상 엔드포인트 중 ~17% 커버 |
| **LLM 통합** | ✅ 검증 완료 (Gemini) |
| **코드 품질** | 깔끔하고 문서화되고 테스트됨 |
| **버전** | v1.5.0 |

**최근:** Smithery 의존성 제거. 2단계 OC 해석 (도구 인자 > 환경변수), 의존성 9개 감소.

## 사전 요구사항

- **Python 3.10+**
- **law.go.kr OC 식별자**: [open.law.go.kr](https://open.law.go.kr/)에서 등록, 이메일 로컬 부분 (예: `g4c@korea.kr` → `g4c`)

## 빠른 시작

### 1. 의존성 설치

```bash
uv sync
```

### 2. OC 식별자 설정

**옵션 A: 환경 변수 (권장)**
```bash
# 환경 변수로 OC 설정
export OC=your_id_here
```

**옵션 B: 도구 인자로 전달**
```python
# 각 도구 호출에서 OC 재정의
eflaw_search(query="법령명", oc="your_id")
```

### 3. 서버 실행

```bash
# Stdio 전송 (Claude Code, Cursor 등)
OC=your_oc uv run stdio

# HTTP 전송 (Kakao PlayMCP용)
OC=your_oc TRANSPORT=http uv run serve
```

## 사용 가능한 도구

### Phase 1: 핵심 법령 API (6개 도구)

#### 1. `eflaw_search` - 시행일 기준 법령 검색
시행일 기준으로 정리된 법령을 검색합니다.

```python
eflaw_search(
    query="자동차관리법",      # 검색 키워드
    display=10,                # 페이지당 결과 수
    type="XML",                # 응답 형식
    ef_yd="20240101~20241231"  # 선택사항: 날짜 범위
)
```

#### 2. `law_search` - 공포일 기준 법령 검색
공포일 기준으로 정리된 법령을 검색합니다.

```python
law_search(
    query="민법",
    display=10,
    type="XML"
)
```

#### 3. `eflaw_service` - 법령 본문 조회 (시행일 기준)
시행일 기준으로 전체 법령 텍스트와 조항을 가져옵니다.

> **중요:** 특정 조문 조회 시 (예: "제174조") `jo` 매개변수를 사용하세요. 일부 법령은 400개 이상의 조문이 있어 `jo` 없이 응답이 1MB를 초과할 수 있습니다.

```python
# 특정 조문 조회 (권장)
eflaw_service(
    mst="279823",              # 법령 MST
    jo="017400",               # 제174조
    type="XML"
)

# 전체 법령 조회 (경고: 큰 응답)
eflaw_service(
    id="001823",
    type="XML"
)
```

#### 4. `law_service` - 법령 본문 조회 (공포일 기준)
공포일 기준으로 전체 법령 텍스트와 조항을 가져옵니다.

> **중요:** 특정 조문 조회 시 (예: "제174조") `jo` 매개변수를 사용하세요. 일부 법령은 400개 이상의 조문이 있어 `jo` 없이 응답이 1MB를 초과할 수 있습니다.

```python
# 특정 조문 조회 (권장)
law_service(
    mst="279823",              # 법령 MST
    jo="017400",               # 제174조
    type="XML"
)
```

#### 5. `eflaw_josub` - 조항/항목 조회 (시행일 기준)
**특정 조문 조회에 최적화된 도구입니다.** 요청한 조문/항만 반환합니다.

```python
eflaw_josub(
    mst="279823",              # 법령 MST
    jo="017400",               # 제174조
    type="XML"
)
# jo 형식: "XXXXXX" - 앞 4자리 = 조문번호(제로패딩), 뒤 2자리 = 가지번호(00=본조)
# 예시: "017400" (제174조), "000300" (제3조), "001502" (제15조의2)
```

#### 6. `law_josub` - 조항/항목 조회 (공포일 기준)
**특정 조문 조회에 최적화된 도구입니다.** 요청한 조문/항만 반환합니다.

```python
law_josub(
    mst="279823",              # 법령 MST
    jo="017200",               # 제172조
    type="XML"
)
```

### Phase 2: 확장 API (9개 도구)

#### 7. `elaw_search` - 영문 번역 법령 검색
영어로 번역된 한국 법령을 검색합니다.

```python
elaw_search(
    query="employment",
    display=10,
    type="XML"
)
```

#### 8. `elaw_service` - 영문 법령 본문 조회
영어로 번역된 전체 법령 텍스트를 가져옵니다.

```python
elaw_service(
    id="009589",
    type="XML"
)
```

#### 9. `admrul_search` - 행정규칙 검색
행정규칙(훈령, 예규, 고시, 공고, 지침)을 검색합니다.

```python
admrul_search(
    query="학교",
    display=10,
    type="XML"
)
```

#### 10. `admrul_service` - 행정규칙 본문 조회
부속서를 포함한 전체 행정규칙 텍스트를 가져옵니다.

```python
admrul_service(
    id="62505",
    type="XML"
)
```

#### 11. `lnkLs_search` - 법령-자치법규 연계 검색
지방자치법규와 연결된 법령을 찾습니다.

```python
lnkLs_search(
    query="건축",
    display=10,
    type="XML"
)
```

#### 12. `lnkLsOrdJo_search` - 법령별 자치법규 조문 검색
특정 법령 조항과 연결된 자치법규 조문을 찾습니다.

```python
lnkLsOrdJo_search(
    knd="002118",              # 법령 ID
    display=10,
    type="XML"
)
```

#### 13. `lnkDep_search` - 부처별 법령-자치법규 연계 검색
정부 부처별로 자치법규와 연결된 법령을 찾습니다.

```python
lnkDep_search(
    org="1400000",             # 부처 코드
    display=10,
    type="XML"
)
```

#### 14. `drlaw_search` - 법령-자치법규 연계 통계 조회
연계 통계 테이블을 가져옵니다 (HTML 형식).

```python
drlaw_search(
    lid="001823",              # 법령 ID
    type="HTML"
)
```

#### 15. `lsDelegated_service` - 위임법령 정보 조회
위임법령, 시행규칙, 시행령에 대한 정보를 가져옵니다.

```python
lsDelegated_service(
    id="001823",
    type="XML"
)
```


### Phase 3: 판례 및 법령연구 (8개 도구 - 신규!)

#### 16. `prec_search` - 법원 판례 검색
대법원 및 하급법원의 판례를 검색합니다.

```python
prec_search(
    query="담보권",
    display=10,
    type="XML",
    curt="대법원"             # 선택사항: 법원명 필터
)
```

#### 17. `prec_service` - 판례 본문 조회
판례의 전체 내용을 가져옵니다.

```python
prec_service(
    id="228541",
    type="XML"
)
```

#### 18. `detc_search` - 헌법재판소 결정례 검색
헌법재판소 결정례를 검색합니다.

```python
detc_search(
    query="벌금",
    display=10,
    type="XML"
)
```

#### 19. `detc_service` - 헌재결정례 본문 조회
헌법재판소 결정례의 전체 내용을 가져옵니다.

```python
detc_service(
    id="58386",
    type="XML"
)
```

#### 20. `expc_search` - 법령해석례 검색
정부 기관에서 발행한 법령해석례를 검색합니다.

```python
expc_search(
    query="임차",
    display=10,
    type="XML"
)
```

#### 21. `expc_service` - 법령해석례 본문 조회
법령해석례의 전체 내용을 가져옵니다.

```python
expc_service(
    id="334617",
    type="XML"
)
```

#### 22. `decc_search` - 행정심판 재결례 검색
행정심판 재결례를 검색합니다.

```python
decc_search(
    query="*",                # 모든 재결례 검색
    display=10,
    type="XML"
)
```

#### 23. `decc_service` - 행정심판례 본문 조회
행정심판 재결례의 전체 내용을 가져옵니다.

```python
decc_service(
    id="243263",
    type="XML"
)
```

### Phase 4: 조문 인용 추출 (1개 도구 - 신규!)

#### 24. `article_citation` - 법령 조문에서 인용 추출
특정 법령 조문에서 인용된 모든 법률을 추출합니다.

```python
# 먼저 법령을 검색하여 MST 획득
eflaw_search(query="건축법")  # MST: 268611 반환

# 인용 추출
article_citation(
    mst="268611",              # 검색 결과의 법령 MST
    law_name="건축법",          # 법령명
    article=3                  # 조문 번호 (제3조)
)
```

**응답:**
```json
{
    "success": true,
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
            "target_paragraph": 1
        }
    ]
}
```

**주요 특징:**
- HTML 파싱 기반 100% 정확도 (LLM 기반 아님)
- 외부 API 비용 없음 (LLM 호출 불필요)
- 평균 추출 시간 ~350ms
- 내부 인용과 외부 인용 구분

### Phase 5: AI 기반 검색 (2개 도구 - 신규!)

#### 25. `aiSearch` - AI 기반 의미론적 법령 검색
⭐ **모호하거나 자연어 쿼리에 우선 사용하는 도구입니다.** 사용자 의도가 불명확하거나 대화형일 때 이 도구를 먼저 사용하세요.

지능형/의미론적 검색을 사용하여 관련 법령 조문을 찾습니다. 전체 조문 텍스트를 반환합니다.

```python
aiSearch(
    query="뺑소니 처벌",           # 자연어 쿼리
    search=0,                      # 0: 법령조문, 1: 별표서식, 2: 행정규칙조문, 3: 행정규칙별표서식
    display=20,                    # 페이지당 결과 수
    page=1,                        # 페이지 번호
    type="XML"                     # 응답 형식 (XML만 지원)
)
```

**최적 용도:** "음주운전 벌금", "이혼 재산분할", "상속 문제" 같은 자연어 쿼리

#### 26. `aiRltLs_search` - AI 기반 연관법령 검색
⭐ **모호한 주제에서 연관 법령을 탐색할 때 우선 사용하는 도구입니다.** 사용자가 일반적인 주제 주변의 법령을 탐색하고자 할 때 사용하세요.

주어진 법령명이나 키워드와 의미론적으로 연관된 법령을 찾습니다.

```python
aiRltLs_search(
    query="민법",                  # 법령명 또는 키워드
    search=0,                      # 0: 법령조문, 1: 행정규칙조문
    type="XML"                     # 응답 형식 (XML만 지원)
)
```

**최적 용도:** "민법" → 상법, 의료법, 소송촉진법 등 연관 법령 찾기

### 도구 선택 가이드

한국 법령 검색 시, 쿼리 명확성에 따라 도구를 선택하세요:

| 쿼리 유형 | 권장 도구 | 예시 |
|----------|----------|------|
| 🔍 **모호한/자연어** | `aiSearch`, `aiRltLs_search` | "음주운전 처벌", "이혼 재산분할" |
| 📋 **특정 법령/조문** | `eflaw_search`, `law_search` | "형법 제148조의2", "민법 상속편" |
| ⚖️ **판례** | `prec_search`, `detc_search` | "대법원 2023다12345" |
| 🔗 **연관 법령** | `aiRltLs_search` | "민법과 관련된 법률" |

## 설정

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OC` | *(필수)* | law.go.kr API 식별자 (이메일 로컬 부분) |
| `LEXLINK_BASE_URL` | `http://www.law.go.kr` | API 기본 URL |
| `LEXLINK_TIMEOUT` | `60` | HTTP 요청 타임아웃 (초) |
| `SLIM_RESPONSE` | *(미설정)* | `true` 설정 시 파싱된 데이터 존재할 때 중복 raw XML 제거 (PlayMCP용) |
| `TRANSPORT` | `sse` | 전송 유형: `sse` 또는 `http` |

### OC 우선순위

OC 식별자를 확인할 때:
1. **도구 인자** (최우선) - 도구 호출 시 `oc` 매개변수
2. **환경 변수** - `OC` 환경변수 (.env 또는 HTTP 헤더 미들웨어로 설정)

## 사용 예시

### 예시 1: 기본 검색

```python
# 자동차관리법 검색
result = eflaw_search(
    query="자동차관리법",
    display=5,
    type="XML"
)

# 반환:
{
    "status": "ok",
    "request_id": "uuid",
    "upstream_type": "XML",
    "data": {
        # 법령 검색 결과...
    }
}
```

### 예시 2: 날짜 범위로 검색

```python
# 2024년에 시행되는 법령 찾기
result = eflaw_search(
    query="교통",
    ef_yd="20240101~20241231",
    type="XML"
)
```

### 예시 3: 오류 처리

```python
# OC 매개변수 누락
result = eflaw_search(query="test")

# 유용한 오류 반환:
{
    "status": "error",
    "error_code": "MISSING_OC",
    "message": "OC parameter is required but not provided.",
    "hints": [
        "1. Tool argument: oc='your_value'",
        "2. Environment variable: OC=your_value"
    ]
}
```

## 실전 MCP 도구 활용 예시

다음은 LLM이 LexLink 도구를 사용하여 법령 조사 질문에 답변하는 실제 대화 흐름을 보여주는 예시입니다.

### 활용 예시 1: 기본 법령 조사
**사용자 질문:** "민법 제20조의 내용이 뭐야?"

**도구 호출:**
1. `law_search(query="민법", display=50, type="XML")` → 민법 ID 찾기
2. `law_service(id="000021", jo="002000", type="XML")` → 제20조 본문 조회

**결과:** LLM이 민법 제20조의 전체 법령 텍스트와 맥락을 포함한 설명 제공.

---

### 활용 예시 2: 판례 분석
**사용자 질문:** "담보권에 관한 최근 대법원 판례 찾아줘"

**도구 호출:**
1. `prec_search(query="담보권", curt="대법원", display=50, type="XML")` → 대법원 판례 검색
2. `prec_service(id="228541", type="XML")` → 주요 판례 상세 내용 조회

**결과:** LLM이 담보권 관련 주요 판례를 사건번호, 날짜, 판시사항과 함께 요약 제공.

---

### 활용 예시 3: 통합 법령 조사
**사용자 질문:** "근로기준법은 연장근로를 어떻게 규정하고 있고, 관련 판례는 있어?"

**도구 호출:**
1. `eflaw_search(query="근로기준법", display=50, type="XML")` → 근로기준법 찾기
2. `eflaw_service(id="001234", jo="005000", type="XML")` → 제50조(연장근로) 조회
3. `prec_search(query="근로기준법 연장근로", display=30, type="XML")` → 연장근로 판례 검색
4. `prec_service(id="234567", type="XML")` → 주요 판례 조회

**결과:** LLM이 법령 조문과 법원의 해석을 결합한 종합 분석을 제공하여 연장근로 규정이 실무에서 어떻게 적용되는지 설명.

---

### 활용 예시 4: 헌법재판소 결정례 조사
**사용자 질문:** "헌법재판소가 벌금 관련 법률을 심사한 적이 있어?"

**도구 호출:**
1. `detc_search(query="벌금", display=50, type="XML")` → 헌재 결정례 검색
2. `detc_service(id="58386", type="XML")` → 결정례 전문 조회
3. `law_search(query=<결정례에서_찾은_법령명>, type="XML")` → 관련 법령 조회

**결과:** LLM이 벌금 관련 조항에 대한 헌법재판소 판단과 특정 법령에 미친 영향을 설명.

---

### 활용 예시 5: 행정법령 조사
**사용자 질문:** "학교 관련 행정규칙이 뭐가 있고, 관련 법령해석은 있어?"

**도구 호출:**
1. `admrul_search(query="학교", display=50, type="XML")` → 학교 관련 행정규칙 검색
2. `admrul_service(id="62505", type="XML")` → 행정규칙 본문 조회
3. `expc_search(query="학교", display=30, type="XML")` → 법령해석례 검색
4. `expc_service(id="334617", type="XML")` → 해석례 상세 내용 조회

**결과:** LLM이 학교에 대한 행정규칙 체계와 정부기관의 공식 해석을 종합하여 제공.

---

### 활용 예시 6: 종합 법령 분석
**사용자 질문:** "주택 임대차 분쟁을 조사하고 있어. 관련 법률, 판례, 행정심판례를 모두 보여줘."

**도구 호출:**
1. `eflaw_search(query="주택임대차보호법", display=50, type="XML")` → 주택임대차보호법 찾기
2. `eflaw_service(id="002876", type="XML")` → 법령 전문 조회
3. `prec_search(query="주택임대차", display=50, type="XML")` → 주택임대차 판례 검색
4. `prec_service(id="156789", type="XML")` → 주요 판례 조회
5. `decc_search(query="주택임대차", display=30, type="XML")` → 행정심판례 검색
6. `decc_service(id="243263", type="XML")` → 심판례 조회

**결과:** LLM이 주택 임대차 분쟁에 대한 법령 체계, 사법적 해석, 행정심판 선례를 망라한 종합 법령조사 보고서 제공.

---

### 활용 예시 7: 인용 네트워크 분석 (Phase 4)
**사용자 질문:** "건축법 제3조가 인용하는 법률들이 뭐야?"

**도구 호출:**
1. `eflaw_search(query="건축법", display=50, type="XML")` → 건축법 찾기, MST 획득
2. `article_citation(mst="268611", law_name="건축법", article=3)` → 모든 인용 추출

**결과:** LLM이 12개 인용(외부 법률 8개, 내부 조문 4개)을 분석하여 구체적인 조항 및 항 참조와 함께 완전한 인용 분석 제공.

---

### 활용 예시 8: AI 기반 자연어 검색 (Phase 5)
**사용자 질문:** "뺑소니 사고 처벌은 어떻게 돼?"

**도구 호출:**
1. `aiSearch(query="뺑소니 처벌", search=0, display=20, type="XML")` → 뺑소니 처벌 의미론적 검색

**결과:** LLM이 관련 법률(특정범죄 가중처벌 등에 관한 법률 제5조의3)의 전체 조문 텍스트를 수신하여 뺑소니 처벌 규정 전문을 포함한 종합적인 답변 제공. 특정 법령명을 알 필요 없이 포괄적인 답변 가능.

---

### 활용 예시 9: 연관 법령 탐색 (Phase 5)
**사용자 질문:** "민법과 관련된 법률은 뭐가 있어?"

**도구 호출:**
1. `aiRltLs_search(query="민법", search=0, type="XML")` → 의미론적으로 연관된 법령 검색

**결과:** LLM이 상법(상사법), 의료법(의료서비스법), 소송촉진법 등 연관 법령을 탐색하여 법률 영역 간의 연결 관계를 보여줌.

---

### 주요 패턴

1. **모호한 쿼리는 AI 도구 우선**: 사용자 의도가 불명확하거나 대화형일 때 `aiSearch` 또는 `aiRltLs_search`를 먼저 사용
2. **검색 후 조회**: 서비스 도구 호출 전에 항상 검색으로 ID를 먼저 찾기
3. **법령 검색 시 display=50-100 사용**: 관련성 순위로 정확한 일치 항목이 확실히 표시됨
4. **단계별 결합**: Phase 1(법령), Phase 2(행정규칙), Phase 3(판례), Phase 5(AI 검색)를 혼합하여 완전한 조사
5. **type 매개변수**: 일관되고 파싱 가능한 결과를 위해 항상 `type="XML"` 지정
6. **조문 번호**: 특정 조문 조회 시 6자리 형식 사용 (예: 제20조는 "002000")

## 개발

### 프로젝트 구조

```
lexlink-ko-mcp/
├── src/lexlink/
│   ├── server.py        # 26개 도구가 포함된 메인 MCP 서버
│   ├── http_server.py   # Kakao PlayMCP용 HTTP/SSE 서버
│   ├── stdio_server.py  # Stdio 전송 진입점
│   ├── params.py        # 매개변수 확인 및 매핑
│   ├── validation.py    # 입력 검증
│   ├── parser.py        # XML 파싱 유틸리티
│   ├── ranking.py       # 관련성 순위 지정
│   ├── citation.py      # 조문 인용 추출 (Phase 4)
│   ├── client.py        # law.go.kr API용 HTTP 클라이언트
│   ├── errors.py        # 오류 코드 및 응답
│   ├── raw_logger.py    # PlayMCP 트래픽 로깅
│   └── log_processor.py # 로그 형식 변환기
├── logs/playmcp/         # PlayMCP 트래픽 로그 (일별 JSONL)
├── pyproject.toml        # 프로젝트 설정
└── README.md             # 영문 문서
```

### 테스트 실행

```bash
# 테스트 의존성 설치
uv sync

# 모든 테스트 실행
uv run pytest

# 커버리지와 함께 실행
uv run pytest --cov=src/lexlink --cov-report=html

# 특정 테스트 카테고리 실행
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
```

### 새로운 도구 추가

**현재 상태:** 26/26 도구 구현 및 검증 완료 (Phase 1-5 완료)

124개 이상의 남은 API에서 추가 도구를 구현하려면:
1. `src/lexlink/server.py`에 확립된 패턴 따르기
2. MCP 로깅/진행 상태를 위해 `ctx: Context = None` 매개변수 사용
3. 범용 파서 함수 사용 (`extract_items_list`, `update_items_list`)
4. 의미론적 검증 테스트 추가

**도구 구현 패턴:**
- 각 도구는 MCP 스키마가 있는 데코레이터 함수
- MCP 컨텍스트를 위해 `ctx: Context = None` 매개변수 사용
- 2단계 OC 확인: 도구 인자 > 환경변수
- 범용 파서 함수는 모든 XML 태그에서 작동
- 실행 가능한 힌트가 포함된 포괄적인 오류 처리

## 배포

### Kakao PlayMCP에 배포 (HTTP 서버)

LexLink는 Kakao PlayMCP와 같은 플랫폼을 위해 HTTP 서버로도 배포할 수 있습니다.

> **중요:** Kakao PlayMCP는 URL에 포트 번호를 허용하지 않습니다.
> Nginx를 리버스 프록시로 사용하여 포트 80에서 서비스해야 합니다.

**빠른 시작 (로컬 테스트):**
```bash
# HTTP 서버 실행
OC=your_oc uv run serve

# 서버 시작 주소: http://localhost:8000/sse
```

**프로덕션 설정:**
```
인터넷 → Nginx (포트 80) → LexLink (포트 8000)
```

**PlayMCP 등록 정보:**

| 필드 | 값 |
|------|-----|
| **MCP Endpoint** | `http://YOUR_SERVER_IP/sse` (포트 없음!) |
| **인증 방식** | Key/Token (헤더: `OC`) |

자세한 배포 방법(AWS EC2, Nginx, systemd, HTTPS)은 [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)를 참조하세요.

### PlayMCP 트래픽 로깅

LexLink는 PlayMCP 트래픽 분석을 위한 내장 로깅 기능을 제공합니다. 로그는 대시보드 호환 JSONL 형식으로 저장됩니다.

**로그 위치:** `logs/playmcp/YYYY-MM-DD.jsonl`

**로그 스키마:**
```json
{
  "rpc_id": "3",
  "request_id": "d8ee45eb",
  "session_id": "9ff9dc23431848a4901b4cb6326ba5bd",
  "timestamp": "2025-12-25T05:40:23.957987",
  "duration_ms": 1.52,
  "method": "tools/call",
  "tool_name": "aiSearch",
  "params": { "arguments": {"query": "뺑소니 처벌"} },
  "client": "PlayMCP",
  "client_version": "2025.0.0",
  "protocol_version": "2025-06-18",
  "client_ip": "220.64.111.219",
  "oc": "user_id",
  "status": "success",
  "status_code": 200,
  "result": { ... }
}
```

**기능:**
- 일별 로그 로테이션 (하루에 파일 하나)
- 필터링 및 분석을 위한 대시보드 호환 형식
- 타이밍 정보가 포함된 요청/응답 쌍 캡처
- SSE 스트리밍 응답 파싱

**기존 원시 로그 변환:**
```bash
uv run python -m lexlink.log_processor input.jsonl output.jsonl
```

## 문제 해결

### "OC parameter is required" 오류

**해결책:** 위의 세 가지 방법 중 하나를 사용하여 OC 식별자를 설정하세요.

### 한글 문자가 올바르게 표시되지 않음

**해결책:** 터미널이 UTF-8을 지원하는지 확인하세요:
```bash
export PYTHONIOENCODING=utf-8
```

### "Timeout" 오류

**해결책:** 환경 변수로 타임아웃을 늘리세요:
```bash
export LEXLINK_TIMEOUT=90  # 기본값 60초에서 증가
```

### 의존성 업데이트 후 서버가 시작되지 않음

**해결책:** 의존성 재동기화:
```bash
uv sync --reinstall
```

## 기여

기여를 환영합니다! 다음 단계를 따라주세요:

1. 리포지토리 포크
2. 기능 브랜치 생성 (`git checkout -b feature/amazing-feature`)
3. 새로운 기능에 대한 테스트 작성
4. 모든 테스트 통과 확인 (`uv run pytest`)
5. 변경사항 커밋 (`git commit -m 'Add amazing feature'`)
6. 브랜치에 푸시 (`git push origin feature/amazing-feature`)
7. Pull Request 열기

## 라이선스

이 프로젝트는 오픈 소스입니다.

## 감사의 말

- **law.go.kr** - 대한민국 국가법령정보 API
- **MCP** - Anthropic의 Model Context Protocol

## 지원

- **이슈:** [GitHub Issues](https://github.com/rabqatab/LexLink-ko-mcp/issues)
- **law.go.kr API:** [공식 문서](http://open.law.go.kr)

---

## 변경 로그

### v1.5.0 - 2026-02-28
**리팩토링: Smithery 의존성 제거**

- `smithery` 패키지 및 8개 전이 의존성 제거
- OC 해석을 2단계로 단순화 (도구 인자 > 환경변수)
- stdio 전송을 위한 `stdio_server.py` 진입점 추가
- 자세한 내용은 [CHANGELOG.md](CHANGELOG.md) 참조

전체 변경 로그(v1.0.0 – v1.5.0)는 [CHANGELOG.md](CHANGELOG.md)를 참조하세요.

---

**[MCP](https://modelcontextprotocol.io) 기반**
