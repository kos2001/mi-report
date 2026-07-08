"""MS Office 텍스트 추출기 (COM).

각 추출기는 COM 애플리케이션을 '앱 팩토리'(인자 없는 콜러블)로부터 받는다.
실제 실행에서는 win32com 으로 Word/Excel/PowerPoint 를 띄우고,
테스트에서는 동일한 인터페이스를 흉내내는 가짜 객체를 주입한다.
이 덕분에 Windows 가 아닌 환경에서도 추출 오케스트레이션을 단위 테스트할 수 있다.

앱 수명주기: 추출기는 컨텍스트 매니저다. `with` 블록 동안 Office 앱 1개를
재사용해 파일들을 연달아 추출한다(파일마다 프로세스 기동/종료 비용 제거).
일회성 추출은 extract_text() 를 쓰면 종료까지 처리된다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from app import officetext, pdftext

AppFactory = Callable[[], Any]


def get_com_factory(prog_id: str) -> AppFactory:
    """주어진 ProgID 의 COM 앱을 생성하는 팩토리. Windows 에서만 동작."""

    def factory() -> Any:
        if sys.platform != "win32":
            raise RuntimeError(
                f"COM({prog_id})은 Windows 에서만 사용할 수 있습니다. "
                "DRM 클라이언트+MS Office 가 설치된 Windows 워커에서 실행하세요."
            )
        import win32com.client  # type: ignore  # noqa: PLC0415 (Windows 전용 지연 import)

        # DispatchEx: 사용자가 쓰는 기존 Office 인스턴스에 붙지 않고 별도 프로세스로 띄운다.
        return win32com.client.DispatchEx(prog_id)

    return factory


class BaseExtractor:
    """앱 재사용 수명주기를 제공하는 공통 추출기.

    with 블록에서 앱 1개를 띄워 extract() 호출들이 재사용한다. Office 는
    장시간 재사용 시 메모리가 누적되므로 배치 러너가 restart() 로 주기 재기동한다.
    """

    prog_id: str

    def __init__(self, app_factory: AppFactory | None = None):
        self._factory = app_factory or get_com_factory(self.prog_id)
        self._app: Any | None = None
        self.last_route: str | None = None  # 직전 추출 경로: "local" | "com"

    def __enter__(self):
        self._ensure_app()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _ensure_app(self) -> Any:
        if self._app is None:
            app = self._factory()
            try:
                self._configure(app)
            except Exception:
                # 설정 실패 시 방금 띄운 프로세스를 즉시 회수(추적 안 되는 누수 방지)
                try:
                    app.Quit()
                except Exception:
                    pass
                raise
            self._app = app
        return self._app

    def close(self) -> None:
        app, self._app = self._app, None
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass  # 이미 죽었거나 행 상태의 앱 — 종료 실패는 무시

    def restart(self) -> None:
        """앱을 재기동한다(메모리 누수 예방 주기 재시작, 장애 복구)."""
        self.close()
        self._ensure_app()

    def pid(self) -> int | None:
        """앱 프로세스 PID(가능한 경우). 워치독의 강제 종료에 쓴다.

        Excel(Hwnd)/PowerPoint(HWND)는 창 핸들로 역추적하고, Word 는 핸들을
        노출하지 않아 None 일 수 있다(그 경우 행 프로세스는 강제 종료 불가).
        """
        if sys.platform != "win32" or self._app is None:
            return None
        hwnd = 0
        for attr in ("Hwnd", "HWND"):
            try:
                hwnd = int(getattr(self._app, attr))
                break
            except Exception:
                continue
        if not hwnd:
            return None
        try:
            import win32process  # type: ignore  # noqa: PLC0415

            return win32process.GetWindowThreadProcessId(hwnd)[1]
        except Exception:
            return None

    def _configure(self, app: Any) -> None:
        """앱 생성 직후 1회 설정(창 숨김·경고 억제). 파일마다 반복하지 않는다."""

    def _extract(self, app: Any, path: str) -> str:
        raise NotImplementedError

    def extract(self, path: str) -> str:
        self.last_route = "com"
        return self._extract(self._ensure_app(), path)


class WordExtractor(BaseExtractor):
    prog_id = "Word.Application"

    def _configure(self, app: Any) -> None:
        app.Visible = False
        app.DisplayAlerts = False

    def _extract(self, app: Any, path: str) -> str:
        # PDF 폴백도 이 경로를 탄다: Word 2013+ 가 리플로우 변환으로 연다
        # (ConfirmConversions=False 로 변환 확인 대화상자 억제).
        doc = app.Documents.Open(
            path, ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False
        )
        try:
            return str(doc.Content.Text)
        finally:
            doc.Close(False)


class ExcelExtractor(BaseExtractor):
    prog_id = "Excel.Application"

    def _configure(self, app: Any) -> None:
        app.Visible = False
        app.DisplayAlerts = False

    def _extract(self, app: Any, path: str) -> str:
        wb = app.Workbooks.Open(path, ReadOnly=True, UpdateLinks=0)
        try:
            parts: list[str] = []
            for sheet in wb.Worksheets:
                values = sheet.UsedRange.Value
                parts.append(f"# {sheet.Name}")
                parts.append(_flatten_cells(values))
            return "\n".join(p for p in parts if p)
        finally:
            wb.Close(False)


# PpAlertLevel.ppAlertsNone. Word/Excel 과 달리 False/0 은 유효값이 아니다(ppAlertsAll=2).
PP_ALERTS_NONE = 1


class PowerPointExtractor(BaseExtractor):
    prog_id = "PowerPoint.Application"

    def _configure(self, app: Any) -> None:
        # PowerPoint 는 Visible=False 를 허용하지 않는다(창 없는 열기는 WithWindow=False).
        try:
            app.DisplayAlerts = PP_ALERTS_NONE  # DRM/복구 대화상자 억제
        except Exception:
            pass  # 일부 버전은 미지원

    def _extract(self, app: Any, path: str) -> str:
        pres = app.Presentations.Open(path, ReadOnly=True, WithWindow=False)
        try:
            parts: list[str] = []
            for idx, slide in enumerate(pres.Slides, start=1):
                parts.append(f"--- slide {idx} ---")
                for shape in slide.Shapes:
                    if shape.HasTextFrame and shape.TextFrame.HasText:
                        parts.append(str(shape.TextFrame.TextRange.Text))
            return "\n".join(parts)
        finally:
            pres.Close()


# ── Adobe Acrobat (IAC/COM) PDF 추출 ─────────────────────────────────────
# 나스카(NASCA) 등 기업용 DRM 은 보통 PDF 를 Acrobat/Reader 에 인가한다(Word 아님).
# Acrobat 이 PDF 를 열면 DRM 이 투명 복호화 → JSObject 로 단어 단위 텍스트를 회수한다.
# Word 리플로우 폴백보다 표·다단 PDF 의 텍스트 품질이 낫다.
# 필요 조건: Acrobat '전체 제품'(Pro/Standard) — 무료 Reader 는 IAC/JSObject 미지원.
ACRO_CLOSE_NO_SAVE = 1  # AVDoc.Close(1): 저장 없이 닫기


def _new_avdoc() -> Any:
    """AcroExch.AVDoc COM 객체(문서 단위) 생성. Windows+Acrobat 전용.

    App(수명주기)과 달리 문서마다 새로 만든다. 테스트는 이 함수를 몽키패치해
    가짜 AVDoc 을 주입한다(비 Windows 에서 오케스트레이션 검증).
    """
    if sys.platform != "win32":
        raise RuntimeError(
            "Acrobat COM 은 Windows 에서만 사용할 수 있습니다. "
            "DRM 클라이언트+Adobe Acrobat(전체 제품)이 설치된 워커에서 실행하세요."
        )
    import win32com.client  # type: ignore  # noqa: PLC0415

    return win32com.client.DispatchEx("AcroExch.AVDoc")


class AcrobatExtractor(BaseExtractor):
    """Adobe Acrobat(IAC/COM)로 PDF 텍스트 추출.

    AcroExch.App(수명주기) + AcroExch.AVDoc(문서) + JSObject(getPageNthWord).
    """

    prog_id = "AcroExch.App"

    def _configure(self, app: Any) -> None:
        try:
            app.Hide()  # 창 숨김(백그라운드 자동화)
        except Exception:
            pass  # 일부 버전/설정은 Hide 미지원 — 무시하고 진행

    def close(self) -> None:
        # AcroExch.App 은 Quit 이 아니라 Exit 로 종료한다(그 외 수명주기는 Base 와 동일).
        app, self._app = self._app, None
        if app is not None:
            try:
                app.Exit()
            except Exception:
                pass

    def _extract(self, app: Any, path: str) -> str:
        avdoc = _new_avdoc()
        if not avdoc.Open(path, ""):
            raise RuntimeError(f"Acrobat 으로 PDF 열기 실패(권한/인가 확인): {path}")
        try:
            pddoc = avdoc.GetPDDoc()
            jso = pddoc.GetJSObject()  # Acrobat Pro/Standard 필요
            parts: list[str] = []
            for p in range(int(pddoc.GetNumPages())):
                try:
                    nwords = int(jso.getPageNumWords(p))
                except Exception:
                    continue  # 페이지 단어수 조회 실패 → 해당 페이지 건너뜀
                words: list[str] = []
                for i in range(nwords):
                    try:
                        w = str(jso.getPageNthWord(p, i)).strip()
                    except Exception:
                        continue
                    if w:
                        words.append(w)
                if words:
                    parts.append(" ".join(words))
            return "\n".join(parts)
        finally:
            try:
                avdoc.Close(ACRO_CLOSE_NO_SAVE)
            except Exception:
                pass  # 닫기 실패는 무시(다음 파일이 새 AVDoc 을 연다)


class LocalFirstMixin:
    """로컬 고속 파서 우선 → 실패(None) 시 COM 폴백.

    일반 문서는 Office 기동 없이 즉시 추출한다(비 Windows 워커에서도 동작).
    DRM 래핑 문서는 로컬 파서가 (파일 시그니처 훼손으로) 자연히 실패해 COM 경로로
    넘어간다 — DRM 투명 복호화라는 기존 계약은 그대로 유지된다.
    """

    @staticmethod
    def _local(path: str) -> str | None:  # 서브클래스가 포맷별 파서를 지정
        raise NotImplementedError

    def __enter__(self):
        return self  # COM 앱은 폴백이 실제로 필요할 때만 띄운다(지연 기동)

    def extract(self, path: str) -> str:
        text = self._local(path)
        if text is not None:
            self.last_route = "local"
            return text
        return super().extract(path)  # type: ignore[misc]  # last_route="com" 설정됨


class PdfAcrobatExtractor(LocalFirstMixin, AcrobatExtractor):
    """PDF: PyMuPDF 우선 → Acrobat COM 폴백(DRM/암호화/스캔본). 나스카 권장."""

    @staticmethod
    def _local(path: str) -> str | None:
        return pdftext.extract_path(path)


class PdfWordExtractor(LocalFirstMixin, WordExtractor):
    """PDF: PyMuPDF 우선 → Word COM 리플로우 폴백. Acrobat 미보유 환경용."""

    @staticmethod
    def _local(path: str) -> str | None:
        return pdftext.extract_path(path)


def _pdf_extractor_cls() -> type[BaseExtractor]:
    """PDF COM 폴백 엔진 선택. MI_PDF_COM_ENGINE=word(기본)|acrobat.

    기본은 word: Word 리플로우는 이미 있는 MS Office 만 있으면 되고, Acrobat COM
    (IAC/JSObject)은 유료 제품(Pro/Standard)에서만 동작한다(무료 Reader 미지원).
    Acrobat 을 PDF 인가 뷰어로 두고 유료 제품을 보유한 환경만 acrobat 으로 지정한다.
    """
    engine = (os.getenv("MI_PDF_COM_ENGINE") or "word").strip().lower()
    return PdfAcrobatExtractor if engine == "acrobat" else PdfWordExtractor


# 하위호환 별칭 + 확장자 매핑(임포트 시 엔진 확정 — 워커는 실행 전 env 를 설정한다).
PdfExtractor = _pdf_extractor_cls()


class DocxExtractor(LocalFirstMixin, WordExtractor):
    """docx: python-docx 우선 → Word COM 폴백(DRM)."""

    @staticmethod
    def _local(path: str) -> str | None:
        return officetext.extract_docx(path)


class XlsxExtractor(LocalFirstMixin, ExcelExtractor):
    """xlsx/xlsm: openpyxl(read_only) 우선 → Excel COM 폴백(DRM)."""

    @staticmethod
    def _local(path: str) -> str | None:
        return officetext.extract_xlsx(path)


class PptxExtractor(LocalFirstMixin, PowerPointExtractor):
    """pptx: python-pptx 우선 → PowerPoint COM 폴백(DRM)."""

    @staticmethod
    def _local(path: str) -> str | None:
        return officetext.extract_pptx(path)


def _flatten_cells(values: Any) -> str:
    """Excel UsedRange.Value(스칼라 또는 행×열 튜플)를 탭/줄바꿈 텍스트로."""
    if values is None:
        return ""
    if not isinstance(values, tuple):
        return str(values)
    rows: list[str] = []
    for row in values:
        if isinstance(row, tuple):
            rows.append("\t".join("" if c is None else str(c) for c in row))
        else:
            rows.append("" if row is None else str(row))
    return "\n".join(rows)


# 확장자 → 추출기 클래스. OOXML/PDF 는 로컬 고속 경로(→ DRM 시 COM 폴백),
# 레거시 바이너리(doc/xls/ppt/rtf)는 좋은 로컬 파서가 없어 COM 전용.
EXTRACTORS: dict[str, type[BaseExtractor]] = {
    ".doc": WordExtractor,
    ".docx": DocxExtractor,
    ".rtf": WordExtractor,
    ".pdf": PdfExtractor,
    ".xls": ExcelExtractor,
    ".xlsx": XlsxExtractor,
    ".xlsm": XlsxExtractor,
    ".ppt": PowerPointExtractor,
    ".pptx": PptxExtractor,
}

SUPPORTED_EXTENSIONS = tuple(EXTRACTORS.keys())


def extractor_class(path: str) -> type[BaseExtractor]:
    """경로의 확장자에 맞는 추출기 클래스를 고른다(미지원이면 ValueError)."""
    suffix = Path(path).suffix.lower()
    cls = EXTRACTORS.get(suffix)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 형식: {suffix} (지원: {', '.join(SUPPORTED_EXTENSIONS)})"
        )
    return cls


def extract_text(path: str, factories: dict[str, AppFactory] | None = None) -> str:
    """확장자에 맞는 추출기로 텍스트를 뽑는다(일회성: 앱 기동→추출→종료).

    factories: 테스트용. {prog_id: app_factory} 로 가짜 COM 앱을 주입한다.
    배치에서는 워커의 러너가 추출기를 재사용하므로 이 함수를 쓰지 않는다.
    """
    cls = extractor_class(path)
    app_factory = None
    if factories is not None:
        app_factory = factories.get(cls.prog_id)
    with cls(app_factory) as ex:
        return ex.extract(path)
