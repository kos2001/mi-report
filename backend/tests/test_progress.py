"""AI 생성 파이프라인 진행 이벤트(progress) 테스트."""

from __future__ import annotations

import asyncio

from app import progress


def test_emit_noop_when_no_callback():
    asyncio.run(progress.emit(None, tool="x", emoji="🛠", label="l", status="running"))  # 예외 없이 통과


def test_emit_calls_callback_with_expected_shape():
    events = []

    async def cb(ev):
        events.append(ev)

    asyncio.run(progress.emit(cb, tool="digest", emoji="📰", label="다이제스트 생성", status="running"))
    assert events == [{
        "type": "progress", "tool": "digest", "emoji": "📰", "label": "다이제스트 생성",
        "status": "running", "toolCallId": "digest",
    }]


def test_track_emits_running_then_completed_around_coro():
    events = []

    async def cb(ev):
        events.append(ev["status"])

    async def work():
        events.append("doing")
        return 42

    result = asyncio.run(progress.track(work(), cb, tool="x", emoji="🛠", label="l"))
    assert result == 42
    assert events == ["running", "doing", "completed"]


def test_track_without_callback_still_returns_result():
    async def work():
        return "ok"

    assert asyncio.run(progress.track(work(), None, tool="x", emoji="🛠", label="l")) == "ok"
