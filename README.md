# MI Report Agent

반도체/IT 시장 인텔리전스(MI) 리포트 작성을 자동화하는 에이전트.
시장 센싱·뉴스 다이제스트·경쟁사 IR 분석을 한 곳에서 다룬다.

## 구성

```
mi-report/
├── frontend/   # Next.js 16 + React 19 + Tailwind v4 대시보드
└── backend/    # FastAPI — agno + OpenRouter(OpenAI 호환) LLM 으로 AI 기능 제공
```

## 주요 기능

- **데이터 수집** — 소스(EDM·Confluence·뉴스·증권사·컨센서스) 관리, 수집 상태·트리거, 수동 업로드, 문서 조회
- **주제별 History** — 누적 정보 기반 주제 이력·요약·시황 인사이트
- **뉴스 다이제스트** — 주 2회 기술 뉴스 요약 + S.LSI 연관성·수요·리스크 영향도
- **경쟁사 IR** — 분기 실적 요약, 컨퍼런스콜 요약, 전분기 대비 변화, 증권사 컨센서스 추적

## 실행

**Docker Compose**
```bash
# OPENROUTER_API_KEY 등 시크릿은 backend/profiles/mi-report/.env 에 둔다.
docker compose up -d --build

# 상태 확인
docker compose ps

# 종료
docker compose down
```

- 프론트엔드: http://localhost:3000
- 백엔드: http://localhost:8000
- 백엔드 헬스 체크: `GET http://localhost:8000/health`

최근 Docker 검증 결과:

| 항목 | 결과 |
|---|---|
| `docker compose build` | 성공 |
| `docker compose up -d` | 성공 |
| 백엔드 헬스 체크 | `{"status":"ok","active_profile":"mi-report"}` |
| 백엔드 API 스모크 테스트 | `GET /collection/sources` 성공 |
| 프론트엔드 스모크 테스트 | `GET /` → HTTP 200 OK |
| Next.js 정적 asset 로딩 | `/_next/static/*.js` → HTTP 200 OK |
| 생성 이미지 | `mi-report-backend:latest`(약 137MB), `mi-report-frontend:latest`(약 195MB) |

컨테이너 로그에서 백엔드는 `Application startup complete`, 프론트엔드는 `Ready` 상태를 확인했다.

**로컬 개발 실행**

**프론트엔드**
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

**백엔드** (agno + OpenRouter LLM — 자세한 설정은 `backend/README.md`)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[embeddings]'
# profiles/mi-report/.env 에 OPENROUTER_API_KEY 입력 (모델 기본값: minimax/minimax-m3)
# MI_SCHEDULER=1 없으면 /schedule 에서 설정한 주기(매일/매주)가 자동 실행되지 않는다
# (설정 자체는 되지만, 앱 내 스케줄러가 꺼져 있으면 아무 일도 일어나지 않는다).
MI_SCHEDULER=1 uvicorn app.main:app --reload --port 8000  # http://localhost:8000/docs
```

## 현황

- 프론트엔드 대시보드/주제/다이제스트/경쟁사 화면: 목업 데이터 (백엔드 연동 전)
- 데이터 수집 페이지: 백엔드(SQLite) 실연동 — 업로드·문서·소스 관리 동작
- 커넥터(EDM/Confluence/뉴스) 실제 크롤링: 스텁 (이후 단계 연동 예정)
