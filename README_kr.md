# LexLink - 대한민국 법령정보 MCP 서버

**🌐 Read this in other languages:** [English](README.md) | **한국어**

[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink는 대한민국 국가법령정보 API ([open.law.go.kr](https://open.law.go.kr/))를 AI 에이전트와 LLM 애플리케이션에 제공하는 MCP (Model Context Protocol) 서버입니다. AI 시스템이 표준화된 MCP 도구를 통해 한국 법령 정보를 검색, 조회, 분석할 수 있도록 지원합니다.

## 주요 기능

- **15개의 MCP 도구**로 포괄적인 한국 법령 정보 접근
  - 한국 법령 검색 및 조회 (시행일 & 공포일 기준)
  - 영문 번역 법령 검색 및 조회
  - 행정규칙 검색 및 조회 (훈령, 예규, 고시, 공고, 지침)
  - 특정 조항, 항, 호목 조회
  - 법령-자치법규 연계 정보
  - 위임법령 정보
- **내용 반환 확인** - 15개 도구 모두 실제 법령 데이터 반환 확인
- **세션 설정** - 한 번 설정하면 모든 도구 호출에서 사용
- **오류 처리** - 해결 방법이 포함된 실행 가능한 오류 메시지
- **한글 텍스트 지원** - UTF-8 인코딩으로 한글 문자 정확히 처리
- **응답 형식** - HTML, XML 지원 (다양한 형식 지원)

## 프로젝트 상태

🎉 **프로덕션 준비 완료!**

| 지표 | 상태 |
|--------|--------|
| **구현된 도구** | 15/15 (100%) ✅ |
| **의미론적 검증** | 15/15 (100%) ✅ |
| **API 커버리지** | 150개 이상 엔드포인트 중 핵심적인 10% API 커버 |
| **LLM 통합** | ✅ 검증 완료 (Gemini) |
| **코드 품질** | 깔끔하고 문서화되고 테스트됨 |

**성과:** 포괄적인 검증 테스트를 통해 15개 도구 모두 실제 한국 법령 데이터를 반환함을 확인했습니다.

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
LAW_OC=your_id_here
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

```python
eflaw_service(
    id="001823",               # 법령 ID
    type="XML",
    jo="0001"                  # 선택사항: 특정 조항
)
```

#### 4. `law_service` - 법령 본문 조회 (공포일 기준)
공포일 기준으로 전체 법령 텍스트와 조항을 가져옵니다.

```python
law_service(
    id="001823",
    type="XML"
)
```

#### 5. `eflaw_josub` - 조항/항목 조회 (시행일 기준)
시행일 기준으로 특정 조항, 항, 호목을 조회합니다.

```python
eflaw_josub(
    id="001823",
    jo="0001",                 # 조항 번호
    type="XML"
)
```

#### 6. `law_josub` - 조항/항목 조회 (공포일 기준)
공포일 기준으로 특정 조항, 항, 호목을 조회합니다.

```python
law_josub(
    id="001823",
    jo="0001",
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

## 설정

### 세션 설정 스키마

Smithery UI 또는 URL 파라미터에서 한 번 설정:

```python
{
    "oc": "your_id",              # 필수: law.go.kr 사용자 ID
    "debug": false,               # 선택사항: 상세 로깅 활성화
    "base_url": "http://www.law.go.kr",  # 선택사항: API 기본 URL
    "http_timeout_s": 15          # 선택사항: HTTP 타임아웃 (5-60초)
}
```

### 매개변수 우선순위

OC 식별자를 확인할 때:
1. **도구 인자** (최우선) - 도구 호출 시 `oc` 매개변수
2. **세션 설정** - Smithery UI/URL에서 설정
3. **환경 변수** - .env 파일의 `LAW_OC`

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
        "3. Environment variable: LAW_OC=your_value"
    ]
}
```

## 개발

### 프로젝트 구조

```
lexlink-ko-mcp/
├── src/lexlink/
│   ├── server.py       # 15개 도구가 포함된 메인 MCP 서버
│   ├── config.py       # 세션 설정 스키마
│   ├── params.py       # 매개변수 확인 및 매핑
│   ├── validation.py   # 입력 검증
│   ├── client.py       # law.go.kr API용 HTTP 클라이언트
│   └── errors.py       # 오류 코드 및 응답
├── pyproject.toml       # 프로젝트 설정
└── README.md            # 영문 문서
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

**현재 상태:** 15/15 핵심 도구 구현 및 검증 완료

150개 이상의 사용 가능한 API에서 추가 도구를 구현하려면:
1. `src/lexlink/server.py`에 확립된 패턴 따르기
2. 세션 설정에 Context 주입 사용
3. 의미론적 검증 테스트 추가

**도구 구현 패턴:**
- 각 도구는 MCP 스키마가 있는 데코레이터 함수
- 세션 설정을 위해 `ctx: Context = None` 매개변수 사용
- 3단계 매개변수 확인: 도구 인자 > 세션 > 환경변수
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
    "http_timeout_s": 30  # 기본값 15초에서 증가
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
