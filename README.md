# MI Report Agent

반도체/IT 시장 인텔리전스(MI) 리포트 작성을 자동화하는 에이전트.
시장 센싱·뉴스 다이제스트·경쟁사 IR 분석을 한 곳에서 다룬다.

## 구성

```
mi-report/
├── frontend/   # Next.js 16 + React 19 + Tailwind v4 대시보드
└── backend/    # FastAPI — Hermes Gateway(OpenAI 호환)로 Hermes Agent 전체 기능 사용
```

## 주요 기능

- **데이터 수집** — 소스(EDM·Confluence·뉴스·증권사·컨센서스) 관리, 수집 상태·트리거, 수동 업로드, 문서 조회
- **주제별 History** — 누적 정보 기반 주제 이력·요약·시황 인사이트
- **뉴스 다이제스트** — 주 2회 기술 뉴스 요약 + S.LSI 연관성·수요·리스크 영향도
- **경쟁사 IR** — 분기 실적 요약, 컨퍼런스콜 요약, 전분기 대비 변화, 증권사 컨센서스 추적

## 실행

**프론트엔드**
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

**백엔드** (Hermes Gateway 연동 — 자세한 설정은 `backend/README.md`)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp profiles/hermes/.env.example profiles/hermes/.env   # 게이트웨이 토큰 입력
uvicorn app.main:app --reload --port 8000              # http://localhost:8000/docs
```

## 현황

- 프론트엔드 대시보드/주제/다이제스트/경쟁사 화면: 목업 데이터 (백엔드 연동 전)
- 데이터 수집 페이지: 백엔드(SQLite) 실연동 — 업로드·문서·소스 관리 동작
- 커넥터(EDM/Confluence/뉴스) 실제 크롤링: 스텁 (이후 단계 연동 예정)
