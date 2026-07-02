"""OpenRouter 재순위(rerank) — 1차 검색 후보를 cross-encoder 로 재채점.

RAG 2단계 검색의 재순위를 LLM 대신 전용 rerank 모델(다국어·한국어: cohere/rerank-v3.5
등)로 수행한다. MI_RERANK_MODEL 가 설정돼 있고 OPENROUTER_API_KEY 가 있으면 활성화되며,
아니면 호출부가 기존 LLM 재순위로 폴백한다.

순수 파싱(_order_from_results)과 네트워크(rerank_documents)를 분리해 테스트한다.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_RERANK_MODEL = "cohere/rerank-v3.5"
_DOC_CHARS = 2000  # 문서당 rerank 입력 길이 제한

_client = None       # 이벤트 루프별 재사용 AsyncClient(keep-alive)
_client_loop = None


def _http():
    """rerank 호출용 AsyncClient — 현재 이벤트 루프에 묶어 재사용한다."""
    global _client, _client_loop
    import asyncio

    import httpx

    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient()
        _client_loop = loop
    return _client


def model() -> str | None:
    return (os.getenv("MI_RERANK_MODEL") or "").strip() or None


def enabled() -> bool:
    """rerank 모델이 지정되고 키가 있으면 활성."""
    return bool(model()) and bool(os.getenv("OPENROUTER_API_KEY"))


def _order_from_results(results: list[dict[str, Any]], n: int) -> list[int]:
    """rerank 응답(results[].index, relevance_score)을 점수 내림차순 인덱스로."""
    valid = [
        r for r in results
        if isinstance(r.get("index"), int) and 0 <= r["index"] < n
    ]
    valid.sort(key=lambda r: r.get("relevance_score", 0.0), reverse=True)
    return [r["index"] for r in valid]


async def rerank_documents(
    question: str,
    docs: list[dict[str, Any]],
    *,
    top_n: int = 6,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """OpenRouter /rerank 로 후보를 재정렬해 상위 top_n 문서를 반환한다.

    HTTP/형식 오류는 예외로 전파(호출부가 폴백 처리).
    """
    from .gateway import DEFAULT_BASE_URL, _custom_headers

    key = os.environ["OPENROUTER_API_KEY"]
    base = (os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    documents = [(d.get("content") or d.get("title") or "")[:_DOC_CHARS] for d in docs]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               **_custom_headers()}
    body = {"model": model(), "query": question, "documents": documents, "top_n": top_n}
    r = await _http().post(f"{base}/rerank", headers=headers, json=body, timeout=timeout)
    r.raise_for_status()
    results = r.json().get("results", [])
    order = _order_from_results(results, len(docs))[:top_n]
    return [docs[i] for i in order]
