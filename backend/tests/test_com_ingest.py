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


def test_pdf_fast_path_skips_word(monkeypatch):
    """일반 PDF 는 PyMuPDF 고속 경로로 추출한다 — Word 앱을 아예 띄우지 않는다."""
    from app import pdftext

    monkeypatch.setattr(pdftext, "extract_path", lambda p, **k: "PyMuPDF 본문")

    def must_not_launch():
        raise AssertionError("고속 경로에서 Word 를 띄우면 안 된다")

    text = extractors.extract_text("plain.pdf", {"Word.Application": must_not_launch})
    assert text == "PyMuPDF 본문"


def test_pdf_falls_back_to_word_extractor(monkeypatch):
    """PyMuPDF 가 못 읽는 PDF(DRM/암호화/스캔본)는 Word 리플로우 폴백으로 추출한다."""
    from app import pdftext

    monkeypatch.setattr(pdftext, "extract_path", lambda p, **k: None)
    factories = {"Word.Application": lambda: FakeWordApp("PDF 본문")}
    text = extractors.extract_text("scan.pdf", factories)
    assert "PDF 본문" in text


def test_unsupported_extension_raises():
    with pytest.raises(ValueError):
        extractors.extract_text("메모.hwp")


def test_extractor_reuses_app_across_files():
    """with 블록 동안 앱 1개를 재사용하고, 종료 시에만 Quit 한다."""
    created: list[FakeWordApp] = []

    def factory():
        app = FakeWordApp("본문")
        created.append(app)
        return app

    with extractors.WordExtractor(factory) as ex:
        ex.extract("a.docx")
        ex.extract("b.docx")
        assert len(created) == 1          # 파일마다 새 앱을 띄우지 않는다
        assert created[0].quit is False   # 재사용 중에는 종료하지 않는다
    assert created[0].quit is True        # 블록 종료 시 Quit

    # restart: 앱 재기동(메모리 누수 예방 주기 재시작)
    with extractors.WordExtractor(factory) as ex:
        ex.extract("c.docx")
        ex.restart()
        ex.extract("d.docx")
    assert len(created) == 3 and all(a.quit for a in created)


def test_one_shot_extract_quits_app():
    """extract_text(일회성)는 추출 후 앱을 종료한다(기존 동작 유지)."""
    app = FakeWordApp("한 건")
    extractors.extract_text("one.docx", {"Word.Application": lambda: app})
    assert app.quit is True


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


# ── 러너(전용 스레드 + 타임아웃) 테스트 ───────────────────────────────
class SlowOpenWordApp(FakeWordApp):
    """path 에 'hang' 이 들어가면 Open 이 오래 걸리는 가짜 앱(DRM 모달 모사)."""

    class _Docs(FakeWordApp._Docs):
        def Open(self, path, **kw):  # noqa: N802
            if "hang" in str(path):
                import time

                time.sleep(1.0)
            return super().Open(path, **kw)

    @property
    def Documents(self):  # noqa: N802
        return SlowOpenWordApp._Docs(self)


def test_runner_timeout_and_recovery():
    """행 걸린 파일은 ExtractTimeout, 러너는 새 앱으로 다음 파일을 계속 처리한다."""
    runner = worker.ExtractorRunner(
        extractors.WordExtractor, lambda: SlowOpenWordApp("본문"), timeout=0.2
    )
    try:
        with pytest.raises(worker.ExtractTimeout):
            runner.extract("hang.docx")
        assert "본문" in runner.extract("ok.docx")  # 재기동 후 정상 처리
    finally:
        runner.close()


def test_runner_propagates_startup_error():
    """앱 기동 실패(비 Windows 등)는 타임아웃 대기 없이 즉시 에러로 전달된다."""

    def broken_factory():
        raise RuntimeError("Office 없음")

    runner = worker.ExtractorRunner(extractors.WordExtractor, broken_factory, timeout=5.0)
    try:
        with pytest.raises(RuntimeError, match="Office 없음"):
            runner.extract("a.docx")
    finally:
        runner.close()


# ── 배치 인제스트 + 매니페스트 테스트 ─────────────────────────────────
def _make_docs(tmp_path, names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"fake-office-bytes")
        paths.append(str(p))
    return paths


def test_ingest_target_batches_and_reuses_app(tmp_path):
    """폴더 배치: 앱은 타입별 1개만 생성되고, 전송은 batch_size 단위로 묶인다."""
    _make_docs(tmp_path, ["a.docx", "b.docx", "c.docx"])
    created: list[FakeWordApp] = []

    def factory():
        app = FakeWordApp("본문")
        created.append(app)
        return app

    batches: list[int] = []

    def batch_poster(payloads):
        batches.append(len(payloads))
        return [{"id": pl["title"]} for pl in payloads]

    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", batch_poster=batch_poster,
        batch_size=2, factories={"Word.Application": factory},
    )
    assert len(results) == 3
    assert batches == [2, 1]      # 2건 배치 + 잔여 1건
    assert len(created) == 1      # 파일 3개에 Word 앱 1개 재사용
    assert created[0].quit is True


def test_ingest_target_state_skips_unchanged(tmp_path):
    """매니페스트가 있으면 재실행 시 변경 없는 파일을 건너뛴다(force 로 무시 가능)."""
    _make_docs(tmp_path, ["a.docx", "b.docx"])
    state = tmp_path / "state.json"
    factories = {"Word.Application": lambda: FakeWordApp("본문")}
    calls: list[int] = []

    def batch_poster(payloads):
        calls.append(len(payloads))
        return [{"id": pl["title"]} for pl in payloads]

    kw = dict(batch_poster=batch_poster, state_path=state, factories=factories)
    assert len(worker.ingest_target(str(tmp_path), "http://mi:8000", **kw)) == 2
    assert len(worker.ingest_target(str(tmp_path), "http://mi:8000", **kw)) == 0  # 전부 skip
    assert len(worker.ingest_target(str(tmp_path), "http://mi:8000", force=True, **kw)) == 2
    assert calls == [2, 2]


class _ClientError(Exception):
    """httpx.HTTPStatusError 모양(4xx response)의 가짜 예외."""

    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.response = type("R", (), {"status_code": status})()


def test_ingest_target_isolates_poison_payload(tmp_path):
    """배치가 4xx 로 거부되면 단건으로 격리 재시도 — 불량 1건이 배치를 침몰시키지 않는다."""
    _make_docs(tmp_path, ["a.docx", "bad.docx", "c.docx"])

    def batch_poster(payloads):
        if len(payloads) > 1 or payloads[0]["title"] == "bad":
            raise _ClientError(422)
        return [{"id": payloads[0]["title"]}]

    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", batch_poster=batch_poster,
        batch_size=3, factories={"Word.Application": lambda: FakeWordApp("본문")},
    )
    assert sorted(d["id"] for d in results) == ["a", "c"]  # bad 만 실패


def test_ingest_target_server_error_fails_batch_without_retry(tmp_path):
    """5xx/네트워크 장애는 단건 재시도 없이 배치 실패(요청 폭증 방지)."""
    _make_docs(tmp_path, ["a.docx", "b.docx"])
    calls: list[int] = []

    def batch_poster(payloads):
        calls.append(len(payloads))
        raise RuntimeError("connection refused")

    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", batch_poster=batch_poster,
        factories={"Word.Application": lambda: FakeWordApp("본문")},
    )
    assert results == [] and calls == [2]  # 배치 1회만 시도


def test_ingest_target_state_is_per_backend(tmp_path):
    """매니페스트는 백엔드 URL 별 — 백엔드를 바꿔 재실행하면 skip 하지 않는다."""
    _make_docs(tmp_path, ["a.docx"])
    state = tmp_path / "state.json"
    factories = {"Word.Application": lambda: FakeWordApp("본문")}

    def bp(payloads):
        return [{"id": pl["title"]} for pl in payloads]

    kw = dict(batch_poster=bp, state_path=state, factories=factories)
    assert len(worker.ingest_target(str(tmp_path), "http://one:8000", **kw)) == 1
    assert len(worker.ingest_target(str(tmp_path), "http://one:8000", **kw)) == 0  # 같은 백엔드: skip
    assert len(worker.ingest_target(str(tmp_path), "http://two:8000", **kw)) == 1  # 다른 백엔드: 재인제스트


def test_ingest_target_single_poster_compat(tmp_path):
    """단건 poster 주입(기존 인터페이스)도 배치 어댑터로 동작한다."""
    _make_docs(tmp_path, ["a.docx"])
    posted = []

    def poster(url, payload):
        posted.append((url, payload["title"]))
        return {"id": payload["title"]}

    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", poster=poster,
        factories={"Word.Application": lambda: FakeWordApp("본문")},
    )
    assert results == [{"id": "a"}]
    assert posted == [("http://mi:8000", "a")]
