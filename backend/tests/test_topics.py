"""주제별 History 생성 테스트.

순수 로직은 네트워크 없이, 엔드포인트는 페이크 게이트웨이 클라이언트를 주입해 검증.
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app import main, topics
from app.schemas import TopicSummaryOut


class FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple] = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


_VALID_RESPONSE = json.dumps(
    {
        "category": "수요/시황",
        "summary": "HBM 수요가 AI 가속기 투자로 강세를 지속한다.",
        "insight": "HBM 공급 부족이 일반 DRAM 캐파를 잠식할 수 있다.",
        "history": [
            {"date": "2026-06-10", "event": "HBM4 채택 공식화", "source": "기술 뉴스"},
            {"date": "2026-05-28", "event": "가속기 로드맵 공개", "source": "뉴스"},
        ],
    },
    ensure_ascii=False,
)


# ── 순수 로직 ─────────────────────────────────────────────────────────────
def test_slugify():
    assert topics.slugify("HBM 수요 사이클") == "hbm-수요-사이클"
    assert topics.slugify("  ") == "topic"


def test_build_messages_includes_topic_and_docs():
    docs = [{"title": "T", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문X"}]
    msgs = topics.build_messages("HBM 수요", docs)
    assert msgs[0]["role"] == "system"
    assert "HBM 수요" in msgs[1]["content"]
    assert "본문X" in msgs[1]["content"]


def test_parse_summary_valid():
    out = topics.parse_summary(_VALID_RESPONSE)
    assert isinstance(out, TopicSummaryOut)
    assert out.category == "수요/시황"
    assert len(out.history) == 2


def test_parse_summary_invalid_raises():
    with pytest.raises(ValueError):
        topics.parse_summary("JSON 아님")


def test_generate_topic_summary_assigns_metadata():
    client = FakeClient(_VALID_RESPONSE)
    docs = [{"title": "T", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]
    result = asyncio.run(
        topics.generate_topic_summary(client, "HBM 수요", docs, updated_at="2026-06-13")
    )
    assert result["id"] == "hbm-수요"
    assert result["title"] == "HBM 수요"
    assert result["sourceCount"] == 1
    assert result["updatedAt"] == "2026-06-13"
    assert result["generated"] is True
    assert len(result["history"]) == 2
    assert result["unsupportedClaims"] == []
    # 요약 호출 + 총평 검증(audit) 호출
    assert len(client.calls) == 2


def test_generate_topic_summary_grounds_numbers_and_history():
    # summary 에 미근거 수치(999), history 에 거짓 출처(없는 매체) → 둘 다 플래그.
    resp = json.dumps({
        "category": "수요/시황",
        "summary": "HBM 점유율 35% 기록, 매출 999억 전망.",
        "insight": "S.LSI 연계.",
        "history": [
            {"date": "2026-06-10", "event": "HBM4 채택 공식화", "source": "기술뉴스"},
            {"date": "2026-05-01", "event": "조작된 사건 ZZZ", "source": "없는매체"},
        ],
    }, ensure_ascii=False)
    docs = [{"title": "HBM4 채택 공식화", "source": "기술뉴스",
             "publishedAt": "2026-06-10", "content": "HBM4 채택. 점유율 35% 기록."}]
    out = asyncio.run(
        topics.generate_topic_summary(FakeClient(resp), "HBM", docs, updated_at="2026-06-13")
    )
    assert out["numbersGrounded"] is False and "999" in out["ungroundedNumbers"]
    assert "35" not in out["ungroundedNumbers"]          # 문서 근거 수치는 통과
    assert out["history"][0]["sourceVerified"] is True   # 출처·제목 일치
    assert out["history"][1]["sourceVerified"] is False  # 거짓 출처
    assert out["unverifiedHistoryCount"] == 1


def test_generate_topic_summary_flags_unsupported_claims():
    # summary/insight 에 원문이 뒷받침하지 않는 추세 주장 → 독립 검증 agent 가 잡는다.
    class RoutingFakeClient:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                content = json.dumps({
                    "category": "수요/시황",
                    "summary": "HBM 수요가 3주 연속 악화되고 있다.",
                    "insight": "S.LSI 연계.",
                    "history": [],
                }, ensure_ascii=False)
            else:
                content = json.dumps({
                    "unsupported": [{"claim": "3주 연속 악화되고 있다", "why": "원문에 추세 언급 없음"}],
                }, ensure_ascii=False)
            return {"choices": [{"message": {"content": content}}]}

    docs = [{"title": "HBM", "source": "뉴스", "publishedAt": "2026-06-10", "content": "HBM 수요 관련 보도."}]
    out = asyncio.run(
        topics.generate_topic_summary(RoutingFakeClient(), "HBM", docs, updated_at="2026-06-13")
    )
    assert out["unsupportedClaims"] == ["3주 연속 악화되고 있다"]


def test_generate_topic_summary_empty_docs_raises():
    with pytest.raises(ValueError):
        asyncio.run(
            topics.generate_topic_summary(FakeClient(""), "t", [], updated_at="2026-06-13")
        )


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_topics_list_endpoint(client):
    _upload(client, "a.txt", "HBM 관련 본문.", "HBM")
    _upload(client, "b.txt", "HBM 추가 본문.", "HBM")
    _upload(client, "c.txt", "파운드리 본문.", "파운드리")
    r = client.get("/topics")
    assert r.status_code == 200
    by_topic = {t["topic"]: t["count"] for t in r.json()["topics"]}
    assert by_topic["HBM"] == 2
    assert by_topic["파운드리"] == 1


def test_topics_summarize_endpoint(client, monkeypatch):
    _upload(client, "hbm.txt", "HBM4 채택 공식화. AI 가속기 수요 강세.", "HBM")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/topics/summarize", json={"topic": "HBM"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "HBM"
    assert body["sourceCount"] == 1
    assert body["category"] == "수요/시황"
    assert len(body["history"]) == 2


def test_topics_summarize_no_documents_422(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/topics/summarize", json={"topic": "없는주제"})
    assert r.status_code == 422


def test_topics_summarize_bad_llm_output_502(client, monkeypatch):
    _upload(client, "d.txt", "본문.", "HBM")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient("JSON 아님"))
    r = client.post("/topics/summarize", json={"topic": "HBM"})
    assert r.status_code == 502
