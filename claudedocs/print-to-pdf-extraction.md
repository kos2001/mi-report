# DRM PDF → 인쇄(Print to PDF) → PyMuPDF 텍스트 추출

Word COM 리플로우가 DRM PDF를 잘 못 파싱하는 문제의 우회로. **인가된 무료 Reader로
"인쇄"해 비보호 PDF를 만든 뒤, 좋은 파서(PyMuPDF)로 추출**한다. Word 리플로우의
표·순서 깨짐을 피한다.

전제: 본인이 **열람 권한**을 가진 문서 + 나스카 정책이 **인쇄를 허용**할 것.
인쇄가 정책상 금지면 이 방법은 불가(= 우회 아님) → 대신 Samsung SDS 반출 승인.

## 1단계 — Reader에서 Print to PDF (비보호 PDF 생성)

1. DRM PDF를 **Adobe Reader**(인가 앱)로 연다 → 정상 표시되면 복호화 OK.
2. 파일 → 인쇄 → 프린터에서 **"Microsoft Print to PDF"** 선택 → 인쇄.
3. 저장 대화상자에서 출력 폴더/파일명 지정(예: `C:\printed\a.pdf`).

주의:
- **일괄(배치) 무음 인쇄는 신뢰성이 낮다** — Microsoft Print to PDF는 파일명 저장
  대화상자를 띄운다. 소량이면 수동, **대량이면 Samsung SDS 반출 승인**이 낫다.
- 인쇄본은 보통 **선택 가능한 텍스트를 보존**한다(원본이 텍스트일 때) → 2단계에서
  PyMuPDF가 직접 추출. 일부는 **이미지로 래스터화**될 수 있다 → OCR 필요(아래).
- DRM 인쇄 워터마크가 텍스트에 섞여 들어올 수 있다(검토 시 감안).

## 2단계 — 워커로 텍스트 추출 (백엔드·Office 불필요)

비보호 PDF는 PyMuPDF가 로컬 고속 경로(route=local)로 처리한다. Office/Word가 필요
없고, DRM PC가 아닌 곳에서 돌려도 된다.

```bat
python -m tools.com_ingest.worker "C:\printed" --out "C:\text"
:: [out] C:\printed\a.pdf → C:\text\a.txt | 경로=local | 4210자
```

- `경로=local` + 정상 텍스트면 성공. Word 리플로우보다 표·순서가 온전하다.
- 백엔드에 바로 적재하려면 `--out` 대신 `--backend http://<host>:8000` 사용.

## 3단계(조건부) — 인쇄본이 이미지면 OCR 켜기

인쇄본이 래스터화돼 `경로=local`인데 글자 수가 0/빈약하면 텍스트 레이어가 없는 것.
OCR을 켜면 PyMuPDF가 페이지를 렌더해 회수한다(pdftext → imagetext).

```bat
pip install .[pdf,ocr]
:: 한국어 인식 품질이 필요하면 PP-OCR korean 모델(.onnx) 경로 지정:
set MI_OCR_REC_MODEL=C:\models\korean_rec.onnx
```

OCR은 설치만 하면 기본 켜짐(`MI_OCR=1`). 끄기: `set MI_OCR=0`.

## 자가 진단 (`[warn]`) — 라이브 확인이 어려운 환경용

워커는 추출 결과가 의심스러우면 파일별로 `[warn]` 을 함께 출력한다(등록은 막지 않음).
DRM PC 에서 직접 눈으로 확인하기 어려울 때, 로그의 `[warn]` 만 훑어 문제 파일을 걸러낸다:

| 경고 | 뜻 |
|---|---|
| `본문 과소(N자)` | 빈 문서 / 추출 실패 / **미복호화(미인가 앱)** 의심 |
| `깨진 문자 U+FFFD 과다` | 인코딩·폰트 매핑 실패(한글 □□□) |
| `제어문자 과다` | **이진/암호문을 그대로 추출** — 복호화가 안 됨(인가 아님) |

→ `[warn]` 이 대량이면 그 경로(예: Word)가 인가 앱이 아니거나 인쇄본이 이미지인 것.
정상이면 경고 없이 `[ok]`/`[out]` 만 나온다.

## 품질을 더 올리려면 (선택)

표가 많은 IR/실적 PDF는 평문보다 구조 보존이 중요하다. 비보호 PDF가 확보된 뒤에는
`pdftext.py`를 **pymupdf4llm**(마크다운·표 보존) 또는 **Docling**(MIT, 표 강함)으로
올릴 수 있다. 별도 작업으로 진행.

## 정리 흐름

```
DRM PDF ──(Reader 인쇄, 인쇄 허용 시)──▶ 비보호 PDF (C:\printed)
        │
        ▼
worker --out ──(PyMuPDF, 필요시 OCR)──▶ C:\text\*.txt
```

소량·인쇄 허용 → 이 경로. 대량 or 인쇄 금지 → Samsung SDS 반출/복호화 승인.
