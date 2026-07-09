"""hermes 에이전트 멀티턴 대화 — /agent/chat 의 백엔드.

gateway.LLMClient(완결형 completion 계약)와 달리, 이 모듈은 hermes profile
'mi-report' 의 OpenAI 호환 api_server 를 **에이전트로** 사용한다:
  - X-Hermes-Session-Id 헤더로 세션을 이어 멀티턴 대화를 유지하고,
  - 에이전트가 스스로 도구(코퍼스 검색 skill·웹 검색 등)를 써서 답한다.

연결 정보는 chat 라우팅과 동일하게 MI_LLM_* 를 쓴다(hermes 전용 기능이라
OPENROUTER_* 폴백은 하지 않는다 — 미설정 시 503 성격의 LLMError).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from . import collection, grounding
from .gateway import LLMError

# 에이전트는 도구(웹 검색·코퍼스 검색)를 쓸 수 있어 완결형 호출보다 오래 걸린다.
AGENT_TIMEOUT = 300.0

_client = None       # 이벤트 루프별 재사용 AsyncClient(keep-alive) — reranker 와 동일 패턴
_client_loop = None


def _http():
    global _client, _client_loop
    import asyncio

    import httpx

    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient()
        _client_loop = loop
    return _client


def _hermes_config() -> tuple[str, str, str]:
    """(base_url, api_key, model) — MI_LLM_* 필수(hermes 전용 기능)."""
    base = (os.getenv("MI_LLM_BASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("MI_LLM_API_KEY") or "").strip()
    model = (os.getenv("MI_LLM_MODEL") or "mi-report").strip()
    if not base or not key:
        raise LLMError(
            503,
            "에이전트 대화는 hermes 연결(MI_LLM_BASE_URL/MI_LLM_API_KEY)이 필요합니다 — "
            "프로파일 .env 를 확인하세요.",
        )
    return base, key, model


def new_session_id() -> str:
    return f"mi-agent-{uuid.uuid4().hex}"


async def chat(message: str, session_id: str | None = None) -> dict[str, Any]:
    """hermes 에이전트에 한 턴을 보내고 {answer, sessionId} 를 반환한다."""
    import httpx

    base, key, model = _hermes_config()
    sid = (session_id or "").strip() or new_session_id()
    if len(sid) > 256:  # hermes api_server 의 세션 헤더 길이 제한과 동일
        raise LLMError(400, "sessionId 가 너무 깁니다(최대 256자).")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Hermes-Session-Id": sid,
    }
    body = {"model": model, "messages": [{"role": "user", "content": message}]}
    try:
        # base 는 OpenAI 호환 루트(…/v1) — 예: http://127.0.0.1:8644/v1
        r = await _http().post(
            f"{base}/chat/completions", headers=headers, json=body,
            timeout=AGENT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise LLMError(502, f"hermes 에이전트 연결 실패: {e}") from e
    if r.status_code >= 400:
        detail: Any
        try:
            detail = r.json().get("error", {}).get("message") or r.text[:300]
        except ValueError:
            detail = r.text[:300]
        raise LLMError(r.status_code, f"hermes 에이전트 오류: {detail}")
    try:
        answer = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMError(502, f"hermes 응답 형식 오류: {r.text[:300]}") from e
    return {"answer": answer, "sessionId": sid}


# 검증용 재검색 폭 — 질문·답변 각각으로 검색해 union 하므로 실질 최대 2×limit.
_GROUND_SEARCH_LIMIT = 8
_GROUND_MAX_CHARS = 8000
_SOURCES_MAX = 6


async def ground_answer(question: str, answer: str) -> dict[str, Any]:
    """에이전트 답변을 코퍼스와 대조해 {수치 검증, 관련 문서} 를 만든다.

    에이전트는 스스로 검색하므로 어떤 문서를 근거로 썼는지 서버가 모른다.
    → 질문·답변 텍스트로 코퍼스를 재검색(결정적 하이브리드)한 문서로:
      - sources: 관련 수집 문서 목록(항상 반환 — 답변 옆에 출처로 표시)
      - 수치 검증: 답변의 수치가 그 본문에 실재하는지 strict(직접 매칭) 대조.
        가수 폴백은 쓰지 않는다 — 문서가 많으면 우연 일치로 무력화되기 때문.
    미근거 수치가 곧 환각은 아니다(웹 출처일 수 있음) — UI 는
    '수집 문서에서 미확인'으로 표기한다.
    """

    def _gather_docs() -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for query in (question, answer[:600]):
            docs = collection.documents_for_rag(
                query, limit=_GROUND_SEARCH_LIMIT, max_chars=_GROUND_MAX_CHARS,
            )
            for d in docs:
                seen.setdefault(d["id"], d)  # 질문 기준 검색 결과를 우선 유지
        return list(seen.values())

    docs = await asyncio.to_thread(_gather_docs)
    sources = [
        {"title": d.get("title", ""), "source": d.get("source", ""),
         "publishedAt": d.get("publishedAt")}
        for d in docs[:_SOURCES_MAX]
    ]
    if grounding.extract_numbers(answer):
        g = grounding.check(
            answer, [d.get("content", "") for d in docs], mantissa_fallback=False,
        )
    else:
        g = {"numbersGrounded": True, "ungroundedNumbers": []}
    return {**g, "sources": sources}
