# 오픈소스로 풀 수 있는 부분 — 문서 추출/OCR (NASCA 환경)

조사일 2026-07-08. 결론: **NASCA(=Samsung SDS DRM) 자체를 푸는 정식 오픈소스는 없다**
(정책서버 키 + 프로세스 인젝션 기반 — 우회는 대상 아님). 그러나 **정식 복호화
이후의 "문서→텍스트/구조화" 단계**는 오픈소스 생태계가 강력하며, 이 저장소의
기존 스택(PyMuPDF/RapidOCR/python-docx…)을 그대로 강화할 수 있다.

## 두 갈래로 나눠서

### ① NASCA 잠금 해제 자체 → 오픈소스 해당 없음
NASCA(Samsung SDS)는 에이전트가 인가 프로세스에만 투명 복호화하고 키는 정책서버에
있다. 이를 제거하는 정식 오픈소스는 존재하지 않으며, 무력화(메모리 덤프/후킹/키
추출)는 다루지 않는다. "풀린 파일"의 정식 경로는 **Samsung SDS 반출/복호화 승인**
(사내 보안팀·SDS 콘솔)뿐이다. 인가 앱 자동화(현재 COM 워커)는 pywin32(이미 사용)
기반 자체 구현이 사실상 유일한 오픈소스적 접근.

### ② 복호화 이후 문서 추출 → 오픈소스 활용처(핵심)

MI 리포트는 반도체 IR/실적 PDF(표·차트 많음)와 한국어 문서가 핵심이므로 표·레이아웃·
한국어 OCR 품질이 관건. 기존 `pdftext.py`(PyMuPDF 평문)·Word 리플로우보다 나은 선택지:

| 프로젝트 | 강점 | 라이선스 | 이 저장소 적용 |
|---|---|---|---|
| **Docling** (IBM) | 표·레이아웃 우수, PDF/DOCX/PPTX/XLSX/HTML, LangChain/LlamaIndex 연동 | MIT(허용적) | RAG 파이프라인에 가장 라이선스-클린. 유력 |
| **MinerU** (OpenDataLab) | **CJK(한국어)·복잡 레이아웃 최강**, PaddleOCR 내장 | 카피레프트(AGPL/자체 라이선스 — 현행 확인) | 한국어 IR PDF 품질 최상. 사내용이면 OK |
| **PyMuPDF4LLM** | PyMuPDF 기반 Markdown 출력(LLM용) | AGPL-3.0 | 이미 PyMuPDF 사용 → 최소 변경 업그레이드 |
| **Marker** | 빠른 PDF→MD, 레이아웃 인식 | GPL-3.0(상용 별도) | 경량 대안 |
| **Apache Tika** | 75+ 포맷 파서 + Tesseract OCR, REST 서비스 | Apache-2.0 | 포맷별 추출기 통합 대안 |
| **Unstructured** | RAG 지향 partition/chunk | Apache-2.0 | 인입 청킹 단계 |

**OCR(스캔 PDF·한국어)** — 현재 RapidOCR(ONNX PaddleOCR) 사용 중:
| 프로젝트 | 비고 | 라이선스 |
|---|---|---|
| **PaddleOCR (PP-OCRv5 / PaddleOCR-VL)** | 한국어 강함, OmniDocBench 96%+ | Apache-2.0 |
| **Surya** | 90+ 언어, 최신 | 매출 임계 기반 무료(확인) |
| **docTR** | 검출+인식 파이프라인 | Apache-2.0 |
| **OCRmyPDF** | 스캔 PDF 에 텍스트 레이어 추가(파싱 전 정규화) | MPL-2.0 |

## 라이선스 주의 (기존 [[com-ingest-decisions]] 결정과 일관)
사내 내부 도구는 AGPL/GPL 사용이 일반적으로 무방하나 **외부 배포 시** 검토 필요.
라이선스-클린 우선순위: Apache/MIT(Docling·Tika·Unstructured·PaddleOCR·docTR) >
카피레프트(MinerU·PyMuPDF4LLM·Marker). PyMuPDF 는 이미 AGPL 로 격리해 둔 상태.

## 권장 (측정 후 결정)
1. **표 품질이 핵심** → 비보호 PDF 확보(SDS 승인) 후 **Docling**(라이선스 클린) 또는
   **MinerU**(한국어·표 최강)로 `pdftext.py` 대체/보강. 소규모 벤치로 둘 비교.
2. **최소 변경** → `pdftext.py` 를 **PyMuPDF4LLM** 마크다운 출력으로 업그레이드.
3. **스캔 한국어** → RapidOCR → **PaddleOCR PP-OCRv5** 또는 **OCRmyPDF** 전처리.

## 출처
- PDF→Markdown 비교(Docling/Marker/MinerU): themenonlab.blog, jimmysong.io, marktechpost.com
- 라이선스: PyMuPDF4LLM/MinerU AGPL, Marker GPL-3.0 (검색 확인)
- OCR: unstract.com, PaddleOCR GitHub, tasarim.ai(Surya)
- NASCA=Samsung SDS: software.informer, Mozilla bug 1733532(NtMapViewOfSection 인젝션)
