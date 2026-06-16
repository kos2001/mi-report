"""임베딩 백엔드 선택·모델명·OpenRouter 응답 파싱 (네트워크 없음)."""

from __future__ import annotations

from app import embeddings


def test_backend_defaults_to_fastembed(monkeypatch):
    monkeypatch.delenv("MI_EMBED_BACKEND", raising=False)
    assert embeddings.backend() == "fastembed"
    monkeypatch.setenv("MI_EMBED_BACKEND", "openrouter")
    assert embeddings.backend() == "openrouter"


def test_model_name_backend_defaults(monkeypatch):
    monkeypatch.delenv("MI_EMBED_MODEL", raising=False)
    monkeypatch.setenv("MI_EMBED_BACKEND", "openrouter")
    assert embeddings.model_name() == "baai/bge-m3"
    monkeypatch.setenv("MI_EMBED_BACKEND", "fastembed")
    assert "MiniLM" in embeddings.model_name()
    monkeypatch.setenv("MI_EMBED_MODEL", "custom/model")
    assert embeddings.model_name() == "custom/model"


def test_active_openrouter_needs_only_key(monkeypatch):
    monkeypatch.setenv("MI_EMBEDDINGS", "1")
    monkeypatch.setenv("MI_EMBED_BACKEND", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert embeddings.active() is False  # 키 없으면 비활성
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert embeddings.active() is True   # 모델 다운로드 불필요


def test_parse_embed_payload_orders_by_index():
    payload = {"data": [{"embedding": [2.0], "index": 1}, {"embedding": [1.0], "index": 0}]}
    assert embeddings._parse_embed_payload(payload) == [[1.0], [2.0]]
