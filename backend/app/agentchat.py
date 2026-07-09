"""hermes 에이전트 멀티턴 대화 — /agent/chat 의 백엔드.

gateway.LLMClient(완결형 completion 계약)와 달리, 이 모듈은 hermes profile
'mi-report' 의 OpenAI 호환 api_server 를 **에이전트로** 사용한다:
  - X-Hermes-Session-Id 헤더로 세션을 이어 멀티턴 대화를 유지하고,
  - 에이전트가 스스로 도구(코퍼스 검색 skill·웹 검색 등)를 써서 답한다.

연결 정보는 chat 라우팅과 동일하게 MI_LLM_* 를 쓴다(hermes 전용 기능이라
OPENROUTER_* 폴백은 하지 않는다 — 미설정 시 503 성격의 LLMError).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

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
