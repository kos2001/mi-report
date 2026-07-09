"""hermes 에이전트 멀티턴 대화 — /agent/chat 의 백엔드.

gateway.LLMClient(완결형 completion 계약)와 달리, 이 모듈은 hermes profile
'mi-report' 의 OpenAI 호환 api_server 를 **에이전트로** 사용한다:
  - X-Hermes-Session-Id 헤더로 세션을 이어 멀티턴 대화를 유지하고,
  - X-Hermes-Session-Key 로 사용자별 장기 메모리 스코프를 분리하고,
  - 에이전트가 스스로 도구(코퍼스 검색 skill·웹 검색 등)를 써서 답한다.

멀티유저: 세션·메시지를 SQLite(collection.db)에 영속화한다. 세션은 userId 에
귀속되며, 목록/재개/삭제는 소유자만 가능하다(다른 userId 에는 404).

연결 정보는 chat 라우팅과 동일하게 MI_LLM_* 를 쓴다(hermes 전용 기능이라
OPENROUTER_* 폴백은 하지 않는다 — 미설정 시 503 성격의 LLMError).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import collection, db, grounding
from .gateway import LLMError

USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TITLE_CHARS = 60

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


async def chat(message: str, session_id: str | None = None,
               user_id: str | None = None) -> dict[str, Any]:
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
    if user_id:  # 사용자별 장기 메모리 스코프 분리(hermes Session-Key)
        headers["X-Hermes-Session-Key"] = f"mi-report:{user_id}"
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


# ── 스트리밍 (진행사항 + 답변 델타) ────────────────────────────────────────

async def parse_sse(lines) -> Any:
    """SSE 라인 스트림 → (event, data) 튜플의 async generator.

    event: 가 없는 data: 는 event=None. 빈 줄이 디스패치 경계, ':' 시작은
    keepalive 주석. data: [DONE] 은 (None, "[DONE]") 로 그대로 넘긴다.
    """
    event: str | None = None
    async for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            event = None  # 이벤트 경계
            continue
        if line.startswith(":"):
            continue  # keepalive
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            yield event, line[len("data:"):].strip()


async def stream_events(message: str, session_id: str | None = None,
                        user_id: str | None = None, *,
                        persist: bool = True) -> Any:
    """hermes 스트리밍 chat 을 이벤트 dict 로 중계하는 async generator.

    산출 이벤트:
      {"type": "progress", "tool", "emoji"?, "label"?, "status"}  도구 진행사항
      {"type": "delta", "text"}                                    답변 토큰
      {"type": "done", "answer", "sessionId", numbersGrounded, ungroundedNumbers, sources}
    오류는 LLMError 로 raise(호출부가 SSE error 이벤트로 변환).
    """
    base, key, model = _hermes_config()
    sid = (session_id or "").strip() or new_session_id()
    if len(sid) > 256:
        raise LLMError(400, "sessionId 가 너무 깁니다(최대 256자).")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Hermes-Session-Id": sid,
    }
    if user_id:
        headers["X-Hermes-Session-Key"] = f"mi-report:{user_id}"
    body = {"model": model, "stream": True,
            "messages": [{"role": "user", "content": message}]}

    import httpx

    parts: list[str] = []
    try:
        async with _http().stream(
            "POST", f"{base}/chat/completions", headers=headers, json=body,
            timeout=AGENT_TIMEOUT,
        ) as r:
            if r.status_code >= 400:
                detail = (await r.aread()).decode("utf-8", "replace")[:300]
                try:
                    detail = json.loads(detail).get("error", {}).get("message") or detail
                except ValueError:
                    pass
                raise LLMError(r.status_code, f"hermes 에이전트 오류: {detail}")
            async for event, data in parse_sse(r.aiter_lines()):
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except ValueError:
                    continue
                if event == "hermes.tool.progress":
                    yield {"type": "progress", **payload}
                    continue
                delta = (payload.get("choices") or [{}])[0].get("delta", {})
                text = delta.get("content")
                if text:
                    parts.append(text)
                    yield {"type": "delta", "text": text}
    except httpx.HTTPError as e:
        raise LLMError(502, f"hermes 에이전트 연결 실패: {e}") from e

    answer = "".join(parts)
    if not answer:
        raise LLMError(502, "hermes 에이전트가 빈 응답을 반환했습니다.")
    result: dict[str, Any] = {"answer": answer, "sessionId": sid}
    result.update(await ground_answer(message, answer))
    if persist and user_id:
        await asyncio.to_thread(record_turn, user_id, sid, message, result)
    yield {"type": "done", **result}


# ── 다이제스트 초안 에이전트 코멘트 ────────────────────────────────────────

_COMMENT_SUMMARY_CHARS = 300


def digest_comment_prompt(issue_no: int, period: str,
                          items: list[dict[str, Any]]) -> str:
    lines = [
        f"- (영향도 {it.get('impact') or '?'}) {it.get('title', '')}: "
        f"{(it.get('summary') or '')[:_COMMENT_SUMMARY_CHARS]}"
        for it in items
    ]
    return (
        "다음은 발송 전 검토 단계의 주간 뉴스 다이제스트 초안이다. "
        "MI 애널리스트 관점의 에이전트 코멘트를 작성하라.\n"
        "코퍼스 검색(필요시 웹 검색 병행)으로 근거를 확인해서 간결하게:\n"
        "1) 항목별 타당성과 놓친 근거, 2) 초안에 빠진 리스크·시사점, "
        "3) 발송 전 수정 제안.\n"
        "근거 문서·출처는 본문에 인용하라.\n\n"
        f"제{issue_no}호 {period}\n" + "\n".join(lines)
    )


async def digest_comment(issue_no: int, period: str,
                         items: list[dict[str, Any]]) -> dict[str, Any]:
    """다이제스트 초안에 대한 에이전트 코멘트(일회성 — 세션 저장 안 함).

    에이전트가 코퍼스·웹을 검색해 초안의 타당성 검토, 근거 보강, 놓친
    리스크/시사점을 코멘트로 작성한다. 답변 수치는 코퍼스 대조로 검증한다.
    """
    message = digest_comment_prompt(issue_no, period, items)
    result = await chat(message)  # 매번 새 세션(일회성 코멘트)
    result.update(await ground_answer(message, result["answer"]))
    return result


# ── 세션 영속화 (멀티유저) ─────────────────────────────────────────────────

def init_db() -> None:
    """에이전트 세션/메시지 테이블 생성(collection.db 공유)."""
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                id         TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_sessions_user
                ON agent_sessions(user_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS agent_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                meta       TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_messages_session
                ON agent_messages(session_id, id);
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_valid_user_id(user_id: object) -> bool:
    return isinstance(user_id, str) and bool(USER_ID_RE.match(user_id))


def get_session(session_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM agent_sessions WHERE id=?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    """사용자의 세션 목록(최근 대화 순, 메시지 수 포함)."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM agent_sessions s
            LEFT JOIN agent_messages m ON m.session_id = s.id
            WHERE s.user_id=?
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [
        {"id": r["id"], "title": r["title"], "createdAt": r["created_at"],
         "updatedAt": r["updated_at"], "messageCount": r["message_count"]}
        for r in rows
    ]


def session_messages(session_id: str) -> list[dict[str, Any]]:
    """세션의 메시지들(시간순) — assistant 메시지는 meta(검증/출처)를 풀어 반환."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT role, content, meta, created_at FROM agent_messages "
            "WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            meta = json.loads(r["meta"])
        except ValueError:
            meta = {}
        out.append({"role": r["role"], "content": r["content"],
                    "createdAt": r["created_at"], **meta})
    return out


def record_turn(user_id: str, session_id: str, question: str,
                result: dict[str, Any]) -> None:
    """한 턴(user 질문 + assistant 답변)을 저장한다. 새 세션이면 생성."""
    now = _now()
    meta = json.dumps(
        {k: result[k] for k in ("numbersGrounded", "ungroundedNumbers", "sources")
         if k in result},
        ensure_ascii=False,
    )
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO agent_sessions (id, user_id, title, created_at, updated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, user_id, question[:_TITLE_CHARS], now, now),
        )
        conn.execute(
            "INSERT INTO agent_messages (session_id, role, content, meta, created_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, "user", question, "{}", now),
        )
        conn.execute(
            "INSERT INTO agent_messages (session_id, role, content, meta, created_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, "assistant", result.get("answer", ""), meta, now),
        )


def delete_session(session_id: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM agent_sessions WHERE id=?", (session_id,))
