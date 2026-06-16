# MI Report Agent — Backend

**agno + OpenRouter**(OpenAI 호환)를 LLM 엔진으로 쓰는 FastAPI 백엔드.
수집 → 분류 → AI 생성(다이제스트·주제·경쟁사·RAG·리포트)을 제공한다.

## 프로파일 구조

LLM 연결 설정은 **프로파일**로 관리한다. provider 만 갈아끼우면 다른 OpenAI 호환
엔드포인트(온프렘 모델 등)로도 동작한다.

```
backend/
  active_profile            # 활성 프로파일 이름 (기본: mi-report)
  profiles/
    mi-report/
      config.yaml           # model.default / model.provider / model.base_url / providers
      .env                  # 시크릿 (OPENROUTER_API_KEY 등) — .gitignore 처리
```

- 프로파일 이름 규칙: `^[a-z0-9_][a-z0-9_-]{0,63}$`
- 활성 프로파일 우선순위: 환경변수 `MI_ACTIVE_PROFILE` > `active_profile` 파일 > 기본값 `mi-report`

## 설정

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[embeddings]'      # 임베딩 하이브리드 검색 포함

# profiles/mi-report/.env 에 LLM 키 설정
#   OPENROUTER_API_KEY=sk-or-...
#   OPENROUTER_MODEL=deepseek/deepseek-v4-flash   (선택, 기본값)
#   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1  (선택; 사내 게이트웨이면 그 주소)
#   MI_EMBEDDINGS=1                               (선택, 의미 임베딩 검색)
#   MI_EMBED_BACKEND=openrouter                   (선택; fastembed(로컬, 기본) | openrouter)
#   MI_EMBED_MODEL=baai/bge-m3                     (선택; 다국어·한국어 강함. openrouter 기본 bge-m3)
#   MI_RERANK_MODEL=cohere/rerank-v3.5            (선택; 설정 시 OpenRouter 전용 rerank, 미설정 시 LLM 재정렬)
#   LLM_SERVICE_ID / LLM_USER_ID                  (선택; 사내 LLM 요청에 x-service-id / x-user-id 헤더 첨부)

uvicorn app.main:app --reload --port 8000
```

LLM 호출은 `app/gateway.py`(`LLMClient`)가 `OPENROUTER_*` 환경변수를 읽어 agno 의
OpenRouter 모델로 수행한다. 키가 없으면 AI 생성 엔드포인트는 401 로 안내하고,
데이터 수집·문서 관리·임베딩 검색은 키 없이도 동작한다.

## 엔드포인트(주요)

| 분류 | 메서드/경로 | 설명 |
|---|---|---|
| 프로파일 | `GET /profiles` | 프로파일 목록 + 활성 프로파일 |
| 수집 | `… /collection/*` | 소스·문서·업로드·수집 트리거 |
| AI 생성 | `POST /digest/generate` `…/topics/summarize` `…/competitors/analyze` `…/report/generate` | LLM 생성물 |
| 문서 Q&A | `POST /rag/query` | 하이브리드 검색 + LLM 답변(근거 인용) |
| 지식 자산 | `GET /artifacts` `POST /feedback` | 생성물 이력 + 피드백 |

대화형 문서: 실행 후 `http://localhost:8000/docs`.

## COM 인제스트 워커 (Windows 전용)

DRM 보호된 MS Office 문서를 입력하기 위한 워커. **DRM 클라이언트 + MS Office 가 설치된
Windows** 에서, 인가된 사용자 권한으로 Word/Excel/PowerPoint 를 COM 자동화로 열면
DRM 에이전트가 투명하게 복호화하고, 그 텍스트를 추출해 백엔드 `/collection/ingest` 에 등록한다.

> 보호를 깨거나 제거하는 것이 아니라, 사용자가 이미 열람 권한을 가진 문서를
> 정식 응용프로그램으로 열어 내용을 읽는 방식이다. macOS/Linux 백엔드와 분리해
> Windows 워커로 운영한다(COM 은 Windows 전용).

```bash
# Windows 워커 호스트에서
pip install -e ".[windows]"      # pywin32 포함
python -m tools.com_ingest.worker "C:\reports\analysis.docx" --backend http://mi-host:8000
python -m tools.com_ingest.worker "C:\reports" --topic HBM         # 폴더 일괄
```

- 지원 포맷: `.doc/.docx/.rtf`(Word), `.xls/.xlsx/.xlsm`(Excel), `.ppt/.pptx`(PowerPoint)
- 추출 로직은 주입 가능한 COM 앱 팩토리 뒤에 있어, Windows 가 아닌 환경에서도
  모의 객체로 단위 테스트된다(`tests/test_com_ingest.py`).
- 운영 주의: 추출된 평문은 DRM 보호 경계를 벗어나므로 사내 보존/접근 정책을 따라야 한다.

## 테스트

```bash
pip install -e ".[dev]"
pytest -q
```

격리된 임시 SQLite/업로드 디렉토리에서 수집·프로파일·LLM 클라이언트·COM 추출을 검증한다
(실제 DB·네트워크·COM 미사용).

## 보안

- LLM API 키(OPENROUTER_API_KEY)는 프로파일 `.env` 에만 둔다. `.env` 와 `profiles/*/.env` 는 `.gitignore` 처리됨.
- 코드에는 키를 넣지 않는다 (`config.yaml` 은 `key_env` 로 환경변수 이름만 가리킴).
- COM 인제스트는 인가된 사용자의 정식 열람을 자동화하는 것이며, 추출 평문의 보관은 사내 정책을 따른다.
