"""COM 인제스트 추출/워커 테스트.

실제 COM/Windows 없이, COM 인터페이스를 흉내내는 가짜 객체를 주입해
추출 오케스트레이션과 워커 페이로드/등록 흐름을 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


# ── 가짜 Acrobat COM 스택 (IAC 인터페이스 모사) ──────────────────────
class _FakeJso:
    def __init__(self, pages):  # pages: list[list[str]] — 페이지별 단어 목록
        self._pages = pages

    def getPageNumWords(self, p):  # noqa: N802
        return len(self._pages[p])

    def getPageNthWord(self, p, i):  # noqa: N802
        return self._pages[p][i]


class _FakePdDoc:
    def __init__(self, pages):
        self._pages = pages

    def GetNumPages(self):  # noqa: N802
        return len(self._pages)

    def GetJSObject(self):  # noqa: N802
        return _FakeJso(self._pages)


class FakeAvDoc:
    """AcroExch.AVDoc 모사. words 는 단일 페이지 단어 목록."""

    def __init__(self, words):
        self._pages = [words]
        self.closed = False

    def Open(self, path, msg):  # noqa: N802
        return True

    def GetPDDoc(self):  # noqa: N802
        return _FakePdDoc(self._pages)

    def Close(self, flag):  # noqa: N802
        self.closed = True


class FakeAcroApp:
    """AcroExch.App 모사(Hide/Exit 수명주기)."""

    def __init__(self):
        self.exited = False

    def Hide(self):  # noqa: N802
        pass

    def Exit(self):  # noqa: N802
        self.exited = True


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
    """word 엔진: PyMuPDF 가 못 읽는 PDF 는 Word 리플로우 폴백으로 추출한다."""
    from app import pdftext

    monkeypatch.setattr(pdftext, "extract_path", lambda p, **k: None)
    with extractors.PdfWordExtractor(lambda: FakeWordApp("PDF 본문")) as ex:
        text = ex.extract("scan.pdf")
    assert "PDF 본문" in text


def test_pdf_falls_back_to_acrobat(monkeypatch):
    """acrobat 엔진(나스카 기본): PyMuPDF 가 못 읽는 PDF 는 Acrobat COM(JSObject)로 추출한다."""
    from app import pdftext

    monkeypatch.setattr(pdftext, "extract_path", lambda p, **k: None)
    monkeypatch.setattr(extractors, "_new_avdoc", lambda: FakeAvDoc(["HBM", "수요", "증가"]))
    with extractors.PdfAcrobatExtractor(lambda: FakeAcroApp()) as ex:
        text = ex.extract("drm.pdf")
    assert "HBM" in text and "수요" in text and "증가" in text


def test_pdf_com_engine_selection(monkeypatch):
    """MI_PDF_COM_ENGINE 로 PDF COM 폴백 엔진을 고른다(기본 word)."""
    monkeypatch.setenv("MI_PDF_COM_ENGINE", "acrobat")
    assert extractors._pdf_extractor_cls() is extractors.PdfAcrobatExtractor
    monkeypatch.setenv("MI_PDF_COM_ENGINE", "word")
    assert extractors._pdf_extractor_cls() is extractors.PdfWordExtractor
    monkeypatch.delenv("MI_PDF_COM_ENGINE", raising=False)
    assert extractors._pdf_extractor_cls() is extractors.PdfWordExtractor  # 기본


def test_ooxml_fast_path_skips_office(monkeypatch):
    """일반 docx/xlsx/pptx 는 로컬 파서로 추출한다 — Office 앱을 아예 띄우지 않는다."""
    from app import officetext

    monkeypatch.setattr(officetext, "extract_docx", lambda p: "docx 본문")
    monkeypatch.setattr(officetext, "extract_xlsx", lambda p: "xlsx 본문")
    monkeypatch.setattr(officetext, "extract_pptx", lambda p: "pptx 본문")

    def must_not_launch():
        raise AssertionError("고속 경로에서 Office 를 띄우면 안 된다")

    factories = {p: must_not_launch for p in
                 ("Word.Application", "Excel.Application", "PowerPoint.Application")}
    assert extractors.extract_text("a.docx", factories) == "docx 본문"
    assert extractors.extract_text("b.xlsx", factories) == "xlsx 본문"
    assert extractors.extract_text("c.xlsm", factories) == "xlsx 본문"
    assert extractors.extract_text("d.pptx", factories) == "pptx 본문"


def test_ooxml_drm_falls_back_to_com(tmp_path):
    """DRM 래핑(비 zip) OOXML 은 로컬 파서가 실패해 COM 으로 폴백한다(실파일)."""
    p = tmp_path / "drm.docx"
    p.write_bytes(b"DRM-wrapped, not a zip")
    factories = {"Word.Application": lambda: FakeWordApp("DRM 해제 본문")}
    assert "DRM 해제 본문" in extractors.extract_text(str(p), factories)


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


def test_dry_run_reports_route_without_posting(tmp_path, monkeypatch):
    """--dry-run: 등록 없이 파일별 추출 경로(local/com)와 미리보기를 반환한다."""
    from app import officetext

    _make_docs(tmp_path, ["일반.docx", "drm.docx"])
    # '일반.docx' 만 로컬 파서가 성공하는 상황을 모사(DRM 은 None → COM 폴백)
    monkeypatch.setattr(officetext, "extract_docx",
                        lambda p: "로컬 추출 본문" if "일반" in p else None)

    def must_not_post(payloads):
        raise AssertionError("dry-run 에서 전송 금지")

    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", batch_poster=must_not_post, dry_run=True,
        factories={"Word.Application": lambda: FakeWordApp("COM 추출 본문 (DRM 해제)")},
    )
    by = {Path(r["path"]).name: r for r in results}
    assert by["일반.docx"]["route"] == "local" and "로컬" in by["일반.docx"]["preview"]
    assert by["drm.docx"]["route"] == "com" and "DRM 해제" in by["drm.docx"]["preview"]
    assert all(r["chars"] > 0 for r in results)


def test_flag_low_quality():
    """추출 품질 가드: 빈/과소·U+FFFD·제어문자 텍스트를 경고로 잡고, 정상은 통과."""
    good = "반도체 시장 동향 " * 10
    assert worker.flag_low_quality(good) is None
    assert worker.flag_low_quality("") is not None            # 빈 텍스트
    assert worker.flag_low_quality("너무 짧은 본문") is not None  # < 20자
    assert worker.flag_low_quality(good + "�" * 5) is not None  # 깨진 문자 과다
    assert worker.flag_low_quality("정상 텍스트 " * 5 + "\x00" * 10) is not None  # 제어문자


def test_out_dir_records_quality_warning(tmp_path):
    """--out 결과 dict 에 품질 경고(warn)가 실린다(정상 추출은 None)."""
    _make_docs(tmp_path, ["a.docx"])
    out = tmp_path / "out"
    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", out_dir=out,
        factories={"Word.Application": lambda: FakeWordApp("짧음")},  # 과소 → 경고
    )
    assert results and results[0]["warn"] is not None


def test_ingest_target_out_dir_writes_text(tmp_path):
    """--out: 추출 텍스트를 <stem>.txt 로 저장하고 백엔드 전송은 하지 않는다."""
    _make_docs(tmp_path, ["a.docx", "b.docx"])
    out = tmp_path / "out"

    def must_not_post(payloads):
        raise AssertionError("out 모드에서 전송 금지")

    results = worker.ingest_target(
        str(tmp_path), "http://mi:8000", batch_poster=must_not_post, out_dir=out,
        factories={"Word.Application": lambda: FakeWordApp("추출된 본문")},
    )
    assert sorted(p.name for p in out.glob("*.txt")) == ["a.txt", "b.txt"]
    assert (out / "a.txt").read_text(encoding="utf-8") == "추출된 본문"
    assert len(results) == 2 and all("out" in r for r in results)


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
