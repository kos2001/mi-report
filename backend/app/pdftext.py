"""PDF 텍스트 추출 — PyMuPDF 우선, 호출부별 폴백.

PyMuPDF(pymupdf)는 파이썬 PDF 파서 중 추출 속도가 가장 빠르고(순수 파이썬
pypdf/pdfminer 대비 수십 배) 한글 텍스트 품질도 좋다. 선택 의존성(extras: pdf)으로
두고, 미설치·암호화·텍스트 없음이면 None 을 돌려 호출부가 폴백한다
(COM 워커 → Word 리플로우 변환, 한경 수집 → pypdf).

라이선스 주의: PyMuPDF 는 AGPL-3.0(상용 라이선스 별매). 사내 내부 도구로 쓰는 것은
일반적으로 문제없으나 외부 배포 시 검토가 필요하다. 허용적 라이선스가 필요하면
pypdfium2(Apache/BSD)로 교체할 수 있도록 이 모듈 뒤에 격리해 둔다.
"""

from __future__ import annotations

from typing import Any


def _pymupdf() -> Any | None:
    """pymupdf 모듈(미설치면 None). 신(pymupdf)·구(fitz) 임포트명 모두 지원."""
    try:
        import pymupdf  # noqa: PLC0415

        return pymupdf
    except ImportError:
        try:
            import fitz  # noqa: PLC0415  # 구버전 배포 별칭

            return fitz
        except ImportError:
            return None


def available() -> bool:
    """PyMuPDF 사용 가능 여부(설치: pip install .[pdf])."""
    return _pymupdf() is not None


def _doc_text(doc: Any, max_pages: int | None) -> str:
    n = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    parts = []
    for i in range(n):
        t = doc[i].get_text().strip()
        if t:
            parts.append(t)
    return "\n".join(parts)


def extract_path(path: str, *, max_pages: int | None = None) -> str | None:
    """PDF 파일에서 텍스트 추출. 미설치/암호화/텍스트 없음/실패 → None(호출부 폴백).

    암호화(needs_pass) PDF 는 여기서 열지 않는다 — DRM/권한 문서는 인가된
    정식 응용프로그램(COM 워커의 Word 경로)으로 여는 것이 원칙.
    """
    mod = _pymupdf()
    if mod is None:
        return None
    try:
        with mod.open(path) as doc:
            if doc.needs_pass:
                return None
            text = _doc_text(doc, max_pages)
        return text or None  # 텍스트 레이어 없음(스캔본 등) → 폴백
    except Exception:
        return None


def extract_bytes(content: bytes, *, max_pages: int | None = None) -> str | None:
    """PDF 바이트에서 텍스트 추출. 실패 시 None(호출부 폴백)."""
    mod = _pymupdf()
    if mod is None or not content:
        return None
    try:
        with mod.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                return None
            text = _doc_text(doc, max_pages)
        return text or None
    except Exception:
        return None
