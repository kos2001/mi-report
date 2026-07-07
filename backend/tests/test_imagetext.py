"""문서 이미지 OCR(imagetext) + 스캔 PDF/내장 이미지 경로 테스트.

rapidocr 미설치 환경에서는 실 OCR 테스트를 건너뛴다. 파이프라인 연결(스캔 페이지
감지, 이미지 블록 결합)은 가짜 OCR 주입으로 설치 여부와 무관하게 검증한다.
"""

from __future__ import annotations

import pytest

from app import imagetext, officetext, pdftext

needs_pymupdf = pytest.mark.skipif(not pdftext.available(), reason="pymupdf 미설치")
needs_ocr = pytest.mark.skipif(not imagetext.available(), reason="rapidocr 미설치")


def _text_png(lines: int = 12) -> bytes:
    """텍스트가 그려진 PNG(≥10KiB — officetext 크기 필터 통과용)."""
    mod = pdftext._pymupdf()
    doc = mod.open()
    page = doc.new_page()
    for i in range(lines):
        page.insert_text((50, 60 + i * 30), f"SUPPLY CHAIN RISK LINE {i}", fontsize=16)
    png = page.get_pixmap(dpi=200).tobytes("png")
    doc.close()
    return png


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("MI_OCR", "0")
    assert imagetext.enabled() is False
    assert imagetext.ocr_bytes(b"png-bytes") is None


# ── VLM 캡셔닝 ────────────────────────────────────────────────────────
def test_vlm_enabled_requires_optin_and_key(monkeypatch):
    monkeypatch.delenv("MI_VLM", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert imagetext.vlm_enabled() is False  # opt-in 없음
    monkeypatch.setenv("MI_VLM", "1")
    assert imagetext.vlm_enabled() is True
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert imagetext.vlm_enabled() is False  # 키 없음


def test_image_text_rich_ocr_skips_vlm(monkeypatch):
    """OCR 로 글자가 충분하면 VLM 을 호출하지 않는다(비용 절약)."""
    monkeypatch.setattr(imagetext, "ocr_bytes", lambda d: "글자 " * 30)

    def no_vlm(d):
        raise AssertionError("OCR 충분 시 VLM 호출 금지")

    monkeypatch.setattr(imagetext, "describe_bytes", no_vlm)
    assert "글자" in imagetext.image_text(b"img")


def test_image_text_sparse_ocr_uses_vlm(monkeypatch):
    """글자가 빈약한 이미지(차트)는 VLM 캡션으로 보완·결합한다."""
    monkeypatch.setattr(imagetext, "ocr_bytes", lambda d: "45%")
    monkeypatch.setattr(imagetext, "describe_bytes",
                        lambda d: "매출 성장률 차트: 45% 상승 추세")
    text = imagetext.image_text(b"img")
    assert "45%" in text and "상승 추세" in text

    monkeypatch.setattr(imagetext, "ocr_bytes", lambda d: None)  # OCR 전무 → 캡션만
    assert imagetext.image_text(b"img") == "매출 성장률 차트: 45% 상승 추세"


def test_describe_bytes_posts_data_url(monkeypatch):
    """VLM 요청 형식: data URL 이미지 + 프롬프트, 응답 content 를 돌려준다."""
    monkeypatch.setenv("MI_VLM", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    sent = {}

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "차트 설명"}}]}

    class _FakeClient:
        def post(self, url, headers=None, json=None):
            sent["url"], sent["json"] = url, json
            return _FakeResp()

    monkeypatch.setattr(imagetext, "_http", lambda: _FakeClient())
    assert imagetext.describe_bytes(b"\x89PNG fake") == "차트 설명"
    assert sent["url"].endswith("/chat/completions")
    assert sent["json"]["model"]  # 모델 지정됨(기본 minimax-m3 계열)
    parts = sent["json"]["messages"][0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_mime_detection():
    assert imagetext._mime(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert imagetext._mime(b"\x89PNG\r\n") == "image/png"
    assert imagetext._mime(b"GIF89a") == "image/gif"


def test_ocr_bytes_bad_input_returns_none():
    assert imagetext.ocr_bytes(b"") is None


@needs_pymupdf
@needs_ocr
def test_real_ocr_reads_rendered_text():
    text = imagetext.ocr_bytes(_text_png())
    assert text and "SUPPLY CHAIN RISK" in text


@needs_pymupdf
@needs_ocr
def test_scanned_pdf_extracted_via_ocr(tmp_path):
    """텍스트 레이어 없는 스캔 PDF 도 extract_path 가 OCR 로 본문을 회수한다."""
    mod = pdftext._pymupdf()
    doc = mod.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=_text_png())  # 이미지만 있는 페이지(스캔본)
    path = tmp_path / "scan.pdf"
    doc.save(str(path))
    doc.close()

    text = pdftext.extract_path(str(path))
    assert text and "SUPPLY CHAIN RISK" in text


@needs_pymupdf
def test_scanned_pdf_ocr_pipeline_with_fake_engine(tmp_path, monkeypatch):
    """스캔 페이지 감지 → OCR 결합 배선을 가짜 OCR 로 검증(설치 무관)."""
    mod = pdftext._pymupdf()
    doc = mod.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=_text_png(2))
    path = tmp_path / "scan.pdf"
    doc.save(str(path))
    doc.close()

    monkeypatch.setattr(imagetext, "available", lambda: True)
    monkeypatch.setattr(imagetext, "ocr_bytes", lambda data: "가짜 OCR 본문")
    assert pdftext.extract_path(str(path)) == "가짜 OCR 본문"

    # OCR 비활성이면 기존 계약 유지: 텍스트 없음 → None(COM 폴백)
    monkeypatch.setattr(imagetext, "available", lambda: False)
    assert pdftext.extract_path(str(path)) is None


@needs_pymupdf
def test_docx_embedded_image_text_appended(tmp_path, monkeypatch):
    """docx 내장 이미지의 OCR 텍스트가 '[이미지 텍스트]' 블록으로 붙는다."""
    docx = pytest.importorskip("docx")
    import io

    png = _text_png()
    assert len(png) >= 10 * 1024  # 크기 필터(_IMG_MIN_BYTES) 통과 전제
    d = docx.Document()
    d.add_paragraph("본문 문단")
    d.add_picture(io.BytesIO(png))
    path = tmp_path / "img.docx"
    d.save(str(path))

    monkeypatch.setattr(imagetext, "available", lambda: True)
    monkeypatch.setattr(imagetext, "ocr_bytes", lambda data: "이미지 속 표 내용")
    text = officetext.extract_docx(str(path))
    assert "본문 문단" in text
    assert "[이미지 텍스트]" in text and "이미지 속 표 내용" in text

    # OCR 비활성이면 본문만(기존 동작)
    monkeypatch.setattr(imagetext, "available", lambda: False)
    text = officetext.extract_docx(str(path))
    assert "본문 문단" in text and "[이미지 텍스트]" not in text