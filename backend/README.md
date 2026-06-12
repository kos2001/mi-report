# MI Report Agent — Backend

Hermes Gateway(OpenAI 호환)를 **LLM/에이전트 게이트웨이**로 사용하는 FastAPI 백엔드.
Hermes Agent CLI 의 전체 기능(에이전틱 run + 툴셋, 세션, 승인, 스트리밍)을 HTTP 로 노출한다.

## 프로파일 구조 (hermes-desktop-new 참조)

연결 설정은 **프로파일**로 관리한다. 프로파일만 갈아끼우면 다른 게이트웨이로도 동작한다.

```
backend/
  active_profile            # 활성 프로파일 이름 (예: hermes)
  profiles/
    hermes/
      config.yaml           # model.default / model.provider / model.base_url / providers
      .env                  # 시크릿 (HERMES_GATEWAY_API_KEY) — .env.example 복사해서 생성
      .env.example
      SOUL.md               # 페르소나 (선택)
```

- 프로파일 이름 규칙: `^[a-z0-9_][a-z0-9_-]{0,63}$` (hermes-desktop-new 와 동일)
- 활성 프로파일 우선순위: 환경변수 `MI_ACTIVE_PROFILE` > `active_profile` 파일 > 기본값 `hermes`

## 설정

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 게이트웨이 토큰 설정 (Hermes 설치본의 platforms.api_server.token 값)
cp profiles/hermes/.env.example profiles/hermes/.env
# .env 의 HERMES_GATEWAY_API_KEY= 에 토큰을 채운다

# 실행
uvicorn app.main:app --reload --port 8000
```

`profiles/hermes/config.yaml` 의 `base_url` 은 Hermes Gateway 주소(`http://127.0.0.1:8642/v1`)를 가리킨다.
게이트웨이가 떠 있어야 한다(`hermes` 실행 시 api_server 플랫폼이 8642 포트로 기동).

## 엔드포인트

| 분류 | 메서드/경로 | 설명 |
|---|---|---|
| 프로파일 | `GET /profiles` | 프로파일 목록 + 활성 프로파일 |
| 디스커버리 | `GET /gateway/capabilities` `…/models` `…/skills` `…/toolsets` | 게이트웨이 기능/모델/스킬/툴셋 |
| 대화 | `POST /chat` | 단순 OpenAI 호환 chat completion |
| 에이전틱 | `POST /runs` | 전체 툴셋으로 에이전트 run 시작 (run_id 반환) |
| 에이전틱 | `GET /runs/{id}` `…/events`(SSE) `POST …/approval` `…/stop` | run 상태/이벤트/승인/중단 |
| 세션 | `GET/POST /sessions`, `…/{id}/messages`, `…/chat`, `…/fork`, `DELETE …/{id}` | 세션 관리 |

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

격리된 임시 SQLite/업로드 디렉토리에서 수집·프로파일·게이트웨이 구성·COM 추출을 검증한다
(실제 DB·네트워크·COM 미사용).

## 보안

- 게이트웨이 토큰은 프로파일 `.env` 에만 둔다. `.env` 와 `profiles/*/.env` 는 `.gitignore` 처리됨.
- 코드에는 키를 넣지 않는다 (`config.yaml` 은 `key_env` 로 환경변수 이름만 가리킴).
- COM 인제스트는 인가된 사용자의 정식 열람을 자동화하는 것이며, 추출 평문의 보관은 사내 정책을 따른다.
