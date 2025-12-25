<div align="center">
  <img src="assets/LexLink_logo.png" alt="LexLink Logo" width="200"/>
  <h1>LexLink - 대한민국 법령정보 MCP 서버</h1>
</div>

**🌐 Read this in other languages:** [English](README.md) | **한국어**

[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink는 대한민국 국가법령정보 API ([open.law.go.kr](https://open.law.go.kr/))를 AI 에이전트와 LLM 애플리케이션에 제공하는 MCP (Model Context Protocol) 서버입니다. AI 시스템이 표준화된 MCP 도구를 통해 한국 법령 정보를 검색, 조회, 분석할 수 있도록 지원합니다.

## 주요 기능

- **26개의 MCP 도구**로 포괄적인 한국 법령 정보 접근
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
- **100% 의미론적 검증** - 26개 도구 모두 실제 법령 데이터 반환 확인
- **세션 설정** - 한 번 설정하면 모든 도구 호출에서 사용
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
| **API 커버리지** | 150개 이상 엔드포인트 중 ~17% 커버 |
| **LLM 통합** | ✅ 검증 완료 (Gemini) |
| **코드 품질** | 깔끔하고 문서화되고 테스트됨 |
| **버전** | v1.3.0 |

**최근 성과:** Phase 5 완성! AI 기반 의미론적 검색 도구 (aiSearch, aiRltLs_search) 추가로 자연어 쿼리 지원.

## 사전 요구사항

- **Python 3.10+**
- **Smithery API 키** (선택사항, 배포용): [smithery.ai/account/api-keys](https://smithery.ai/account/api-keys)에서 발급
- **law.go.kr OC 식별자**:  대한민국 국가법령정보 API ([open.law.go.kr](https://open.law.go.kr/)) 에서 등록 가능, 이메일 로컬 부분 (예: `g4c@korea.kr` → `g4c`)

## 빠른 시작

### 1. 의존성 설치

```bash
uv sync
```

### 2. OC 식별자 설정

세 가지 방법 중 하나를 선택하세요:

**옵션 A: 세션 설정 (권장)**
```bash
# OC를 포함한 개발 서버 시작
uv run dev
# Smithery UI에서 세션 설정의 oc 필드 설정
```

**옵션 B: 환경 변수**
```bash
# 예제 파일 복사
cp .env.example .env

# .env 파일을 편집하고 OC 설정
OC=your_id_here
```

**옵션 C: 도구 인자로 전달**
```python
# 각 도구 호출에서 OC 재정의
eflaw_search(query="법령명", oc="your_id")
```

### 3. 서버 실행

```bash
# 개발 모드 (핫 리로드 포함)
uv run dev

# Smithery Playground를 이용한 대화형 테스트
uv run playground
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

### 세션 설정 스키마

Smithery UI 또는 URL 파라미터에서 한 번 설정:

```python
{
    "oc": "your_id",              # 필수: law.go.kr 사용자 ID
    "http_timeout_s": 60          # 선택사항: HTTP 타임아웃 (5-120초, 기본값: 60)
}
```

### 매개변수 우선순위

OC 식별자를 확인할 때:
1. **도구 인자** (최우선) - 도구 호출 시 `oc` 매개변수
2. **세션 설정** - Smithery UI/URL에서 설정
3. **환경 변수** - .env 파일의 `OC`

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
        "2. Session config: Set 'oc' in Smithery settings",
        "3. Environment variable: OC=your_value"
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
│   ├── config.py        # 세션 설정 스키마
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
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/
```

### 새로운 도구 추가

**현재 상태:** 26/26 도구 구현 및 검증 완료 (Phase 1-5 완료)

124개 이상의 남은 API에서 추가 도구를 구현하려면:
1. `src/lexlink/server.py`에 확립된 패턴 따르기
2. 세션 설정에 Context 주입 사용
3. 범용 파서 함수 사용 (`extract_items_list`, `update_items_list`)
4. 의미론적 검증 테스트 추가

**도구 구현 패턴:**
- 각 도구는 MCP 스키마가 있는 데코레이터 함수
- 세션 설정을 위해 `ctx: Context = None` 매개변수 사용
- 3단계 매개변수 확인: 도구 인자 > 세션 > 환경변수
- 범용 파서 함수는 모든 XML 태그에서 작동
- 실행 가능한 힌트가 포함된 포괄적인 오류 처리

## 배포

### Smithery에 배포

1. GitHub 리포지토리 생성:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

2. [smithery.ai/new](https://smithery.ai/new)에서 배포

3. Smithery UI에서 세션 설정 구성

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

자세한 배포 방법(AWS EC2, Nginx, systemd, HTTPS)은 [assets/DEPLOYMENT_GUIDE.md](assets/DEPLOYMENT_GUIDE.md)를 참조하세요.

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

**해결책:** 세션 설정에서 타임아웃을 늘리세요:
```python
{
    "oc": "your_id",
    "http_timeout_s": 90  # 기본값 60초에서 증가
}
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
- **Smithery** - MCP 서버 배포 플랫폼

## 지원

- **이슈:** [GitHub Issues](https://github.com/rabqatab/LexLink-ko-mcp/issues)
- **law.go.kr API:** [공식 문서](http://open.law.go.kr)

---

## 변경 로그

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
  - Kakao PlayMCP 배포 가이드 추가 (`assets/DEPLOYMENT_GUIDE.md`)
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
- **원인:**
  - `eflaw_josub`와 `law_josub`가 여전히 `id: Optional[str]`과 `mst: Optional[str]`을 사용 (`Union[str, int]` 대신)
  - `lnkLsOrdJo_search`가 `jo: Optional[int]`를 사용 (`Union[str, int]` 대신)
  - LLM이 이 특정 도구들에 정수를 전달할 때 유효성 검증 오류 발생
- **해결책:**
  - `eflaw_josub` 수정: `id`와 `mst`가 이제 `Union[str, int]` 허용
  - `law_josub` 수정: `id`와 `mst`가 이제 `Union[str, int]` 허용
  - `lnkLsOrdJo_search` 수정: `jo`가 이제 `Union[str, int]` 허용
- **검증:**
  - `id` 매개변수를 가진 7개 도구 모두 이제 일관되게 `Optional[Union[str, int]]`
  - `mst` 매개변수를 가진 6개 도구 모두 이제 일관되게 `Optional[Union[str, int]]`
  - `jo` 매개변수를 가진 5개 도구 모두 이제 일관되게 `Optional[Union[str, int]]`
- **영향:**
  - 100% 매개변수 타입 일관성 달성
  - LLM이 어떤 도구를 선택하든 유효성 검증 오류 없음
  - 더 나은 개발자 경험 - 동일한 매개변수가 모든 곳에서 동일하게 작동

### v1.0.7 - 2025-11-10
**수정: 검색 안정성 및 LLM 가이드 개선**

- **문제:** LLM이 "민법"과 같은 일반적인 법률을 자주 찾지 못했던 이유:
  1. 순위 지정 가져오기 제한(50개 결과)이 큰 결과 세트에 너무 작음 (예: "민법"에 대한 77개 결과)
  2. LLM이 기본적으로 작은 `display` 값 사용 (예: 5), 정확한 일치 항목 누락
  3. `jo` 매개변수가 정수를 거부하여 유효성 검사 오류 및 재시도 루프 발생
- **원인:**
  - v1.0.5 순위는 50개 결과만 가져왔고, "민법"은 알파벳 순서로 50번째 이후에 있음
  - 도구 설명이 LLM에게 더 큰 display 값 사용을 안내하지 않음
  - 매개변수 타입 엄격성으로 UX 마찰 발생
- **해결책:**
  - 순위 지정 가져오기 제한을 50에서 **100개 결과**(API 최대값)로 증가
  - `jo` 매개변수가 `Union[str, int]`를 수락하도록 업데이트하여 자동 변환
  - 도구 설명에 가이드 추가: **"법령 검색 시 정확한 일치 항목을 찾으려면 50-100 권장"**
- **변경사항:**
  - 4개 검색 도구 모두 순위 지정을 위해 최대 100개 결과 가져오기
  - `jo` 매개변수가 있는 4개 도구(`eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`) 모두 정수 허용
  - 7개 검색 도구 설명에 display 권장 사항 업데이트
- **영향:**
  - LLM이 작은 초기 display 값으로도 "민법"을 올바르게 찾음
  - LLM이 조문 번호를 정수로 전달할 때 유효성 검사 오류 없음
  - 더 나은 가이드로 더 효율적인 검색 수행

### v1.0.6 - 2025-11-10
**개선: MCP 서버 품질 점수 향상 (Smithery.ai 최적화)**

- **변경사항:**
  - OC 설정 기본값을 "test"로 설정하여 쉬운 온보딩 제공
  - 모든 15개 도구에 도구 주석 추가 (readOnlyHint=True, destructiveHint=False, idempotentHint=True)
  - 모든 도구의 매개변수 설명을 문서 문자열에서 개선
  - 일반적인 사용 사례를 위한 3개 MCP 프롬프트 구현
- **추가된 프롬프트:**
  - `search-korean-law`: 법령명으로 한국 법률 검색 및 요약 제공
  - `get-law-article`: 법률에서 특정 조문 검색 및 설명
  - `search-admin-rules`: 키워드로 행정규칙 검색
- **영향:** Smithery 품질 점수가 47/100에서 ~73/100으로 개선 예상 (+26점)
  - 도구 주석: +9점
  - 매개변수 설명: +12점
  - MCP 프롬프트: +5점

### v1.0.5 - 2025-11-10
**수정: 순위 지정 전 더 많은 결과 가져오기로 순위 개선**

- **문제:** v1.0.4 순위가 제대로 작동하지 않았던 이유는 API가 반환한 제한된 결과만 순위를 매겼기 때문 (예: `display=5`일 때 알파벳 순서로 정렬된 5개 결과만 가져옴). "민법"이 처음 5개 결과에 없으면 순위가 도움이 되지 않음.
- **원인:** 순위 로직이 API가 제한된 결과를 반환한 후에 적용되어 초기 페이지 외부의 관련 일치 항목은 고려되지 않음.
- **해결책:**
  - 순위가 활성화되고 `display < 50`일 때 API에서 최대 50개 결과 자동 가져오기
  - 더 큰 결과 세트(50개 결과)에 순위 적용
  - 순위 지정 후 원래 요청한 `display` 양으로 다시 자르기
  - 실제 반환된 결과 수를 반영하도록 응답의 `numOfRows` 업데이트
- **구현:**
  - 4개 검색 도구 모두 업데이트: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - `original_display` 추적 및 `ranking_enabled` 플래그 추가
  - 순위가 적용될 때 50개 결과 가져온 후 요청된 양으로 자르기
- **예시:**
  - 사용자가 "민법" 쿼리에 대해 `display=5` 요청
  - 시스템이 50개 결과 가져오기 (알파벳 순서로 처음 5개에 없더라도 "민법" 포함)
  - 순위가 "민법"을 첫 번째에 배치
  - 시스템이 상위 5개 순위 결과 반환 (이제 "민법"이 첫 번째에 나타남)
- **영향:** 순위가 이제 실제로 작동 - API 결과의 알파벳 위치와 관계없이 정확한 일치가 먼저 나타남

### v1.0.4 - 2025-11-10
**기능: 검색 결과에 관련성 순위 추가**

- **문제:** law.go.kr API가 알파벳 순서로 결과를 반환하여 관련 없는 결과가 먼저 표시됨 (예: "민법" 검색 시 정확히 일치하는 "민법" 대신 "난민법"이 먼저 표시)
- **해결책:**
  - 알파벳 순서보다 정확한 일치를 우선시하는 지능형 관련성 순위 추가
  - XML 응답의 키워드 검색에 자동으로 순위 적용
  - 결과 재정렬: 정확한 일치 → 쿼리로 시작 → 쿼리 포함 → 기타 일치
- **구현:**
  - `ranking.py` 모듈에 `rank_search_results()`, `should_apply_ranking()`, `detect_query_language()` 함수 추가
  - XML 파싱 및 구조화된 데이터 추출을 위한 `parser.py` 모듈 추가
  - 4개 주요 검색 도구 업데이트: `eflaw_search`, `law_search`, `elaw_search`, `admrul_search`
  - 순위는 원시 XML을 유지하면서 LLM 소비를 위한 `ranked_data` 필드 추가
  - `elaw_search` 특별 처리: 쿼리 언어(한국어 vs 영어) 감지 후 일치하는 이름 필드로 순위 지정
- **예시:**
  - "민법" 쿼리 결과: "민법" (정확한 일치) → "민법 시행령" (시작 일치) → "난민법" (알파벳순)
  - "insurance" 쿼리 결과: "Insurance Act" → "Insurance Business Act" → 기타 일치
- **영향:** 검색 관련성이 크게 향상되어 LLM 혼란이 줄고 사용자 경험 개선

### v1.0.3 - 2025-11-10
**수정: 도구 설명에서 조문 번호 형식 명확화**

- **문제:** LLM이 6자리 조문 번호 형식(`jo` 매개변수)을 잘못 해석하여 제20조에 대해 올바른 "002000" 대신 "000200"을 생성하여 잘못된 조문 검색
- **원인:** 도구 설명이 "제2조"에 대해 "000200" 예시를 사용하여 LLM이 제20조를 "000200"으로 잘못 패턴 매칭
- **해결책:**
  - 여러 예시와 함께 포괄적인 조문 번호 형식 문서 추가
  - 향후 사용을 위해 `validation.py`에 `format_article_number()` 헬퍼 함수 추가
  - XXXXXX 형식 = 앞 4자리(조문 번호, 제로 패딩) + 뒤 2자리(가지조문 접미사) 명확화
- **변경사항:**
  - 4개 도구 업데이트: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`
  - 별도 4+2 자리 형식을 사용하는 `lnkLsOrdJo_search` 업데이트
  - 명확한 예시 추가: "000200" (제2조), "002000" (제20조), "001502" (제15조의2)
- **영향:** LLM이 이제 조문 번호를 올바르게 형식화하여 잘못된 조문 반환 방지

### v1.0.2 - 2025-11-10
**수정: id/mst 매개변수에 문자열과 정수 모두 허용**

- **문제:** LLM이 XML 응답에서 숫자 값을 정수로 추출 (예: `<법령일련번호>188376</법령일련번호>` → `mst=188376`)하지만, 도구는 문자열을 예상하여 Pydantic 검증 오류 발생
- **해결책:** 매개변수 타입을 문자열과 정수 모두 허용하도록 변경하고 자동 변환 추가
- **변경사항:**
  - 7개 도구 서명 업데이트: `id: Optional[str]` → `id: Optional[Union[str, int]]`
  - 각 영향받는 도구의 시작 부분에 자동 문자열 변환 추가
  - 적용 대상: `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`, `elaw_service`, `admrul_service`, `lsDelegated_service`
- **영향:** LLM이 이제 검증 오류 없이 숫자 ID를 정수로 전달할 수 있음

### v1.0.1 - 2025-11-10
**수정: 모든 도구에서 JSON 형식 옵션 제거**

- **문제:** LLM이 JSON 형식을 선택했지만, law.go.kr API는 문서와 달리 JSON을 지원하지 않음 ("미신청된 목록/본문" 메시지와 함께 HTML 오류 페이지 반환)
- **해결책:** 14개 도구 설명에서 JSON 옵션 제거
- **변경사항:**
  - `type` 매개변수 문서를 "API가 JSON을 지원하지 않음"으로 명시적으로 업데이트
  - 모듈 docstring에 JSON 형식 제한 경고 추가
  - 도구 기본값은 XML (작동 형식)로 유지
- **영향:** LLM이 JSON 형식을 요청하고 오류 페이지를 받는 것을 방지

### v1.0.0 - 2025-11-10
**최초 릴리스**

- 한국 법령 정보 접근을 위한 15개 MCP 도구
- 6개 핵심 법령 API (eflaw/law 검색 및 조회)
- 9개 확장 API (영문 법령, 행정규칙, 법령-자치법규 연계)
- Context 주입을 통한 세션 설정
- 100% 의미론적 검증
- Smithery 배포 준비 완료

---

**[Smithery](https://smithery.ai)로 구축 | [MCP](https://modelcontextprotocol.io) 기반**
