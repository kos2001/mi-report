"""MS Office 텍스트 추출기 (COM).

각 추출기는 COM 애플리케이션을 '앱 팩토리'(인자 없는 콜러블)로부터 받는다.
실제 실행에서는 win32com 으로 Word/Excel/PowerPoint 를 띄우고,
테스트에서는 동일한 인터페이스를 흉내내는 가짜 객체를 주입한다.
이 덕분에 Windows 가 아닌 환경에서도 추출 오케스트레이션을 단위 테스트할 수 있다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

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


class WordExtractor:
    prog_id = "Word.Application"

    def __init__(self, app_factory: AppFactory | None = None):
        self._factory = app_factory or get_com_factory(self.prog_id)

    def extract(self, path: str) -> str:
        app = self._factory()
        app.Visible = False
        app.DisplayAlerts = False
        doc = None
        try:
            doc = app.Documents.Open(
                path, ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False
            )
            return str(doc.Content.Text)
        finally:
            if doc is not None:
                doc.Close(False)
            app.Quit()


class ExcelExtractor:
    prog_id = "Excel.Application"

    def __init__(self, app_factory: AppFactory | None = None):
        self._factory = app_factory or get_com_factory(self.prog_id)

    def extract(self, path: str) -> str:
        app = self._factory()
        app.Visible = False
        app.DisplayAlerts = False
        wb = None
        try:
            wb = app.Workbooks.Open(path, ReadOnly=True, UpdateLinks=0)
            parts: list[str] = []
            for sheet in wb.Worksheets:
                values = sheet.UsedRange.Value
                parts.append(f"# {sheet.Name}")
                parts.append(_flatten_cells(values))
            return "\n".join(p for p in parts if p)
        finally:
            if wb is not None:
                wb.Close(False)
            app.Quit()


class PowerPointExtractor:
    prog_id = "PowerPoint.Application"

    def __init__(self, app_factory: AppFactory | None = None):
        self._factory = app_factory or get_com_factory(self.prog_id)

    def extract(self, path: str) -> str:
        app = self._factory()
        pres = None
        try:
            # PowerPoint 는 창 없이 열 때 WithWindow=False 를 쓴다.
            pres = app.Presentations.Open(path, ReadOnly=True, WithWindow=False)
            parts: list[str] = []
            for idx, slide in enumerate(pres.Slides, start=1):
                parts.append(f"--- slide {idx} ---")
                for shape in slide.Shapes:
                    if shape.HasTextFrame and shape.TextFrame.HasText:
                        parts.append(str(shape.TextFrame.TextRange.Text))
            return "\n".join(parts)
        finally:
            if pres is not None:
                pres.Close()
            app.Quit()


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


# 확장자 → 추출기 클래스
EXTRACTORS: dict[str, type] = {
    ".doc": WordExtractor,
    ".docx": WordExtractor,
    ".rtf": WordExtractor,
    ".xls": ExcelExtractor,
    ".xlsx": ExcelExtractor,
    ".xlsm": ExcelExtractor,
    ".ppt": PowerPointExtractor,
    ".pptx": PowerPointExtractor,
}

SUPPORTED_EXTENSIONS = tuple(EXTRACTORS.keys())


def extract_text(path: str, factories: dict[str, AppFactory] | None = None) -> str:
    """확장자에 맞는 추출기로 텍스트를 뽑는다.

    factories: 테스트용. {prog_id: app_factory} 로 가짜 COM 앱을 주입한다.
    """
    suffix = Path(path).suffix.lower()
    cls = EXTRACTORS.get(suffix)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 형식: {suffix} (지원: {', '.join(SUPPORTED_EXTENSIONS)})"
        )
    app_factory = None
    if factories is not None:
        app_factory = factories.get(cls.prog_id)
    return cls(app_factory).extract(path)
