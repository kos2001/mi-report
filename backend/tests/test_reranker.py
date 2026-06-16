"""OpenRouter 재순위 — 활성 조건·결과 정렬 파싱 (네트워크 없음)."""

from __future__ import annotations

from app import reranker


def test_model_and_enabled(monkeypatch):
    monkeypatch.delenv("MI_RERANK_MODEL", raising=False)
    assert reranker.model() is None and reranker.enabled() is False
    monkeypatch.setenv("MI_RERANK_MODEL", "cohere/rerank-v3.5")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert reranker.enabled() is False          # 키 없음
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert reranker.model() == "cohere/rerank-v3.5" and reranker.enabled() is True


def test_order_from_results_sorts_and_filters():
    results = [
        {"index": 2, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.3},
        {"index": 5, "relevance_score": 0.99},  # 범위 밖 → 제외
    ]
    assert reranker._order_from_results(results, n=3) == [2, 0]
