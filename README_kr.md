<div align="center">
  <img src="assets/LexLink_logo.png" alt="LexLink Logo" width="200"/>
  <h1>LexLink - 대한민국 법령정보 MCP 서버</h1>
</div>

**Read this in other languages:** [English](README.md) | **한국어**

[![Kakao PlayMCP 10 3rd Prize](https://img.shields.io/badge/Kakao_PlayMCP_10-3rd_Prize_🏆-CD7F32)](https://playmcp.kakao.com/)
[![smithery badge](https://smithery.ai/badge/@rabqatab/lexlink-ko-mcp)](https://smithery.ai/server/@rabqatab/lexlink-ko-mcp)
[![MCP](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LexLink는 대한민국 국가법령정보 API ([open.law.go.kr](https://open.law.go.kr/))를 감싼 MCP (Model Context Protocol) 서버입니다. AI 에이전트가 한국 법령, 판례, 해석례 등을 검색하고 조회할 수 있습니다.

## 제공 기능

- **도구 66개**, **프롬프트 9개**, **리소스 2개** (v2.2.0, 그리고 [CHANGELOG.md](CHANGELOG.md)의 미배포 변경 사항).
- 시행일/공포일 기준 법령, 단일 조문(`jo`), 영문 법령, 행정규칙, 자치법규, 조약.
- 판례, 헌재결정례, 법령해석례, 행정심판례, 위원회 결정문, 중앙부처 해석, 특별행정심판.
- `law_as_of`: 특정 날짜에 시행 중이던 법령(또는 한 조문).
- `article_citation`: law.go.kr HTML에서 한 조문이 인용하는 법령을 추출(LLM 미사용). 범위 인용, 삭제된 조문 등 한계는 [API 레퍼런스](docs/API_REFERENCE.md#알려진-한계)에 있습니다.
- AI 의미 검색(`aiSearch`, `aiRltLs_search`)과 한 번에 실행하는 체인 도구(`chain_*`).
- 도구별 TTL 캐시, 법령 약칭 해석(예: 자통법).
- 기본 응답은 JSON이며 `type="XML"`, `"HTML"`도 선택할 수 있습니다.
- 오류는 `{status: "error", error_code, message, hints, request_id}` 형태로 반환됩니다.

도구 이름과 인자는 모두 [API 레퍼런스](docs/API_REFERENCE.md#lexlink-도구-목록)에 있습니다.

## 도구 그룹

| 그룹 | 도구 |
|---|---|
| 법령 | `eflaw_search`, `law_search`, `eflaw_service`, `law_service`, `eflaw_josub`, `law_josub`, `law_as_of`, `elaw_search`, `elaw_service` |
| 행정규칙, 자치법규, 연계 | `admrul_*`, `ordin_*`, `ordinLsCon_search`, `lnkLs_search`, `lnkLsOrdJo_search`, `lnkDep_search`, `drlaw_search`, `lsDelegated_service` |
| 판례와 결정례 | `prec_*`, `detc_*`, `expc_*`, `decc_*`, `committee_*`, `cgm_expc_*`, `special_decc_*` |
| 조약 | `trty_search`, `trty_service` |
| AI 검색, 지식베이스 | `aiSearch`, `aiRltLs_search`, `lstrm_ai_search`, `dlytrm_search`, `lstrm_rlt_search`, `dlytrm_rlt_search`, `lstrm_rlt_jo_search`, `jo_rlt_lstrm_search`, `ls_rlt_search` |
| 이력, 비교, 별표, 용어사전 | `oldAndNew_*`, `thdCmp_*`, `lsJoHstInf_search`, `lsHstInf_search`, `delHst_search`, `lsAbrv_search`, `licbyl_search`, `lstrm_*` |
| 분석 | `article_citation`, `check_precedent_odds`, `legal_resolver`, `simplify_article`, `law_amendment_summary`, `article_amendment_diff` |
| 체인, 운영 | `chain_full_research`, `chain_amendment_track`, `chain_dispute_prep`, `chain_law_system`, `cache_stats` |

어떤 도구로 시작할지:

| 상황 | 시작 도구 |
|---|---|
| 일상 언어의 막연한 질문 | `legal_resolver`, `aiSearch`, `aiRltLs_search` |
| 법령명과 조문 번호 | `eflaw_search`(MST 확인) 후 `eflaw_josub` / `eflaw_service`에 `jo` 지정 |
| "특정 날짜에 법이 어땠나?" | `law_as_of` |
| 개정 신구조문 대비 | `oldAndNew_search` 후 `oldAndNew_service` |
| 법률, 시행령, 시행규칙 나란히 보기 | `thdCmp_search` 후 `thdCmp_service`에 `jo` 지정 (없으면 매우 큼) |
| 법령용어의 뜻 | `lstrm_search` 후 `lstrm_service`(사전); `lstrm_ai_search`는 연관 용어 링크만 제공 |
| 판례 주제 조사 | `prec_search`, `detc_search`, `chain_dispute_prep` |

조문 본문은 항상 `jo`를 지정하세요(예: `35`, `"35의5"`, `"제35조의5"`, `"003505"`; 6자리로 정규화됨). 지정하지 않으면 법령에 따라 응답이 매우 커질 수 있습니다.

**프롬프트:** `search-korean-law`, `get-law-article`, `get-article-with-citations`, `analyze-law-citations`, `search-admin-rules`, `tool-selection-guide`, `analyze-legal-situation`, `explain-legal-document`, `check-legal-precedent`.

**리소스:** `lexlink://laws/frequently-used`(자주 쓰는 법령 약 20개의 법령ID 매핑)와 템플릿 `lexlink://law/{name}`(예: `lexlink://law/자통법`처럼 중괄호 없이 읽음. 이름을 URL 디코딩하고 resolver 별칭을 적용하며, 없으면 `law_search` 정확 일치 조회를 한 번 수행).

## 빠른 시작

Python 3.10+와 [uv](https://docs.astral.sh/uv/)가 필요합니다. [open.law.go.kr](https://open.law.go.kr)에서 발급받는 **OC**(등록한 이메일의 `@` 앞부분)도 필요합니다. law.go.kr은 OC와 호출 IP를 함께 검증하므로, LexLink를 실행하는 장비의 IP를 등록해야 할 수 있습니다.

```bash
uv sync

# stdio (Claude Code, Cursor 등 로컬 MCP 클라이언트)
OC=<OC> uv run stdio

# Streamable HTTP, /mcp (HTTP 모드는 인증 설정 없이는 시작되지 않음)
OC=<OC> LEXLINK_AUTH_TOKENS=local:<TOKEN> TRANSPORT=http uv run serve
```

서버는 `.env`를 직접 읽지 않습니다. 환경변수를 export 하거나 `uv run --env-file .env stdio`로 실행하세요.

`OC`는 도구 인자 `oc`가 먼저, 없으면 환경변수 `OC`를 사용합니다. **HTTP 모드에서는 `oc` 인자를 무시**하고 항상 서버의 `OC`를 사용합니다.

HTTP 배포(인증, TLS 프록시, 속도 제한, 로깅)는 [docs/OPERATIONS.md](docs/OPERATIONS.md)를 보세요.

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `OC` | *(필수)* | law.go.kr API 식별자 |
| `LEXLINK_BASE_URL` | `http://www.law.go.kr` | 업스트림 기본 URL |
| `LEXLINK_TIMEOUT` | `60` | 업스트림 요청 타임아웃(초) |
| `SLIM_RESPONSE` | 미설정 | `1`/`true`/`yes`/`on`이면 PlayMCP 같은 크기 제한 환경용 압축 모드: `ranked_data`가 있으면 `raw_content` 제거, 압축 상한 유지(발췌 500자, 상위 10/3건, 위임 항목 80건), 20,000바이트를 넘는 결과는 줄이고 `truncated`, `truncated_notes`로 표시. 미설정이면 이미 가져온 내용은 자르지 않음(예외: `simplify_article`은 법률 용어를 최대 20개까지만 조회) |
| `TRANSPORT` | `sse` | HTTP 서버 전용: `http`(권장) 또는 `sse` |

HTTP 전용 변수(`HOST`, `PORT`, `LEXLINK_AUTH_TOKENS`, 속도 제한, 로깅 등)는 [docs/OPERATIONS.md](docs/OPERATIONS.md)에 있습니다.

### 예시

```python
eflaw_search(query="자동차관리법", display=5)
# {"status": "ok", "request_id": "...", "upstream_type": "JSON", "ranked_data": ..., "raw_content": ...}

eflaw_josub(mst="<검색 결과의 MST>", jo="제3조")
```

오류 코드: `VALIDATION_ERROR`, `TIMEOUT`, `UPSTREAM_ERROR`, `INTERNAL_ERROR`, `NOT_FOUND`, `ARTICLE_NOT_FOUND`, `EMPTY_RESPONSE`, `API_NOT_SUBSCRIBED`, `UPSTREAM_HTML_ERROR`. [API 레퍼런스](docs/API_REFERENCE.md#appendix-c-lexlink-구조화-오류-코드)를 보세요.

## 문서

| 문서 | 내용 |
|---|---|
| [docs/README.md](docs/README.md) | 문서 목차 |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | 도구 목록, 인자, 업스트림 API 카탈로그, 한계 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | HTTP 서버: 배포, 인증, TLS 프록시, 로깅 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 코드 구조, 테스트, 도구 추가 |
| [CHANGELOG.md](CHANGELOG.md) | 릴리스 이력, 미배포 변경 사항 |
| [AGENTS.md](AGENTS.md) | 코딩 에이전트용 안내 |

## 기여

포크, 브랜치 생성, 테스트 추가, `uv run pytest tests/` 실행 후 Pull Request를 열어 주세요. 자세한 내용은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)를 보세요.

## 라이선스

이 저장소에는 LICENSE 파일이 없습니다.

## 감사의 말

- **law.go.kr** - 국가법령정보 API
- **MCP** - Anthropic의 Model Context Protocol
- **[korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp)** - 캐싱, 법령명 해석, 체인 도구의 영감

## 지원

- 이슈: [GitHub Issues](https://github.com/rabqatab/LexLink-ko-mcp/issues)
- law.go.kr API: [open.law.go.kr](https://open.law.go.kr/)
