"""SEC EDGAR 커넥터 테스트(네트워크 없이)."""

from __future__ import annotations

import asyncio

from app import collection, pipeline, sec_edgar

_SUB = {
    "name": "QUALCOMM INC/DE",
    "cik": 804328,
    "filings": {"recent": {
        "form": ["10-Q", "8-K", "4", "10-K"],
        "filingDate": ["2026-04-30", "2026-04-30", "2026-04-15", "2025-11-05"],
    }},
}
_FACTS = {
    "entityName": "QUALCOMM Inc",
    "cik": 804328,
    "facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"start": "2025-09-29", "end": "2025-12-28", "val": 12252000000, "form": "10-Q", "fp": "Q1"},
            # 같은 분기 보고에 누적(YTD ~6개월)과 분기(~3개월)가 공존 → 분기 값이 선택돼야
            {"start": "2025-09-29", "end": "2026-03-29", "val": 22851000000, "form": "10-Q", "fp": "Q2"},
            {"start": "2025-12-29", "end": "2026-03-29", "val": 10599000000, "form": "10-Q", "fp": "Q2"},
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            {"start": "2025-12-29", "end": "2026-03-29", "val": 2700000000, "form": "10-Q", "fp": "Q2"},
        ]}},
    }},
}


def test_config_from_source_pads_cik():
    cik, name = sec_edgar.config_from_source({"config": {"cik": "804328", "name": "Qualcomm"}})
    assert cik == "0000804328" and name == "Qualcomm"


def test_parse_company_ir_extracts_filings_and_financials():
    doc = sec_edgar.parse_company_ir("", _SUB, _FACTS)
    assert "QUALCOMM" in doc["title"]
    assert "경쟁사 IR" in doc["title"]
    # 분기(3개월) 매출이 반영되고 누적(YTD)은 선택되지 않아야
    assert "10,599,000,000" in doc["text"]
    assert "22,851,000,000" not in doc["text"]
    assert "순이익" in doc["text"] and "2,700,000,000" in doc["text"]
    assert "10-Q" in doc["text"] and "10-K" in doc["text"]  # 공시 목록
    assert "data.sec.gov" in doc["text"]


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Http:
    def __init__(self):
        self.calls = []

    async def get(self, url, **kw):
        self.calls.append(url)
        return _Resp(_SUB if "submissions" in url else _FACTS)


def test_fetch_company_ir():
    http = _Http()
    doc = asyncio.run(sec_edgar.fetch_company_ir(http, "0000804328", "Qualcomm"))
    assert "10,599,000,000" in doc["text"]
    assert any("submissions" in u for u in http.calls)
    assert any("companyfacts" in u for u in http.calls)


def test_collect_sec_source_syncs_with_topic(client, monkeypatch):
    sid = client.post("/collection/sources", json={
        "name": "경쟁사 IR · SEC", "type": "sec", "config": {"cik": "0000804328", "name": "Qualcomm"},
    }).json()["id"]

    async def fake_fetch(c, cik, name="", **kw):
        return sec_edgar.parse_company_ir(name, _SUB, _FACTS)

    monkeypatch.setattr(sec_edgar, "fetch_company_ir", fake_fetch)
    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_sec_source(source, client=None))
    assert errors == [] and len(docs) == 1
    # 경쟁사 분석이 topic 으로 찾도록 '경쟁사IR' 주제로 인입됐는지
    found = client.get("/collection/documents", params={"topic": "경쟁사IR"}).json()["documents"]
    assert any("QUALCOMM" in d["title"] for d in found)
