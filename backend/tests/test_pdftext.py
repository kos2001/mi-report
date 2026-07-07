"""PyMuPDF 기반 PDF 텍스트 추출 테스트.

pymupdf 미설치 환경(선택 의존성)에서는 실추출 테스트를 건너뛴다 —
호출부 폴백(None 반환) 계약은 설치 여부와 무관하게 검증한다.
"""

from __future__ import annotations

import pytest

from app import pdftext

needs_pymupdf = pytest.mark.skipif(not pdftext.available(), reason="pymupdf 미설치")


def _make_pdf(tmp_path, text: str, *, password: str | None = None):
    mod = pdftext._pymupdf()
    doc = mod.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    path = tmp_path / "sample.pdf"
    if password:
        doc.save(str(path), encryption=mod.PDF_ENCRYPT_AES_256,
                 user_pw=password, owner_pw=password)
    else:
        doc.save(str(path))
    doc.close()
    return path


@needs_pymupdf
def test_extract_path_and_bytes(tmp_path):
    path = _make_pdf(tmp_path, "HBM market outlook 2026")
    text = pdftext.extract_path(str(path))
    assert text and "HBM market outlook" in text
    assert pdftext.extract_bytes(path.read_bytes()) == text


@needs_pymupdf
def test_encrypted_pdf_falls_back(tmp_path):
    """암호화 PDF 는 열지 않고 None — 정식 앱(DRM 에이전트) 경로로 폴백시킨다."""
    path = _make_pdf(tmp_path, "secret", password="pw")
    assert pdftext.extract_path(str(path)) is None
    assert pdftext.extract_bytes(path.read_bytes()) is None


@needs_pymupdf
def test_textless_pdf_falls_back(tmp_path):
    """텍스트 레이어 없는 PDF(스캔본 모사)는 None — 호출부 폴백."""
    mod = pdftext._pymupdf()
    doc = mod.open()
    doc.new_page()  # 빈 페이지만
    path = tmp_path / "blank.pdf"
    doc.save(str(path))
    doc.close()
    assert pdftext.extract_path(str(path)) is None


def test_broken_input_returns_none(tmp_path):
    """깨진 파일/바이트는 예외 없이 None(폴백 계약) — 설치 여부와 무관."""
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf at all")
    assert pdftext.extract_path(str(p)) is None
    assert pdftext.extract_bytes(b"not a pdf at all") is None
    assert pdftext.extract_bytes(b"") is None


@needs_pymupdf
def test_max_pages_limits_extraction(tmp_path):
    mod = pdftext._pymupdf()
    doc = mod.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"page-{i}")
    path = tmp_path / "multi.pdf"
    doc.save(str(path))
    doc.close()
    text = pdftext.extract_path(str(path), max_pages=2)
    assert "page-0" in text and "page-1" in text and "page-2" not in text
