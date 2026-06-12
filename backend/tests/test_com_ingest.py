"""COM 인제스트 추출/워커 테스트.

실제 COM/Windows 없이, COM 인터페이스를 흉내내는 가짜 객체를 주입해
추출 오케스트레이션과 워커 페이로드/등록 흐름을 검증한다.
"""

from __future__ import annotations

import sys

import pytest

from tools.com_ingest import extractors, worker


# ── 가짜 COM 앱들 (win32com 인터페이스 모사) ──────────────────────────
class _FakeRange:
    def __init__(self, text):
        self.Text = text


class _FakeDoc:
    def __init__(self, text):
        self.Content = _FakeRange(text)
        self.closed = False

    def Close(self, save):  # noqa: N802
        self.closed = True


class FakeWordApp:
    def __init__(self, text="워드 본문 (DRM 해제됨)"):
        self._text = text
        self.Visible = True
        self.DisplayAlerts = True
        self.quit = False

    class _Docs:
        def __init__(self, outer):
            self.outer = outer

        def Open(self, path, **kw):  # noqa: N802
            self.outer.last_doc = _FakeDoc(self.outer._text)
            return self.outer.last_doc

    @property
    def Documents(self):  # noqa: N802
        return FakeWordApp._Docs(self)

    def Quit(self):  # noqa: N802
        self.quit = True


class _FakeSheet:
    def __init__(self, name, values):
        self.Name = name
        self.UsedRange = type("UR", (), {"Value": values})()


class FakeExcelApp:
    def __init__(self):
        self.Visible = True
        self.DisplayAlerts = True

    class _WB:
        Worksheets = [
            _FakeSheet("Sheet1", (("매출", "QoQ"), ("100", "3.2"))),
        ]

        def Close(self, save):  # noqa: N802
            self.closed = True

    def __init_workbooks(self):
        pass

    @property
    def Workbooks(self):  # noqa: N802
        app = self

        class _Books:
            def Open(self, path, **kw):  # noqa: N802
                app._wb = FakeExcelApp._WB()
                return app._wb

        return _Books()

    def Quit(self):  # noqa: N802
        self.quit = True


class _FakeTextRange:
    def __init__(self, text):
        self.Text = text


class _FakeTextFrame:
    def __init__(self, text):
        self.HasText = bool(text)
        self.TextRange = _FakeTextRange(text)


class _FakeShape:
    def __init__(self, text):
        self.HasTextFrame = True
        self.TextFrame = _FakeTextFrame(text)


class _FakeSlide:
    def __init__(self, texts):
        self.Shapes = [_FakeShape(t) for t in texts]


class FakePptApp:
    def __init__(self):
        self.quit = False

    class _Pres:
        Slides = [_FakeSlide(["제목", "본문 줄"])]

        def Close(self):  # noqa: N802
            self.closed = True

    @property
    def Presentations(self):  # noqa: N802
        app = self

        class _Opener:
            def Open(self, path, **kw):  # noqa: N802
                app._pres = FakePptApp._Pres()
                return app._pres

        return _Opener()

    def Quit(self):  # noqa: N802
        self.quit = True


# ── 추출기 테스트 ─────────────────────────────────────────────────────
def test_word_extraction():
    factories = {"Word.Application": lambda: FakeWordApp("HBM 분석 본문")}
    text = extractors.extract_text("report.docx", factories)
    assert "HBM 분석 본문" in text


def test_excel_extraction_flattens_cells():
    factories = {"Excel.Application": FakeExcelApp}
    text = extractors.extract_text("financials.xlsx", factories)
    assert "Sheet1" in text
    assert "매출\tQoQ" in text
    assert "100\t3.2" in text


def test_ppt_extraction_joins_shapes():
    factories = {"PowerPoint.Application": FakePptApp}
    text = extractors.extract_text("deck.pptx", factories)
    assert "slide 1" in text
    assert "제목" in text and "본문 줄" in text


def test_unsupported_extension_raises():
    with pytest.raises(ValueError):
        extractors.extract_text("scan.pdf")


def test_non_windows_factory_raises(monkeypatch):
    """Windows 가 아니면 실제 COM 팩토리는 명확한 에러를 낸다."""
    monkeypatch.setattr(sys, "platform", "darwin")
    factory = extractors.get_com_factory("Word.Application")
    with pytest.raises(RuntimeError, match="Windows"):
        factory()


# ── 워커 테스트 ───────────────────────────────────────────────────────
def test_build_payload():
    p = worker.build_payload("/x/분기분석.docx", "본문", topic="HBM")
    assert p == {
        "title": "분기분석",
        "text": "본문",
        "topic": "HBM",
        "original_filename": "분기분석.docx",
    }


def test_ingest_file_extracts_and_posts():
    posted = {}

    def fake_post(url, payload):
        posted["url"] = url
        posted["payload"] = payload
        return {"id": "doc1", **payload}

    factories = {"Word.Application": lambda: FakeWordApp("DRM 해제 본문")}
    result = worker.ingest_file(
        "보고서.docx", "http://mi:8000", topic="HBM",
        poster=fake_post, factories=factories,
    )
    assert posted["url"] == "http://mi:8000"
    assert posted["payload"]["title"] == "보고서"
    assert "DRM 해제 본문" in posted["payload"]["text"]
    assert result["id"] == "doc1"
