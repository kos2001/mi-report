"""게이트웨이 클라이언트의 URL/헤더 구성 테스트 (네트워크 없음)."""

from __future__ import annotations

from pathlib import Path

from app.gateway import HermesGatewayClient
from app.profiles import Profile, ProviderConfig


def _fake_profile() -> Profile:
    provider = ProviderConfig(
        name="hermes-gateway",
        type="openai-compatible",
        base_url="http://127.0.0.1:8642/v1",
        key_env="HERMES_GATEWAY_API_KEY",
        extra_headers={"X-Test": "1"},
    )
    return Profile(
        name="test", path=Path("/tmp/test"), model="hermes-agent",
        provider_name="hermes-gateway", base_url="http://127.0.0.1:8642/v1",
        providers={"hermes-gateway": provider}, has_env=True, has_soul=False,
    )


def test_url_building_for_v1_and_api_paths():
    c = HermesGatewayClient(_fake_profile())
    assert c._url("/v1/chat/completions") == "http://127.0.0.1:8642/v1/chat/completions"
    assert c._url("/v1/runs") == "http://127.0.0.1:8642/v1/runs"
    assert c._url("/api/sessions") == "http://127.0.0.1:8642/api/sessions"
    assert c._url("/health") == "http://127.0.0.1:8642/health"


def test_headers_include_bearer_and_session(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_API_KEY", "test-token-123")
    c = HermesGatewayClient(_fake_profile())
    h = c._headers(session_id="sess-1", session_key="key-1")
    assert h["Authorization"] == "Bearer test-token-123"
    assert h["X-Hermes-Session-Id"] == "sess-1"
    assert h["X-Hermes-Session-Key"] == "key-1"
    assert h["X-Test"] == "1"  # provider extra_headers 병합


def test_headers_without_key(monkeypatch):
    monkeypatch.delenv("HERMES_GATEWAY_API_KEY", raising=False)
    c = HermesGatewayClient(_fake_profile())
    h = c._headers()
    assert "Authorization" not in h
