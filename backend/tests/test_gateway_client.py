"""LLM 클라이언트(agno + OpenRouter) 테스트 — 네트워크 없이 검증.

agno Agent 구성을 페이크로 치환해, 메시지→프롬프트 매핑과 OpenAI 호환 응답
래핑, API 키 누락 처리만 단위 검증한다.
"""

from __future__ import annotations

import asyncio

import pytest

from app import gateway


class FakeResp:
    def __init__(self, content: str):
        self.content = content


class FakeAgent:
    """agno Agent 대역 — arun 이 .content 를 가진 응답을 돌려준다."""

    def __init__(self, content: str = "응답"):
        self._content = content
        self.last_prompt: str | None = None

    async def arun(self, prompt: str):
        self.last_prompt = prompt
        return FakeResp(self._content)


def test_chat_wraps_openai_shape(monkeypatch):
    fake = FakeAgent("안녕하세요")
    monkeypatch.setattr(
        gateway.LLMClient, "_build_agent",
        lambda self, model, temperature, instructions: fake,
    )
    c = gateway.LLMClient()
    out = asyncio.run(c.chat(
        [{"role": "system", "content": "시스템"}, {"role": "user", "content": "질문입니다"}],
        temperature=0.2,
    ))
    # OpenAI 호환 형태로 content 추출 가능
    assert out["choices"][0]["message"]["content"] == "안녕하세요"
    # 단일 user 메시지는 그대로 프롬프트가 된다(시스템은 instructions 로 분리)
    assert fake.last_prompt == "질문입니다"


def test_to_prompt_separates_system_and_joins_convo():
    system, prompt = gateway.LLMClient._to_prompt([
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
    ])
    assert system == ["S"]
    assert "U1" in prompt and "A1" in prompt and "U2" in prompt


def test_chat_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    c = gateway.LLMClient()
    with pytest.raises(gateway.LLMError):
        asyncio.run(c.chat([{"role": "user", "content": "x"}]))


def test_custom_headers_from_env(monkeypatch):
    monkeypatch.setenv("LLM_SERVICE_ID", "mi-report-svc")
    monkeypatch.setenv("LLM_USER_ID", "u-123")
    c = gateway.LLMClient()
    assert c.headers == {"x-service-id": "mi-report-svc", "x-user-id": "u-123"}


def test_no_custom_headers_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_SERVICE_ID", raising=False)
    monkeypatch.delenv("LLM_USER_ID", raising=False)
    assert gateway.LLMClient().headers == {}


def test_build_agent_attaches_headers(monkeypatch):
    monkeypatch.setenv("LLM_SERVICE_ID", "svc")
    monkeypatch.setenv("LLM_USER_ID", "user")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    c = gateway.LLMClient()
    agent = c._build_agent(None, 0.2, [])
    # 사내 식별 헤더가 OpenRouter 모델의 default_headers 로 전달된다.
    assert agent.model.default_headers == {"x-service-id": "svc", "x-user-id": "user"}
