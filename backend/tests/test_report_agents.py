"""주간 리포트 심층분석 agent(Priority/Risk·Critical Point·총평 검증) 테스트."""

from __future__ import annotations

import asyncio
import json

from app import report_agents

_DOCS = [
    {"title": "HBM4 채택 공식화", "source": "뉴스", "publishedAt": "2026-06-10",
     "content": "고객사가 HBM4 12단 적층을 2027년 양산부터 채택하기로 확정했다. 패키징 병목이 우려된다."},
]

_PRIORITY_RISK_JSON = json.dumps({
    "priorities": [{"rank": 1, "title": "HBM4 12단 조기 확보", "rationale": "고객 채택 확정",
                    "evidence": [{"source": "뉴스", "quote": "고객사가 HBM4 12단 적층을 2027년 양산부터 채택하기로 확정했다."}]}],
    "risks": [{"rank": 1, "title": "패키징 병목", "rationale": "적층 수 증가로 인한 공급 제약",
              "evidence": [{"source": "뉴스", "quote": "패키징 병목이 우려된다."}]}],
}, ensure_ascii=False)

_CRITICAL_POINT_JSON = json.dumps({
    "criticalPoints": [{"title": "패키징 캐파 부족", "rootCause": "적층 수 증가",
                        "chainEffect": "공급 지연", "decisionNeeded": "캐파 증설 여부 결정",
                        "evidence": [{"source": "뉴스", "quote": "패키징 병목이 우려된다."}]}],
}, ensure_ascii=False)


class FakeClient:
    def __init__(self, content: str):
        self.content = content

    async def chat(self, messages, **kwargs):
        return {"choices": [{"message": {"content": self.content}}]}


def test_generate_priority_risk_parses_and_grounds():
    result = asyncio.run(report_agents.generate_priority_risk(FakeClient(_PRIORITY_RISK_JSON), _DOCS))
    assert result["priorities"][0]["title"] == "HBM4 12단 조기 확보"
    assert result["priorities"][0]["evidenceGrounded"] is True
    assert result["risks"][0]["title"] == "패키징 병목"
    assert result["risks"][0]["evidenceGrounded"] is True


def test_generate_priority_risk_flags_ungrounded_evidence():
    bad_json = json.dumps({
        "priorities": [{"rank": 1, "title": "지어낸 우선순위", "rationale": "근거 없음",
                        "evidence": [{"source": "뉴스", "quote": "문서에 없는 완전히 다른 문장이다."}]}],
        "risks": [],
    }, ensure_ascii=False)
    result = asyncio.run(report_agents.generate_priority_risk(FakeClient(bad_json), _DOCS))
    assert result["priorities"][0]["evidenceGrounded"] is False


def test_generate_critical_points_parses_and_grounds():
    result = asyncio.run(report_agents.generate_critical_points(FakeClient(_CRITICAL_POINT_JSON), _DOCS))
    assert result["criticalPoints"][0]["title"] == "패키징 캐파 부족"
    assert result["criticalPoints"][0]["evidenceGrounded"] is True


def test_audit_overview_flags_unsupported_claims():
    audit_json = json.dumps({
        "unsupported": [{"claim": "3주 연속 악화되고 있다", "why": "원문에 추세 언급 없음"}],
    }, ensure_ascii=False)
    src_texts = [d["content"] for d in _DOCS]
    result = asyncio.run(report_agents.audit_overview(
        FakeClient(audit_json), "이번 주는 3주 연속 악화되고 있다.", src_texts))
    assert result == [{"claim": "3주 연속 악화되고 있다", "why": "원문에 추세 언급 없음"}]


def test_feedback_block_empty_when_no_notes():
    assert report_agents.feedback_block(None) == ""
    assert report_agents.feedback_block([]) == ""


def test_feedback_block_formats_notes_as_bullets():
    block = report_agents.feedback_block(["수치가 틀림", "출처 누락"])
    assert "수치가 틀림" in block and "출처 누락" in block
    assert block.startswith("\n\n[과거 피드백")


def test_audit_overview_no_findings_returns_empty():
    src_texts = [d["content"] for d in _DOCS]
    result = asyncio.run(report_agents.audit_overview(
        FakeClient(json.dumps({"unsupported": []})), "이번 주는 HBM4 채택이 핵심입니다.", src_texts))
    assert result == []
