# 나스카(NASCA) DRM PDF — Notepad++ 활용 처리 절차

전제: **본인이 열람 권한을 가진, 소속 조직 소유의 문서**에 한함. 나스카 에이전트가
설치·로그인된 Windows에서만 성립. 권한 없는 문서의 우회·에이전트 무력화·키 추출은
대상이 아니다.

## 먼저 알아야 할 것 — 나스카는 표준 PDF 암호가 아니다

| 구분 | 표준 PDF 암호 | 나스카(NASCA) DRM |
|---|---|---|
| 방식 | 파일 안 `/Encrypt`(RC4/AES), 비밀번호로 복호화 | 에이전트가 커널에서 파일 I/O를 가로채 **인가 프로세스에만** 투명 복호화. 키는 정책서버 |
| 로컬 도구로 해제 | 비밀번호 있으면 qpdf/pikepdf로 가능 | **불가** — Notepad++·qpdf·pikepdf 모두 안 됨 |
| 잠금 해제 정식 경로 | 비밀번호 입력 | **나스카 반출/복호화 승인**(승인자 기반) |

즉 Notepad++가 나스카 암호를 "푸는" 건 원천적으로 불가능하다. 대신 Notepad++는
아래 두 가지 실효적 역할을 한다.

## 역할 1 — Notepad++로 "에이전트 판독 여부" 진단 (1분)

대상 PDF를 Notepad++로 연다(에이전트 설치 PC에서). 맨 앞 바이트를 본다:

- **`%PDF-1.x` 로 시작 + 정상 PDF 구조** → 나스카 에이전트가 Notepad++에게도
  투명 복호화해 주는 상태(= Notepad++가 정책상 인가 앱이거나, 파일이 실제로는
  보호 안 됨). 단 PDF는 바이너리라 여기서 **본문 판독은 안 됨** → 역할 2로.
- **고엔트로피 바이너리 / 소프트캠프·NASCA 매직 헤더 / `%PDF` 아님** → 에이전트가
  Notepad++에는 복호화를 안 해줌(미인가 앱). 이 PC·이 앱으로는 못 읽는다는 신호.

이 진단으로 "내 환경에서 인가된 앱이 무엇인가"가 바로 갈린다.

## 역할 2 — Notepad++를 추출 실행 콘솔로 (NppExec)

PDF 본문은 인가된 뷰어가 열어야 나온다. 이 저장소의 COM 워커가 그 일을 한다
(인가된 Word가 COM으로 PDF를 리플로우로 열면 에이전트가 투명 복호화 → 텍스트 추출).
Notepad++의 **NppExec 플러그인**으로 이 추출을 Notepad++ 안에서 실행한다.

### 설치
- Notepad++ → 플러그인 → Plugins Admin → **NppExec** 설치
- 백엔드 저장소가 PC에 있고 `.venv`에 `pip install .[windows,pdf,office]` 완료돼 있을 것

### NppExec 스크립트 (F6 → 붙여넣기 → Save as `NASCA-extract`)

현재 열려 있는 탭의 파일을 추출·검증(등록 안 함, dry-run):

```
npp_save
cd "C:\mi-report\backend"
"C:\mi-report\backend\.venv\Scripts\python.exe" -m tools.com_ingest.worker "$(FULL_CURRENT_PATH)" --dry-run
```

폴더 전체를 백엔드에 실제 등록하려면 별도 스크립트로:

```
cd "C:\mi-report\backend"
"C:\mi-report\backend\.venv\Scripts\python.exe" -m tools.com_ingest.worker "C:\test-docs" --backend http://<backend-host>:8000 --topic 테스트
```

- 실행 결과(경로=`com`/`local`, 글자 수, 본문 미리보기)가 **NppExec 콘솔에 그대로** 뜬다.
  DRM PDF가 `경로=com` + 읽을 수 있는 평문으로 나오면 성공.
- `[fail]`/타임아웃(`DRM 대화상자/행 의심`)이면 나스카가 Word 경유 PDF 열기에
  복호화를 안 걸어주는 것 → 아래 '정식 경로'로.
- 경로를 `Macro → 단축키`에 바인딩하면 PDF 탭에서 키 하나로 추출 콘솔이 뜬다.

## PDF 전용 — 가장 까다로운 케이스

PDF는 나스카에서 Word 경유 복호화가 보장되지 않는 약한 고리다. 순서:

### 1) dry-run으로 Word COM 경로가 되는지 먼저 판정
PDF는 Notepad++ 탭으로 열 필요 없이, **인박스 폴더**를 NppExec로 돌린다
(F6 → `NASCA-pdf-drylun` 로 저장):

```
cd "C:\mi-report\backend"
"C:\mi-report\backend\.venv\Scripts\python.exe" -m tools.com_ingest.worker "C:\pdf-inbox" --dry-run
```

콘솔 판정:
| dry-run 결과 | 의미 | 조치 |
|---|---|---|
| `경로=com` + 평문 | Word가 PDF 인가 앱 → 복호화 성공 | 그대로 등록 진행 |
| `[fail]`/타임아웃(DRM 대화상자 의심) | Word 경유 PDF 복호화 미지원 | 대안 A 또는 B |
| `경로=com`인데 글자 깨짐/뒤섞임 | 리플로우 변환 손실 | 대안 A(비보호 PDF→PyMuPDF) |
| `경로=local`인데 빈약 | 스캔 PDF | OCR 활성(`[ocr]` extras + 한국어 인식 모델) |

### 2) 판정 결과별 경로
- **Word OK** → `--dry-run` 떼고 `--backend`로 등록
- **Word 실패/품질↓ → 대안 A(권장)**: 나스카 반출/복호화 승인 또는 서버측 SDK로
  비보호 PDF 확보 → `pdftext.py`(PyMuPDF)가 로컬 고속·고품질 처리(스캔본 OCR 자동)
- **Acrobat이 인가 앱 → 대안 B(구현 완료)**: PDF COM 폴백을 Acrobat COM(`AcroExch`
  + JSObject)로 처리하는 추출기가 워커에 들어갔다. 나스카 환경 기본값이며 Word
  리플로우보다 표·다단 PDF 품질이 낫다.

  ```bat
  :: 기본이 acrobat 이라 별도 설정 불필요. Word 리플로우로 되돌리려면:
  set MI_PDF_COM_ENGINE=word
  ```

  전제: Adobe Acrobat **전체 제품(Pro/Standard)** 설치 — 무료 Reader 는 IAC/JSObject
  미지원. 나스카 정책에서 Acrobat 이 PDF 인가 뷰어여야 투명 복호화가 걸린다.
  주의: Acrobat 프로세스는 창 핸들 역추적이 안 돼, 모달로 행 걸리면 워커가 PID 로
  강제 종료하지 못한다(타임아웃 후 경고만) — 작업관리자에서 정리 필요.

## 잠금이 풀린 "파일 자체"가 필요하면 — 나스카 정식 반출/복호화 승인

Notepad++/COM은 **본문 텍스트**를 얻는 경로다. 보호가 제거된 **PDF 파일 자체**가
필요하면(예: 외부 공유), 나스카 관리 콘솔의 **반출(외부반출)/복호화 승인** 절차를
쓴다 — 승인자가 승인하면 에이전트가 비보호 사본을 생성해 준다. 이게 우회가 아닌
사내 표준 방법이며, 감사 로그도 남는다. 절차/승인자는 보안팀에 문의.

## 요약 흐름

```
DRM PDF (나스카)
 ├─ Notepad++로 열기 → 앞바이트 진단 (인가앱 여부 확인)
 ├─ 본문 텍스트가 목적 → NppExec로 COM 워커 실행(인가 Word가 복호화) → 콘솔에 평문
 └─ 비보호 파일이 목적 → 나스카 반출/복호화 승인 (보안팀 승인)
```

대량·자동화가 필요하면 소프트캠프 서버측 복호화 SDK가 COM보다 수십 배 빠르나,
보안팀 승인이 전제다.
