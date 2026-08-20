"""경쟁사 IR 분석 생성 테스트.

순수 로직은 네트워크 없이, 엔드포인트는 페이크 게이트웨이 클라이언트를 주입해 검증.
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app import competitors, main
from app.schemas import CompetitorAnalysisOut


class FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple] = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


_VALID_RESPONSE = json.dumps(
    {
        "fiscalQuarter": "FY26 Q2",
        "reportedAt": "2026-04-30",
        "financials": [
            {"metric": "매출", "value": "$11.7B", "qoq": 3.2, "yoy": 12.4},
            {"metric": "영업이익률", "value": "29.1%", "qoq": None, "yoy": None},
        ],
        "callSummary": ["온디바이스 AI 수요로 프리미엄 AP ASP 상승 강조."],
        "qoqChanges": ["차량용 백로그 언급 증가 — 성장 내러티브 이동."],
        "consensus": [
            {
                "metric": "FY26 매출",
                "current": "$45.2B",
                "previous": "$44.8B",
                "revisedAt": "2026-06-05",
                "broker": "해외 IB A",
                "direction": "up",
            }
        ],
    },
    ensure_ascii=False,
)


# ── 순수 로직 ─────────────────────────────────────────────────────────────
def test_build_messages_includes_name_ticker_and_docs():
    docs = [{"title": "IR", "source": "업로드", "publishedAt": "2026-04-30", "content": "실적본문"}]
    msgs = competitors.build_messages("경쟁사 Q", "QCOM", docs)
    assert msgs[0]["role"] == "system"
    assert "경쟁사 Q" in msgs[1]["content"]
    assert "QCOM" in msgs[1]["content"]
    assert "실적본문" in msgs[1]["content"]


def test_parse_analysis_valid():
    out = competitors.parse_analysis(_VALID_RESPONSE)
    assert isinstance(out, CompetitorAnalysisOut)
    assert out.fiscalQuarter == "FY26 Q2"
    assert out.financials[1].qoq is None  # 수치 없으면 null
    assert out.consensus[0].direction == "up"


def test_parse_analysis_invalid_raises():
    with pytest.raises(ValueError):
        competitors.parse_analysis("JSON 없음")


def test_analyze_competitor_assigns_metadata():
    client = FakeClient(_VALID_RESPONSE)
    docs = [{"title": "IR", "source": "업로드", "publishedAt": "2026-04-30",
            "content": "FY26 Q2 매출 11.7B 달러, 영업이익률 29.1%. FY26 매출 컨센서스 45.2B(직전 44.8B)."}]
    result = asyncio.run(competitors.analyze_competitor(client, "경쟁사 Q", "QCOM", docs))
    assert result["id"] == "경쟁사-q"
    assert result["name"] == "경쟁사 Q"
    assert result["ticker"] == "QCOM"
    assert result["sourceDocCount"] == 1
    assert result["generated"] is True
    assert result["financials"][0]["qoq"] == 3.2
    assert result["unsupportedClaims"] == []
    assert len(client.calls) == 2  # 분기 분석 생성 + 총평 검증(audit)


def test_analyze_competitor_flags_unsupported_claims():
    # callSummary 에 원문이 뒷받침하지 않는 추세 주장 → 독립 검증 agent 가 잡는다.
    class RoutingFakeClient:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                content = json.dumps({
                    "fiscalQuarter": "FY26 Q2", "reportedAt": "2026-04-30",
                    "financials": [], "consensus": [],
                    "callSummary": ["3분기 연속 마진이 악화되고 있다."],
                    "qoqChanges": [],
                }, ensure_ascii=False)
            else:
                content = json.dumps({
                    "unsupported": [{"claim": "3분기 연속 마진이 악화되고 있다", "why": "원문에 추세 언급 없음"}],
                }, ensure_ascii=False)
            return {"choices": [{"message": {"content": content}}]}

    docs = [{"title": "IR", "source": "업로드", "publishedAt": "2026-04-30", "content": "FY26 Q2 실적 발표."}]
    result = asyncio.run(competitors.analyze_competitor(RoutingFakeClient(), "경쟁사 Q", "QCOM", docs))
    assert result["unsupportedClaims"] == ["3분기 연속 마진이 악화되고 있다"]


def test_analyze_competitor_empty_docs_raises():
    with pytest.raises(ValueError):
        asyncio.run(competitors.analyze_competitor(FakeClient(""), "X", "", []))


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_competitors_analyze_endpoint(client, monkeypatch):
    _upload(client, "qcom_ir.txt", "FY26 Q2 매출 11.7B 달러, 영업이익률 29.1%. 온디바이스 AI 수요 강조. FY26 매출 컨센서스 45.2B(직전 44.8B).", "QCOM")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/competitors/analyze", json={"name": "경쟁사 Q", "ticker": "QCOM", "topic": "QCOM"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "경쟁사 Q"
    assert body["ticker"] == "QCOM"
    assert body["sourceDocCount"] == 1
    assert body["financials"][0]["metric"] == "매출"
    assert body["consensus"][0]["direction"] == "up"


def test_competitors_analyze_stream_endpoint(client, monkeypatch):
    _upload(client, "qcom_ir.txt", "FY26 Q2 매출 11.7B 달러, 영업이익률 29.1%.", "QCOM")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/competitors/analyze/stream", json={"name": "경쟁사 Q", "ticker": "QCOM", "topic": "QCOM"})
    assert r.status_code == 200
    events = [json.loads(ln[6:]) for ln in r.text.splitlines() if ln.startswith("data: ")]
    tools = [e["tool"] for e in events if e["type"] == "progress"]
    assert tools == ["competitor_generate", "competitor_generate", "competitor_audit", "competitor_audit"]
    assert events[-1]["type"] == "done" and events[-1]["name"] == "경쟁사 Q"


def test_competitors_analyze_no_documents_422(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/competitors/analyze", json={"name": "없는경쟁사", "topic": "없음"})
    assert r.status_code == 422


def test_competitors_analyze_bad_llm_output_502(client, monkeypatch):
    _upload(client, "x.txt", "본문.", "ZZZ")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient("JSON 아님"))
    r = client.post("/competitors/analyze", json={"name": "X", "topic": "ZZZ"})
    assert r.status_code == 502


def test_ungrounded_financials_are_dropped():
    """문서에 없는 재무 수치는 환각으로 보고 결과에서 제외한다."""
    import asyncio
    import json as _json
    from app import competitors
    docs = [{"title": "삼성물산 리포트", "source": "한경", "publishedAt": "",
             "content": "삼성물산 매출 10,466십억원, 목표주가 620,000원."}]
    # LLM이 근거 있는 값(10,466십억원)과 지어낸 값($11.7B)을 섞어 반환
    payload = _json.dumps({
        "fiscalQuarter": "FY24", "reportedAt": "2024-12-31",
        "financials": [
            {"metric": "매출", "value": "10,466십억원", "qoq": None, "yoy": None},
            {"metric": "핸드셋매출", "value": "$11.7B", "qoq": 3.2, "yoy": 12.4},
        ],
        "callSummary": [], "qoqChanges": [], "consensus": [],
    })
    res = asyncio.run(competitors.analyze_competitor(FakeClient(payload), "삼성물산", "028260", docs))
    vals = [f["value"] for f in res["financials"]]
    assert "10,466십억원" in vals           # 근거 있는 값은 유지
    assert "$11.7B" not in vals             # 환각 값은 제외
    assert res["numbersGrounded"] is False
    assert res["droppedCount"] >= 1
