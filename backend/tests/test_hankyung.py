"""한경 컨센서스 PDF 커넥터 테스트(네트워크 없이)."""

from __future__ import annotations

import asyncio

import pytest

from app import collection, hankyung, pipeline

_HTML = """
<tbody>
  <tr class="first">
    <td class="first txt_number">2026-06-17</td>
    <td class="text_l">
      <a href="/analysis/downpdf?report_idx=650122" onmouseover="x" target="_blank">하이비젼시스템(126700) ESS로 증명하고 본업은 돌아선다 </a>
    </td>
  </tr>
  <tr>
    <td class="text_l">
      <a href="/analysis/downpdf?report_idx=650124" target="_blank">삼성전자(005930) HBM4 모멘텀 </a>
    </td>
  </tr>
</tbody>
"""


def test_parse_listing():
    rows = hankyung.parse_listing(_HTML)
    assert len(rows) == 2
    assert rows[0]["report_idx"] == "650122"
    assert "하이비젼시스템" in rows[0]["title"]
    assert rows[1]["report_idx"] == "650124"


def test_extract_pdf_text_rejects_non_pdf():
    assert hankyung.extract_pdf_text(b"not a pdf") == ""
    assert hankyung.extract_pdf_text(b"") == ""


def test_extract_pdf_text_via_pymupdf():
    """PyMuPDF 설치 시 고속 경로로 실제 PDF 바이트에서 본문을 추출한다."""
    from app import pdftext

    if not pdftext.available():
        pytest.skip("pymupdf 미설치")
    mod = pdftext._pymupdf()
    doc = mod.open()
    doc.new_page().insert_text((72, 72), "target price raised")
    content = doc.tobytes()
    doc.close()
    assert "target price raised" in hankyung.extract_pdf_text(content)


class _Resp:
    def __init__(self, *, text="", content=b""):
        self.text = text
        self.content = content

    def raise_for_status(self):
        pass


class _Http:
    def __init__(self):
        self.calls = []

    async def get(self, url, **kw):
        self.calls.append(url)
        if "list?" in url:
            return _Resp(text=_HTML)
        return _Resp(content=b"%PDF-1.7 fake")


def test_fetch_reports(monkeypatch):
    monkeypatch.setattr(hankyung, "extract_pdf_text", lambda c: "리포트 본문 텍스트")
    docs = asyncio.run(hankyung.fetch_reports(_Http(), limit=2))
    assert len(docs) == 2
    assert docs[0]["title"].startswith("[증권사 리포트]")
    assert "리포트 본문 텍스트" in docs[0]["text"]
    assert "report_idx=650122" in docs[0]["url"]


def test_collect_hankyung_source_syncs(client, monkeypatch):
    sid = client.post("/collection/sources", json={
        "name": "한경 컨센서스", "type": "hankyung", "config": {"limit": 2},
    }).json()["id"]

    async def fake_fetch(c, base=hankyung.BASE_DEFAULT, **kw):
        return hankyung.parse_listing(_HTML) and [
            {"id": "650122", "title": "T1", "text": "본문1", "url": "u1"},
            {"id": "650124", "title": "T2", "text": "본문2", "url": "u2"},
        ]

    monkeypatch.setattr(hankyung, "fetch_reports", fake_fetch)
    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_hankyung_source(source, client=None))
    assert errors == [] and len(docs) == 2
    found = client.get("/collection/documents", params={"topic": "컨센서스"}).json()["documents"]
    assert len(found) == 2
