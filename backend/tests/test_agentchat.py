"""hermes 에이전트 대화(agentchat) + /agent/chat·/rag/search 엔드포인트 테스트.

네트워크 없이: httpx 호출은 페이크 클라이언트로 치환한다.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app import agentchat
from app.gateway import LLMError


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeHttp:
    """httpx.AsyncClient 대역 — 마지막 요청을 기록하고 준비된 응답을 돌려준다."""

    def __init__(self, response: FakeResponse):
        self._response = response
        self.last: dict | None = None

    async def post(self, url, *, headers=None, json=None, timeout=None):
        self.last = {"url": url, "headers": headers, "json": json, "timeout": timeout}
        return self._response


def _ok_response(content: str = "에이전트 답변") -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})


@pytest.fixture
def hermes_env(monkeypatch):
    monkeypatch.setenv("MI_LLM_BASE_URL", "http://127.0.0.1:8644/v1")
    monkeypatch.setenv("MI_LLM_API_KEY", "test-token")
    monkeypatch.setenv("MI_LLM_MODEL", "mi-report")


def test_chat_sends_session_header_and_returns_answer(monkeypatch, hermes_env):
    fake = FakeHttp(_ok_response("안녕하세요"))
    monkeypatch.setattr(agentchat, "_http", lambda: fake)
    out = asyncio.run(agentchat.chat("질문", "sess-1"))
    assert out == {"answer": "안녕하세요", "sessionId": "sess-1"}
    assert fake.last["url"] == "http://127.0.0.1:8644/v1/chat/completions"
    assert fake.last["headers"]["X-Hermes-Session-Id"] == "sess-1"
    assert fake.last["headers"]["Authorization"] == "Bearer test-token"
    assert fake.last["json"]["model"] == "mi-report"


def test_chat_generates_session_id_when_absent(monkeypatch, hermes_env):
    fake = FakeHttp(_ok_response())
    monkeypatch.setattr(agentchat, "_http", lambda: fake)
    out = asyncio.run(agentchat.chat("질문"))
    sid = out["sessionId"]
    assert sid.startswith("mi-agent-") and len(sid) <= 256
    assert fake.last["headers"]["X-Hermes-Session-Id"] == sid


def test_chat_requires_hermes_config(monkeypatch):
    monkeypatch.delenv("MI_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("MI_LLM_API_KEY", raising=False)
    with pytest.raises(LLMError) as e:
        asyncio.run(agentchat.chat("질문"))
    assert e.value.status == 503


def test_chat_surfaces_hermes_error_status(monkeypatch, hermes_env):
    fake = FakeHttp(FakeResponse(401, {"error": {"message": "Invalid API key"}}))
    monkeypatch.setattr(agentchat, "_http", lambda: fake)
    with pytest.raises(LLMError) as e:
        asyncio.run(agentchat.chat("질문"))
    assert e.value.status == 401
    assert "Invalid API key" in str(e.value.detail)


def test_chat_rejects_oversized_session_id(hermes_env):
    with pytest.raises(LLMError) as e:
        asyncio.run(agentchat.chat("질문", "x" * 300))
    assert e.value.status == 400


# ── 답변 수치 grounding (환각 방어) + 관련 문서(sources) ──────────────────

_CORPUS = [{
    "id": "d1", "title": "HBM4 메모", "source": "Confluence", "publishedAt": "2026-06-14",
    "content": "HBM4 양산 목표는 2027년 상반기, 수요는 35% 증가.",
}]


def test_ground_answer_checks_numbers_and_returns_sources(monkeypatch):
    monkeypatch.setattr(
        agentchat.collection, "documents_for_rag", lambda q, **k: _CORPUS
    )
    ok = asyncio.run(agentchat.ground_answer("질문", "양산은 2027년, 수요 35% 증가 전망."))
    assert ok["numbersGrounded"] is True
    assert ok["sources"] == [
        {"title": "HBM4 메모", "source": "Confluence", "publishedAt": "2026-06-14"}
    ]

    bad = asyncio.run(agentchat.ground_answer("질문", "수요는 87% 증가 전망."))
    assert bad["numbersGrounded"] is False
    assert any("87" in n for n in bad["ungroundedNumbers"])


def test_ground_answer_strict_no_mantissa_coincidence(monkeypatch):
    """가수 우연 일치(2.07 ≈ 2,076,000)가 미근거 수치를 통과시키면 안 된다."""
    corpus = [{"id": "d1", "title": "t", "source": "s", "publishedAt": None,
               "content": "성장률 2.07배, 점유율 5.7%."}]
    monkeypatch.setattr(
        agentchat.collection, "documents_for_rag", lambda q, **k: corpus
    )
    out = asyncio.run(agentchat.ground_answer("질문", "종가는 2,076,000원."))
    assert out["numbersGrounded"] is False
    assert "2076000" in out["ungroundedNumbers"]


def test_ground_answer_no_numbers_still_returns_sources(monkeypatch):
    monkeypatch.setattr(
        agentchat.collection, "documents_for_rag", lambda q, **k: _CORPUS
    )
    out = asyncio.run(agentchat.ground_answer("질문", "수치가 없는 답변입니다."))
    assert out["numbersGrounded"] is True and out["ungroundedNumbers"] == []
    assert len(out["sources"]) == 1


# ── 엔드포인트 (TestClient) ────────────────────────────────────────────────

def _fake_chat(monkeypatch):
    async def fake(message, session_id=None, user_id=None):
        return {"answer": f"echo:{message}", "sessionId": session_id or agentchat.new_session_id()}

    monkeypatch.setattr(agentchat, "chat", fake)


def test_agent_chat_endpoint(client, monkeypatch):
    _fake_chat(monkeypatch)
    r = client.post("/agent/chat", json={"message": "안녕", "userId": "user-a"})
    assert r.status_code == 200
    body = r.json()
    sid = body.pop("sessionId")
    assert sid.startswith("mi-agent-")
    # 수치 없는 답변 → grounded 통과, 빈 코퍼스 → sources 없음
    assert body == {
        "answer": "echo:안녕",
        "numbersGrounded": True, "ungroundedNumbers": [], "sources": [],
    }


def test_agent_chat_endpoint_maps_llm_error(client, monkeypatch):
    async def fail_chat(message, session_id=None, user_id=None):
        raise LLMError(503, "hermes 미설정")

    monkeypatch.setattr(agentchat, "chat", fail_chat)
    r = client.post("/agent/chat", json={"message": "안녕", "userId": "user-a"})
    assert r.status_code == 503


def test_agent_chat_requires_user_id(client):
    r = client.post("/agent/chat", json={"message": "안녕"})
    assert r.status_code == 422


# ── 세션 관리 (멀티유저) ───────────────────────────────────────────────────

def test_session_persist_list_resume_and_isolation(client, monkeypatch):
    _fake_chat(monkeypatch)
    # user-a: 두 턴(같은 세션) — 저장·재개
    r1 = client.post("/agent/chat", json={"message": "첫 질문", "userId": "user-a"})
    sid = r1.json()["sessionId"]
    client.post("/agent/chat", json={"message": "이어서", "sessionId": sid, "userId": "user-a"})

    sessions = client.get("/agent/sessions", params={"userId": "user-a"}).json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["id"] == sid
    assert sessions[0]["title"] == "첫 질문"
    assert sessions[0]["messageCount"] == 4  # user/assistant × 2턴

    detail = client.get(f"/agent/sessions/{sid}", params={"userId": "user-a"}).json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["content"] == "echo:첫 질문"
    assert detail["messages"][1]["numbersGrounded"] is True  # meta 언팩

    # user-b 는 user-a 의 세션을 볼 수도, 이어쓸 수도 없다(404)
    assert client.get(f"/agent/sessions/{sid}", params={"userId": "user-b"}).status_code == 404
    assert client.post(
        "/agent/chat", json={"message": "탈취 시도", "sessionId": sid, "userId": "user-b"}
    ).status_code == 404
    assert client.get("/agent/sessions", params={"userId": "user-b"}).json()["sessions"] == []


def test_session_delete(client, monkeypatch):
    _fake_chat(monkeypatch)
    sid = client.post(
        "/agent/chat", json={"message": "삭제될 대화", "userId": "user-a"}
    ).json()["sessionId"]
    assert client.delete(f"/agent/sessions/{sid}", params={"userId": "user-b"}).status_code == 404
    assert client.delete(f"/agent/sessions/{sid}", params={"userId": "user-a"}).status_code == 204
    assert client.get(f"/agent/sessions/{sid}", params={"userId": "user-a"}).status_code == 404


def test_sessions_rejects_bad_user_id(client):
    assert client.get("/agent/sessions", params={"userId": "한글불가"}).status_code == 400


# ── 다이제스트 에이전트 코멘트 ─────────────────────────────────────────────

def test_digest_agent_comment(client, monkeypatch):
    captured: dict = {}

    async def fake_chat(message, session_id=None, user_id=None):
        captured["message"] = message
        return {"answer": "초안 코멘트입니다.", "sessionId": agentchat.new_session_id()}

    monkeypatch.setattr(agentchat, "chat", fake_chat)
    r = client.post("/digest/agent-comment", json={
        "issueNo": 48, "period": "2026.07.06 – 07.09",
        "items": [
            {"title": "HBM4 채택 공식화", "summary": "양산 2027년 상반기", "impact": "high"},
            {"title": "스마트폰 출하 하향", "summary": "", "impact": "medium"},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "초안 코멘트입니다."
    assert body["numbersGrounded"] is True and body["sources"] == []
    # 프롬프트에 호수·항목 제목·요약이 들어간다
    assert "제48호" in captured["message"]
    assert "HBM4 채택 공식화" in captured["message"]
    assert "양산 2027년 상반기" in captured["message"]
    # 다이제스트 코멘트는 일회성 — 대화 세션으로 저장되지 않는다
    with agentchat.db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM agent_sessions").fetchone()["n"]
    assert n == 0


def test_digest_agent_comment_requires_items(client):
    r = client.post("/digest/agent-comment", json={"issueNo": 1, "items": []})
    assert r.status_code == 422


def test_rag_search_endpoint_empty_corpus(client):
    r = client.post("/rag/search", json={"query": "HBM4"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "HBM4"
    assert body["count"] == 0 and body["docs"] == []
