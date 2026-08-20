"""AI 생성 파이프라인의 진행 단계(step) 이벤트 — SSE 로 실시간 중계해 사용자가
'지금 뭘 하고 있는지' 보게 한다. agentchat.py 의 도구 진행사항(progress) 이벤트와
같은 모양({type, tool, emoji, label, status, toolCallId})을 써서 프론트엔드가
이미 갖고 있는 AgentProgressView 를 그대로 재사용할 수 있게 한다.

on_progress 는 선택 인자다 — None 이면 무시되고, 기존 비스트리밍 엔드포인트는
전혀 영향받지 않는다.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

ProgressFn = Callable[[dict[str, Any]], Awaitable[None]]

T = TypeVar("T")


async def emit(on_progress: ProgressFn | None, *, tool: str, emoji: str, label: str, status: str) -> None:
    if on_progress is None:
        return
    await on_progress({
        "type": "progress", "tool": tool, "emoji": emoji, "label": label,
        "status": status, "toolCallId": tool,
    })


async def track(
    coro: Awaitable[T], on_progress: ProgressFn | None, *, tool: str, emoji: str, label: str,
) -> T:
    """coro 실행 전후로 running/completed 진행 이벤트를 낸다(동시 실행 태스크에도 쓸 수 있음 —
    각자 자기 시작·완료 시점에 이벤트를 내므로 asyncio.gather 로 묶어도 실제 완료 순서가 그대로 보인다)."""
    await emit(on_progress, tool=tool, emoji=emoji, label=label, status="running")
    result = await coro
    await emit(on_progress, tool=tool, emoji=emoji, label=label, status="completed")
    return result
