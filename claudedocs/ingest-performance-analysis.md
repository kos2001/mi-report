# COM 인제스트(DRM 문서) 성능 분석 — 2026-07-07

분석 대상: `backend/tools/com_ingest/` (Windows COM 워커) + `backend/app/collection.py` `ingest_text` 경로 + `/collection/ingest` 엔드포인트.

전제: DRM 클라이언트가 설치된 Windows에서 인가된 사용자가 정식 Office 앱(COM)으로 문서를 열어
투명 복호화된 본문을 읽는 구조(보호 우회 아님). 이 전제를 유지한 채 처리량을 높이는 방안만 다룬다.

## 우선순위 요약

| # | 심각도 | 항목 | 위치 | 기대 효과 |
|---|--------|------|------|-----------|
| 1 | 🔴 높음 | 파일마다 Office 프로세스 생성/종료 | `extractors.py` 전체 | 배치 처리 시간 수 배 단축 |
| 2 | 🔴 높음 | PDF 추출기 부재 (기능 공백) | `extractors.py:123` | PDF 인제스트 자체가 불가 → 가능 |
| 3 | 🔴 높음 | 문서 1건당 임베딩 API 1회 (요청 내 동기) | `collection.py:874`, `main.py:336` | 처리량 수 배 (배치 64 활용) |
| 4 | 🟡 중간 | 워커가 파일마다 새 HTTP 커넥션 | `worker.py:22` | TLS 핸드셰이크 제거 |
| 5 | 🟡 중간 | 추출과 전송이 완전 직렬 | `worker.py:64` | 파이프라인화로 지연 겹침 |
| 6 | 🟡 중간 | 재실행 시 중복 인제스트(멱등성 없음) | `collection.py:860` | 재실행 비용 0, 인덱스 비대 방지 |
| 7 | 🟢 낮음 | 임베딩 입력 길이 무제한 | `collection.py:402` | API 비용/지연 절감 |
| 8 | 🟢 낮음 | Office 행/좀비 프로세스 방어 부재 | `extractors.py` | 배치 안정성 (DRM 모달 대비) |

---

## 1. 🔴 파일마다 Office 앱 생성/종료 (최대 병목)

`WordExtractor.extract()` 등 세 추출기 모두 `extract()` 안에서 `self._factory()`(→ `DispatchEx`,
새 Office 프로세스 기동)와 `app.Quit()`을 수행한다. Word/Excel 프로세스 기동은 통상 1~5초로,
소형 문서 수백 건 배치에서는 기동/종료 비용이 실제 추출 시간을 압도한다.

**개선**: 추출기를 컨텍스트 매니저로 바꿔 배치 전체에서 확장자 타입별 앱 1개를 재사용.

```python
class WordExtractor:
    def __enter__(self):
        self._app = self._factory()
        self._app.Visible = False
        self._app.DisplayAlerts = False
        return self

    def extract(self, path):          # 앱 재사용, 문서만 열고 닫음
        doc = self._app.Documents.Open(path, ReadOnly=True, ...)
        try:
            return str(doc.Content.Text)
        finally:
            doc.Close(False)

    def __exit__(self, *exc):
        self._app.Quit()
```

`worker.ingest_target()`에서 파일을 확장자 타입별로 그룹핑한 뒤 타입별 앱 1개로 순회한다.
Office 메모리 누수 대비로 N건(예: 100건)마다 앱을 재기동하는 것을 권장.

## 2. 🔴 PDF 추출기 부재

목표에 PDF가 명시돼 있으나 `EXTRACTORS`에 `.pdf`가 없어 현재 PDF는 인제스트 불가
(`collect_paths`가 아예 수집 대상에서 제외).

**개선 옵션** (DRM 투명 복호화 유지 순):
- **Word COM으로 PDF 열기**: Word 2013+는 `Documents.Open(pdf, ConfirmConversions=False)`로
  PDF를 리플로우 변환해 연다. 추가 설치 없이 기존 `WordExtractor`에 `.pdf` 매핑만 추가하면 됨.
  단, DRM 에이전트가 Word 경유 PDF 열기에도 복호화를 적용하는지 **DRM 벤더 확인 필요**.
- **Acrobat COM** (`AcroExch.PDDoc` + JSObject): Acrobat Pro 라이선스 필요하지만 DRM이
  Acrobat에 바인딩된 경우 가장 확실. 페이지 단위 텍스트 추출은 느리므로 배치 시 앱 재사용 필수.
- DRM이 걸리지 않은 일반 PDF가 섞여 있으면 백엔드에서 `pypdf` 등으로 직접 파싱하는 경로를
  병행(워커 왕복 불필요, 훨씬 빠름).

## 3. 🔴 문서 1건당 임베딩 1회 — 배치 인제스트 부재

`ingest_text()`가 문서마다 `_compute_embedding()`을 호출한다. OpenRouter 백엔드면 문서당
HTTP 왕복 1회(타임아웃 60s), fastembed 로컬이면 배치 크기 1의 ONNX 추론이다.
`embeddings._embed_openrouter`는 이미 배치 64를 지원하는데 인제스트 경로가 활용하지 못한다.
워커도 파일당 POST 1회라 "추출 → 임베딩 → 커밋"이 전부 직렬 왕복.

**개선**: `/collection/ingest/batch` 추가 — 워커가 문서 K건(예: 16~32건)을 모아 전송하면
백엔드가 `embeddings.embed(texts)` 1회로 일괄 임베딩 후 단일 트랜잭션으로 INSERT+FTS 색인.
FTS/INSERT 트랜잭션 오버헤드도 함께 상각된다.

**대안/보완**: 임베딩을 인제스트 응답 경로에서 떼어내 지연 계산(수집 시 NULL → 주기적으로
`rebuild_embeddings()` 유사 백필). 이미 폴백 구조(BM25)가 있어 안전하게 적용 가능.

## 4. 🟡 워커 HTTP 커넥션 미재사용

`_httpx_poster`가 파일마다 `httpx.post`(신규 클라이언트 → TCP+TLS 핸드셰이크)를 수행.
백엔드 쪽은 최근 PR(#58)에서 커넥션 재사용을 적용했는데 워커에는 같은 패턴이 빠져 있다.

**개선**: `httpx.Client`를 배치 수명 동안 재사용(keep-alive). 3번의 배치 전송과 함께 적용하면 자연 해소.

## 5. 🟡 추출·전송 완전 직렬 + 타입별 병렬 여지

`ingest_target()`은 파일 1건에 대해 추출(COM, CPU/디스크 바운드) 완료 후 전송(네트워크 바운드)을
기다리고 다음 파일로 넘어간다.

**개선**:
- **파이프라인화**: 추출 스레드와 전송 스레드를 큐로 연결해 전송 지연을 추출과 겹치기.
- **타입별 병렬**: Word/Excel/PowerPoint는 별개 프로세스이므로 타입별 워커 스레드 1개씩
  (스레드마다 `pythoncom.CoInitialize()` 필수, STA 규칙 준수) 병렬 실행 가능.
  같은 타입 다중 인스턴스 병렬은 DRM 에이전트와의 상호작용 검증 후에만 고려.

## 6. 🟡 멱등성 부재 — 재실행 시 전량 중복

`ingest_text()`는 항상 새 `uuid` 문서를 생성한다. 폴더 배치를 재실행하면 전 문서가 중복 등록되어
(a) 재실행 시간 낭비, (b) FTS·임베딩 테이블 비대 → 검색 성능 저하, (c) RAG 결과 중복.

**개선**: 워커에서 파일 `(경로, size, mtime)` 또는 본문 해시 매니페스트로 기수집 파일 skip.
백엔드에도 본문 SHA-256 컬럼을 두고 동일 해시 도착 시 기존 문서 반환(업서트)하면 이중 방어.

## 7. 🟢 임베딩 입력 길이 무제한

`_embed_doc_text()`가 본문 전체를 임베딩에 넘긴다. MiniLM 계열은 어차피 512토큰에서 절단되고,
OpenRouter(bge-m3)는 긴 입력만큼 비용·지연이 커진다.

**개선**: 임베딩 입력을 앞 4~8K자로 절단(검색 품질 영향 미미, 비용·지연 절감).
장문 검색 품질까지 노리면 청크 단위 임베딩이 다음 단계이나 스키마 변경이 필요한 별도 과제.

## 8. 🟢 Office 행(hang)·좀비 프로세스 방어

DRM 클라이언트는 권한 없음/만료 문서에서 모달 대화상자를 띄울 수 있고, COM 호출은 모달에서
무한 대기한다. 현재 `finally: app.Quit()`은 행 상태에선 도달하지 못하며, 실패 누적 시
WINWORD.EXE 좀비가 쌓여 배치 전체가 느려진다.

**개선**: 파일당 타임아웃 워치독(예: 120s) → 초과 시 해당 Office 프로세스 강제 종료 후 앱 재기동,
해당 파일은 `[fail]` 기록. `DispatchEx` PID 추적(`app.Hwnd` → PID)으로 정확히 그 프로세스만 종료.
PowerPoint에도 `DisplayAlerts = ppAlertsNone` 설정 추가.

---

## 잘 되어 있는 부분 (유지)

- Excel `UsedRange.Value` 일괄 읽기(셀 단위 COM 왕복 회피), Word `Content.Text` 단일 호출.
- `DispatchEx`로 사용자 Office 세션과 분리.
- 임베딩 계산을 쓰기 트랜잭션 밖에서 수행(잠금 시간 최소화), WAL + 스레드별 커넥션 재사용.
- 한 파일 실패가 배치를 중단하지 않는 구조, 테스트용 팩토리 주입 설계.

## 이미지 처리 설계 (2026-07-07 구현)

문서 속 이미지(스캔 페이지, 캡처된 표/차트)는 텍스트 추출만으로는 색인에서 유실된다.
로컬 OCR(RapidOCR/onnxruntime, 외부 API 없음 — 온프렘 요건)로 회수한다. extras `ocr`.

**구현된 것**
- 스캔 PDF: 텍스트 레이어 없는 페이지를 200dpi 렌더링 → OCR (`pdftext._ocr_page`,
  문서당 20페이지 상한). OCR 비활성이면 기존대로 None → COM 폴백.
- OOXML 내장 이미지: zip `media/*` 를 OCR 해 `[이미지 텍스트]` 블록으로 본문 뒤에
  결합 (`officetext._with_image_text`, 문서당 10개·10KiB~8MiB 필터 — 로고/아이콘 제외).
- 스위치: `MI_OCR=0` 으로 끔. 비용: 페이지/이미지당 수백 ms(CPU).

**한계와 후속 옵션**
1. **한국어**: RapidOCR 기본 인식 모델은 중·영문. 한국어 스캔본 품질이 필요하면
   PP-OCR korean 인식 모델(.onnx)을 받아 `MI_OCR_REC_MODEL` 로 지정(워커 배포에 포함).
2. **차트·다이어그램**: OCR 은 글자만 읽는다. 차트 의미 해석이 필요하면 OpenRouter
   멀티모달 모델로 이미지 캡셔닝하는 후속 단계(비용·기밀성 검토 필요 — 이미지가
   외부 API 로 나가므로 DRM 문서에는 부적합).
3. **DRM 문서**: COM 폴백 경로는 텍스트만 추출한다(이미지 미회수). 필요 시 Word COM
   `SaveAs2`(filtered HTML)로 이미지를 내보내 OCR 하는 확장 여지 — DRM 정책상
   내보내기가 허용되는지 벤더 확인 선행.
4. **텍스트 있는 페이지의 삽입 이미지(PDF)**: 노이즈·비용 때문에 미적용. 필요 시
   페이지 내 이미지 블록만 선별 OCR 하는 옵션 추가 가능.

## 권장 적용 순서

1. **#1 앱 재사용 + #8 워치독** — 워커만 수정, 효과 최대.
2. **#2 PDF 지원** — Word COM 경유부터 검증(추가 의존성 0), DRM 벤더 확인 병행.
3. **#3 배치 ingest + #4 커넥션 재사용** — 워커·백엔드 각 소폭 수정.
4. **#6 멱등성(해시 skip)** — 운영 재실행 시나리오에서 즉효.
5. #5 파이프라인화, #7 임베딩 절단 — 위 적용 후 남는 병목 확인 뒤 진행.
