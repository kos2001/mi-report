"""주간 MI 리포트 통합 생성 테스트.

오케스트레이션이 다이제스트·주제·총평 호출을 순서대로 수행하는지, 결과를
조립하는지 검증한다. 페이크 클라이언트는 시스템 프롬프트로 호출 종류를 구분해
각기 다른 응답을 돌려준다(네트워크 없음).
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app import main, report

_DIGEST_JSON = json.dumps(
    {
        "items": [
            {
                "title": "HBM4 채택 공식화",
                "source": "뉴스",
                "publishedAt": "2026-06-10",
                "summary": "...",
                "slsiRelevance": "...",
                "demandImpact": "...",
                "risk": "단일 출처 — 교차검증 필요",
                "impact": "high",
                "tags": ["HBM"],
            }
        ]
    },
    ensure_ascii=False,
)

_TOPIC_JSON = json.dumps(
    {
        "category": "수요/시황",
        "summary": "HBM 수요 강세.",
        "insight": "S.LSI 시사점.",
        "history": [{"date": "2026-06-10", "event": "채택", "source": "뉴스"}],
    },
    ensure_ascii=False,
)

_OVERVIEW = "이번 주는 HBM4 채택과 수요 강세가 핵심 흐름입니다."


class RoutingFakeClient:
    """시스템 프롬프트로 호출 종류를 구분해 알맞은 캔드 응답을 돌려준다."""

    def __init__(self):
        self.kinds: list[str] = []

    async def chat(self, messages, **kwargs):
        sys = messages[0]["content"]
        if "뉴스 다이제스트" in sys:
            kind, content = "digest", _DIGEST_JSON
        elif "주제 이력" in sys:
            kind, content = "topic", _TOPIC_JSON
        elif "총평" in sys:
            kind, content = "overview", _OVERVIEW
        else:
            kind, content = "other", "{}"
        self.kinds.append(kind)
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_build_overview_messages_includes_digest_and_topics():
    digest_obj = {"issueNo": 47, "items": [{"title": "HBM4 채택"}]}
    topics = [{"title": "HBM 수요", "summary": "강세"}]
    msgs = report.build_overview_messages(digest_obj, topics)
    assert "총평" in msgs[0]["content"]
    assert "HBM4 채택" in msgs[1]["content"]
    assert "HBM 수요" in msgs[1]["content"]


def test_generate_report_orchestrates_all_parts():
    client = RoutingFakeClient()
    digest_docs = [{"title": "d", "source": "뉴스", "publishedAt": "2026-06-10", "content": "본문"}]
    topic_docs = {"HBM 수요": [{"title": "t", "source": "뉴스", "publishedAt": "2026-06-10", "content": "본문"}]}
    result = asyncio.run(
        report.generate_report(
            client,
            digest_docs=digest_docs,
            topic_docs=topic_docs,
            issue_no=47,
            period="2026.06.08 – 06.11",
            generated_at="2026-06-13",
        )
    )
    assert result["issueNo"] == 47
    assert result["overview"] == _OVERVIEW
    assert result["digest"]["items"][0]["title"] == "HBM4 채택 공식화"
    assert len(result["topics"]) == 1
    assert result["topics"][0]["title"] == "HBM 수요"
    # 다이제스트 → 주제 → 총평 순으로 호출
    assert client.kinds == ["digest", "topic", "overview"]


def test_generate_report_empty_raises():
    with pytest.raises(ValueError):
        asyncio.run(
            report.generate_report(
                RoutingFakeClient(),
                digest_docs=[],
                topic_docs={},
                issue_no=1,
                period="",
                generated_at="2026-06-13",
            )
        )


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_report_generate_endpoint(client, monkeypatch):
    _upload(client, "hbm.txt", "HBM4 채택 공식화. 수요 강세.", "HBM 수요")
    monkeypatch.setattr(main, "get_client", lambda profile=None: RoutingFakeClient())
    r = client.post("/report/generate", json={"issueNo": 48, "period": "이번 주"})
    assert r.status_code == 200
    body = r.json()
    assert body["issueNo"] == 48
    assert body["overview"] == _OVERVIEW
    assert body["digest"] is not None
    assert len(body["topics"]) >= 1


def test_report_generate_no_documents_422(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: RoutingFakeClient())
    r = client.post("/report/generate", json={})
    assert r.status_code == 422
