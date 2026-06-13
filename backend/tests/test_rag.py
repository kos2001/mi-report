"""문서 코퍼스 Q&A(RAG) 테스트.

순수 로직은 네트워크 없이, 엔드포인트는 페이크 게이트웨이 클라이언트를 주입해 검증.
"""

from __future__ import annotations

import asyncio
import io

import pytest

from app import main, rag


class FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple] = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


# ── 순수 로직 ─────────────────────────────────────────────────────────────
def test_build_messages_includes_question_and_docs():
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문Z"}]
    msgs = rag.build_messages("HBM 동향은?", docs)
    assert msgs[0]["role"] == "system"
    assert "[문서 1]" in msgs[1]["content"]
    assert "본문Z" in msgs[1]["content"]
    assert "HBM 동향은?" in msgs[1]["content"]


def test_answer_question_returns_answer_and_sources():
    client = FakeClient("HBM 수요는 강세입니다 [문서 1].")
    docs = [{"title": "HBM 리포트", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]
    result = asyncio.run(rag.answer_question(client, "HBM 동향은?", docs))
    assert "강세" in result["answer"]
    assert result["usedDocCount"] == 1
    assert result["sources"][0]["title"] == "HBM 리포트"
    assert result["sources"][0]["index"] == 1
    assert len(client.calls) == 1


def test_answer_question_empty_docs_raises():
    with pytest.raises(ValueError):
        asyncio.run(rag.answer_question(FakeClient(""), "q", []))


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_rag_query_endpoint(client, monkeypatch):
    _upload(client, "hbm.txt", "HBM4 채택 공식화. AI 가속기 수요 강세.", "HBM")
    monkeypatch.setattr(
        main, "get_client", lambda profile=None: FakeClient("HBM4 채택이 공식화됐습니다 [문서 1].")
    )
    r = client.post("/rag/query", json={"question": "HBM 최근 동향은?"})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "HBM 최근 동향은?"
    assert "공식화" in body["answer"]
    assert body["usedDocCount"] == 1
    assert len(body["sources"]) == 1


def test_rag_query_no_documents_422(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient("answer"))
    r = client.post("/rag/query", json={"question": "아무거나"})
    assert r.status_code == 422
