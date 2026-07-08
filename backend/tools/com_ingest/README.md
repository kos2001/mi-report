# COM 인제스트 워커 — Windows DRM 환경 테스트 가이드

DRM 클라이언트가 설치된 Windows 에서, 인가된 사용자 권한으로 MS Office 문서를
COM 자동화로 열어(=DRM 에이전트가 투명 복호화) 텍스트를 추출해 백엔드에 등록한다.
일반(비 DRM) 문서는 로컬 파서(PyMuPDF/python-docx 등)로 Office 기동 없이 추출된다.

## 사전 조건

- Windows 10/11, **대화형 로그인 세션** (DRM 에이전트는 보통 로그인 사용자 컨텍스트에서
  복호화한다 — 서비스/RDP 세션 분리 시 동작하지 않을 수 있음)
- DRM 클라이언트 설치 + 로그인 상태, 테스트 문서에 대한 **열람 권한** 보유
- MS Office (Word/Excel/PowerPoint) 설치, 라이선스 활성화 완료
  (첫 실행 시 활성화 대화상자가 뜨면 COM 이 행 → 미리 한 번 수동 실행해 둘 것)
- Python 3.11+, 백엔드 URL 접근 가능 (`http://<backend-host>:8000`)

## 설치

```bat
git clone https://github.com/kos2001/mi-report.git
cd mi-report\backend
python -m venv .venv
.venv\Scripts\activate
pip install .[windows,pdf,office]
:: 이미지 OCR/VLM 까지 테스트하려면:
pip install .[windows,pdf,office,ocr]
set MI_VLM=1& set OPENROUTER_API_KEY=<키>   :: VLM(차트 요약) 선택
:: PDF COM 폴백 엔진: 기본 word(MS Office). Acrobat 전체 제품(Reader 아님) 보유 시:
set MI_PDF_COM_ENGINE=acrobat   :: (선택) Acrobat IAC/JSObject 추출(품질↑)
```

## 1단계 — dry-run (등록 없이 추출 검증) ★ 여기부터

DRM 문서 몇 개를 폴더에 모아 놓고:

```bat
python -m tools.com_ingest.worker "C:\test-docs" --dry-run
```

파일별로 `경로=local|com`, 글자 수, 본문 미리보기가 출력된다. 확인 포인트:

| 파일 | 기대 결과 | 아니라면 |
|---|---|---|
| DRM .docx/.xlsx/.pptx | `경로=com` + **읽을 수 있는 평문** | `경로=local`인데 깨진 텍스트 → DRM 이 zip 구조를 유지하는 제품 — 보고 필요(로컬 파서 차단 로직 추가해야 함) |
| **DRM .pdf** | `경로=com` (기본 Word 리플로우) + 평문 | `[fail]`/타임아웃 → 나스카가 Word 를 PDF 인가 앱으로 안 둠. Acrobat Pro 있으면 `set MI_PDF_COM_ENGINE=acrobat`, 없으면 나스카 반출 승인 |
| 일반 .pdf/.docx | `경로=local` (즉시, Office 미기동) | — |
| 스캔 PDF (ocr 설치 시) | `경로=local` + OCR 텍스트 | 빈약하면 한국어 인식 모델 필요(`MI_OCR_REC_MODEL`) |

행이 걸리면 파일당 120초(조정: `--timeout`) 후 해당 Office 프로세스를 강제 종료하고
다음 파일로 넘어간다. `[fail] ... 초과 (DRM 대화상자/행 의심)` 메시지가 그 신호다.

### 텍스트만 로컬로 뽑기 (`--out`, 백엔드 불필요)

DRM PDF 등에서 **본문 텍스트만 파일로** 받고 싶을 때. 백엔드 없이 추출 텍스트 전체를
`<폴더>/<파일명>.txt` 로 저장한다(전송·매니페스트 없음). Word 엔진(기본)만 있으면
되므로 무료 Reader 환경에서도 추가 SW 가 필요 없다.

```bat
python -m tools.com_ingest.worker "C:\pdf-inbox" --out "C:\extracted"
:: [out] C:\pdf-inbox\a.pdf → C:\extracted\a.txt | 경로=com | 4210자
```

## 2단계 — 실제 등록 (배치)

백엔드가 떠 있는지 확인 후:

```bat
python -m tools.com_ingest.worker "C:\test-docs" --backend http://<backend-host>:8000 --topic 테스트
```

- `[ok]` 건수 확인 → 대시보드/`GET /collection/documents?q=<제목>` 으로 검색 확인
- **같은 명령 재실행** → 전부 `[skip] (변경 없음)` 이어야 함(매니페스트)
- `--force` 재실행 → 서버가 `deduped` 로 응답, 신규 등록 0건이어야 함(해시 멱등)

## 트러블슈팅

- **모든 파일이 행/타임아웃**: DRM 에이전트 미로그인 또는 권한 없음. 같은 문서를
  탐색기에서 더블클릭해 열리는지 먼저 확인.
- **좀비 WINWORD/EXCEL 누적**: 타임아웃 시 PID 를 못 찾으면(특히 Word) 숨은 프로세스가
  남을 수 있다 — 작업관리자에서 정리. 반복되면 `--timeout` 을 늘려볼 것.
- **404 오류**: 백엔드 URL 확인(구버전 백엔드면 `/collection/ingest/batch` 가 없음 —
  백엔드 업데이트 필요).
- **한 파일 때문에 배치 실패 반복**: 4xx 는 자동으로 단건 격리되므로, `[fail]` 난
  파일만 원인 확인(빈 본문, 초대형 등).

## 테스트 후 보고해 주세요

1. dry-run 출력(경로/글자수 분포, 특히 **DRM PDF 가 com 경로로 성공했는지**)
2. 행/타임아웃 발생 파일 유형과 빈도
3. 사용 중인 DRM 제품명 (→ 서버용 복호화 SDK 확보 가능 여부 검토, COM 대비 수십 배)
4. 한국어 스캔 문서가 있다면 OCR 품질 체감
