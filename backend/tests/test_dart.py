"""DART 커넥터 테스트(네트워크 없이)."""

from __future__ import annotations

import asyncio

from app import collection, dart, pipeline

_OVERVIEW = {"status": "000", "corp_name": "삼성전자", "corp_code": "00126380",
             "stock_code": "005930", "ceo_nm": "홍길동"}
_DISCLOSURES = {"status": "000", "list": [
    {"rcept_dt": "20260514", "report_nm": "분기보고서 (2026.03)"},
    {"rcept_dt": "20260311", "report_nm": "사업보고서 (2025.12)"},
]}
_FIN = {"status": "000", "list": [
    {"account_nm": "매출액", "thstrm_amount": "75,000,000,000,000", "bsns_year": "2025", "sj_div": "IS"},
    {"account_nm": "영업이익", "thstrm_amount": "10,000,000,000,000", "bsns_year": "2025", "sj_div": "IS"},
    {"account_nm": "당기순이익", "thstrm_amount": "8,000,000,000,000", "bsns_year": "2025", "sj_div": "IS"},
]}


def test_config_from_source_pads_corp_code():
    corp, name = dart.config_from_source({"config": {"corp_code": "126380", "name": "삼성전자"}})
    assert corp == "00126380" and name == "삼성전자"


def test_parse_company_ir():
    doc = dart.parse_company_ir("", _OVERVIEW, _DISCLOSURES, _FIN)
    assert "삼성전자" in doc["title"] and "경쟁사 IR" in doc["title"]
    assert "분기보고서" in doc["text"]
    assert "매출액: 75,000,000,000,000" in doc["text"]
    assert "당기순이익: 8,000,000,000,000" in doc["text"]
    assert "DART" in doc["text"]


class _Resp:
    def __init__(self, p):
        self._p = p

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Http:
    def __init__(self):
        self.calls = []

    async def get(self, url, **kw):
        self.calls.append(url)
        if "company.json" in url:
            return _Resp(_OVERVIEW)
        if "list.json" in url:
            return _Resp(_DISCLOSURES)
        return _Resp(_FIN)


def test_fetch_company_ir(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "testkey")
    http = _Http()
    doc = asyncio.run(dart.fetch_company_ir(http, "00126380", "삼성전자", year=2026))
    assert "매출액: 75,000,000,000,000" in doc["text"]
    assert any("fnlttSinglAcnt" in u for u in http.calls)


def test_collect_dart_missing_key(client, monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    sid = client.post("/collection/sources", json={
        "name": "경쟁사 IR · DART", "type": "dart", "config": {"corp_code": "00126380", "name": "삼성전자"},
    }).json()["id"]
    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_dart_source(source, client=None))
    assert docs == [] and errors and "DART_API_KEY" in errors[0]["error"]
