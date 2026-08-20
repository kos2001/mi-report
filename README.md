# MI Report Agent

반도체·IT 시장 인텔리전스(MI) 업무를 위한 수집, 검색, 분석, 리포트 생성 에이전트입니다.
실제 문서 코퍼스를 기반으로 뉴스 다이제스트, 주제별 History, 경쟁사 IR, 문서 Q&A와
주간 리포트를 생성하고 결과를 이력과 LLM Wiki에 누적합니다.

## 아키텍처

```text
외부/사내 소스
  ├─ Confluence · 뉴스 URL · 증권사/한경 컨센서스
  ├─ SEC EDGAR · DART
  ├─ EDM/Windows COM 인제스트
  └─ 수동 파일 업로드
          │
          ▼
FastAPI + SQLite
  ├─ 원문 파일·문서 메타데이터
  ├─ SQLite FTS5 / BM25 색인
  ├─ Embedding vector DB
  ├─ 생성물·피드백·Q&A 세션
  └─ LLM Wiki (Markdown)
          │
          ├─ BM25 + 동의어 ─┐
          └─ 의미 임베딩 ───┴─ Hybrid RRF → reranker → Q&A/근거 조회
          │
          └─ LLM 생성 → 다이제스트·주제·경쟁사·주간 리포트
                                      │
                                      └─ 주차별 LLM Wiki → 다음 생성 맥락
```

```text
mi-report/
├── frontend/                 # Next.js 16 · React 19 · Tailwind CSS v4
├── backend/                  # FastAPI · SQLite · LLM/검색 파이프라인
│   ├── app/
│   ├── profiles/mi-report/   # 모델/provider 설정
│   ├── tests/
│   └── data/                 # 로컬 DB·업로드·Wiki·백업(gitignore)
└── docker-compose.yml
```

## 주요 기능

### 데이터 수집

- 소스 등록, 활성화·비활성화, 설정 확인, 즉시 수집
- 실제 커넥터: Confluence, 뉴스 URL, SEC EDGAR, DART, 한경 컨센서스
- Windows COM 워커를 통한 권한 있는 DRM Office 문서 텍스트 인제스트
- 다중 파일 수동 업로드와 주제 태깅
- 동일 URL 소스와 문서 중복 관리
- 문서별 추출 본문, 원본 URL, 수집 소스, 발행일 확인

소스 화면은 저장된 `status` 문자열만 보여주지 않고 다음 조건으로 실제 운영 상태를 계산합니다.

| 상태 | 판정 기준 |
|---|---|
| 활성·정상 | 활성화, 필수 설정 확인, 최근 48시간 내 실행, 수집 문서 존재 |
| 활성·대기 | 설정 완료, 실행 기록 없음 |
| 활성·결과 없음 | 최근 실행했지만 수집 문서 없음 |
| 활성·점검 필요 | 마지막 실행이 48시간보다 오래됨 |
| 활성·오류 | 마지막 수집 실행 실패 |
| 설정 필요 | URL·경로·CIK·API 인증정보 등 필수 설정 누락 |
| 수동 활성 | 파일 업로드 요청 시 동작 |
| 비활성 | 사용자 설정으로 수집 중지 |

### 검색·RAG

- SQLite FTS5 / BM25 기반 제목·주제·본문 검색
- 반도체 도메인 동의어·약어 확장
  - HBM, CXL, ADAS, AP, ASP, DRAM, 캐파, 선단 패키징 등
- strict BM25와 확장 BM25 결합
- 다국어 의미 임베딩 검색
- BM25와 dense 결과를 Reciprocal Rank Fusion(RRF)으로 결합
- 전용 reranker 또는 LLM 재정렬
- 동일 본문 중복 제거 후 Q&A 컨텍스트 구성
- 검색 품질 평가셋의 recall@k·MRR 회귀 테스트

`/collection/results`에서 BM25 색인 수, 벡터 수·차원·모델, 문서 커버리지를 실제 DB 기준으로 확인할 수 있습니다.

### 문서 Q&A

- Hermes Agent API Server 또는 OpenAI 호환 LLM을 통한 멀티턴 에이전트 대화
- 코퍼스 검색·웹 검색 도구 조합
- 답변 수치의 수집 문서 대조 검증
- 관련 문서 ID·출처·발행일 표시
- Q&A 화면에서 추출 원문과 외부 원본을 직접 열람
- 사용자별 세션 저장, 이력 재개·삭제
- 완료 응답의 핵심 수치, 검증 상태, 근거 문서 시각화

### AI 생성물

- 뉴스 다이제스트: S.LSI 연관성, 수요 영향, 리스크, 영향도
- 주제별 History: 누적 사건, 요약, MI 인사이트
- 경쟁사 IR: 재무, 컨퍼런스콜, QoQ 변화, 컨센서스
- 주간 MI 리포트: 총평, Priority/Risk, Critical Point
- 생성물 피드백과 품질 지표
- 동일 종류·대상의 같은 ISO 주차 생성물은 최신 결과로 교체
- 다른 주차 생성물은 이력으로 누적
- 생성 이력에서 실제 저장 내용을 선택하고 결과 영역으로 이동

### LLM Wiki

다이제스트 생성 결과를 Markdown 지식 계층으로 누적합니다.

```text
backend/data/wiki/
├── SCHEMA.md
├── index.md
├── log.md
├── weekly/       # ISO 주차별 다이제스트
├── concepts/     # 태그별 개념 페이지와 주차별 관측
├── entities/
├── comparisons/
├── queries/
└── raw/
```

- 같은 ISO 주차는 교체하고 다른 주차는 누적
- 개념 페이지에 주차·출처·발행일 연결
- 현재 주차를 제외한 최근 4주를 다음 다이제스트의 보조 맥락으로 사용
- 최종 수치·사실은 항상 원문 코퍼스로 다시 검증
- `MI_WIKI_ENABLED=0`으로 비활성화
- `MI_WIKI_PATH`로 저장 위치 변경

`/collection/results`에서 Wiki 누적 주차, 개념 수, 최신 주차와 저장 경로를 확인할 수 있습니다.

## 주요 화면

| 경로 | 기능 |
|---|---|
| `/` | 전체 파이프라인 대시보드 |
| `/collection` | 소스 추가·설정·운영 상태·즉시 수집·파일 업로드 |
| `/collection/documents` | 문서 검색·필터·분류·원문 확인 |
| `/collection/results` | 수집 현황·주제 분포·BM25·Embedding DB·LLM Wiki 상태 |
| `/ask` | 문서 Q&A·세션 이력·관련 원문 열람 |
| `/digest` | 뉴스 다이제스트 생성·이력 |
| `/topics` | 주제별 History 생성·이력 |
| `/competitors` | 경쟁사 IR 분석·이력 |
| `/report` | 주간 MI 리포트 생성·이력 |
| `/quality` | 근거 검증·피드백 품질 현황 |
| `/schedule` | 자동 수집·생성 주기와 실행 이력 |
| `/settings` | 프로파일·인증·사용자 설정 |

## 빠른 실행

### Docker Compose

시크릿은 `backend/profiles/mi-report/.env`에 저장합니다.

```bash
docker compose up -d --build
docker compose ps

# 종료
docker compose down
```

- 프론트엔드: http://localhost:3000
- 백엔드: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- 헬스 체크: `GET http://localhost:8000/health`

### 로컬 개발

프론트엔드:

```bash
cd frontend
npm install
npm run dev
```

백엔드(Python 3.11 이상):

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,embeddings]'

MI_SCHEDULER=1 uvicorn app.main:app --reload --port 8000
```

## LLM·검색 설정

활성 프로파일은 기본적으로 `backend/profiles/mi-report`입니다.

- 기본 provider: `openrouter`
- 기본 모델: `deepseek/deepseek-v4-flash-0731`
- `OPENROUTER_MODEL`로 모델 재정의 가능
- `MI_LLM_*`를 설정하면 채팅·에이전트 호출만 별도 Hermes/OpenAI 호환 API Server로 라우팅

`backend/profiles/mi-report/.env` 예시:

```bash
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# 채팅·에이전트를 Hermes Agent API Server로 보낼 때
MI_LLM_BASE_URL=http://127.0.0.1:8644/v1
MI_LLM_API_KEY=...
MI_LLM_MODEL=mi-report

# 의미 검색·재정렬
MI_EMBEDDINGS=1
MI_EMBED_BACKEND=openrouter       # fastembed | openrouter
MI_EMBED_MODEL=baai/bge-m3
MI_RERANK_MODEL=cohere/rerank-v3.5

# 앱 내부 스케줄러
MI_SCHEDULER=1

# LLM Wiki
MI_WIKI_ENABLED=1
# MI_WIKI_PATH=/absolute/path/to/wiki
```

Confluence·DART·OIDC 등 추가 환경변수는 `backend/README.md`를 참고하세요.
시크릿은 커밋하지 않습니다.

## 주요 API

| 분류 | 엔드포인트 |
|---|---|
| 상태 | `GET /health`, `GET /profiles` |
| 수집 | `GET /collection/sources`, `POST /collection/sources/{id}/collect` |
| 문서 | `GET /collection/documents`, `GET /collection/documents/{id}` |
| 검색 상태 | `GET /collection/search-infrastructure` |
| RAG | `POST /rag/search`, `POST /rag/query` |
| 에이전트 Q&A | `POST /agent/chat`, `POST /agent/chat/stream`, `GET /agent/sessions` |
| AI 생성 | `POST /digest/generate`, `POST /topics/summarize`, `POST /competitors/analyze`, `POST /report/generate` |
| 생성 이력 | `GET /artifacts`, `GET /artifacts/{id}`, `DELETE /artifacts/{id}` |
| 품질 | `GET /quality/summary`, `POST /feedback` |
| 스케줄 | `GET /schedule`, `POST /pipeline/run` |

전체 스키마는 백엔드 실행 후 http://localhost:8000/docs 에서 확인합니다.

## 테스트·검증

백엔드:

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
```

프론트엔드:

```bash
cd frontend
npm run lint
npm run build
```

현재 전체 회귀 검증 기준:

- 백엔드: `381 passed, 1 skipped`
- 프론트엔드 ESLint: 통과
- Next.js TypeScript·프로덕션 빌드: 통과

테스트는 임시 SQLite와 업로드 디렉터리를 사용하며 실제 운영 DB를 변경하지 않습니다.

## 데이터·보안

- 운영 데이터: `backend/data/collection.db`
- 업로드 원문: `backend/data/uploads/`
- LLM Wiki: `backend/data/wiki/`
- 정리 전 백업: `backend/data/backups/`
- API 키와 토큰: `backend/profiles/*/.env`에 저장하고 Git에서 제외
- Q&A 세션은 사용자 ID별로 분리
- 관리자/조회자 권한 및 OIDC SSO 지원
- DRM 문서 인제스트는 사용자가 열람 권한을 가진 문서를 정식 Office COM으로 여는 방식이며 사내 보존·접근 정책을 따라야 합니다.
