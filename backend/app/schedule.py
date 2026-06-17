"""파이프라인 스케줄 설정 — 시각적 cron 설정 + (선택) 앱 내 실행.

UI 에서 주기(매일/매주)·시각·요일을 시각적으로 설정해 DB(단일 행)에 저장한다.
동등한 crontab 라인을 생성해 외부 cron/launchd 로도 쓸 수 있고, 환경변수
MI_SCHEDULER=1 이면 앱 내 백그라운드 루프가 그 시각에 파이프라인을 실행한다.

순수 로직(due_now/next_run/crontab_expr)은 네트워크·시간 의존 없이 테스트한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from . import config

FREQUENCIES = ("daily", "weekly")
# 표시용 요일(월=0 … 일=6) — Python datetime.weekday() 기준
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _conn() -> sqlite3.Connection:
    config.COLLECTION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.COLLECTION_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schedule() -> None:
    """스케줄 단일 행 테이블 생성 + 기본값 시드(멱등)."""
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                enabled     INTEGER NOT NULL DEFAULT 0,
                frequency   TEXT NOT NULL DEFAULT 'daily',
                hour        INTEGER NOT NULL DEFAULT 7,
                minute      INTEGER NOT NULL DEFAULT 0,
                weekday     INTEGER NOT NULL DEFAULT 0,
                digest_limit INTEGER NOT NULL DEFAULT 20,
                last_run_at TEXT
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO schedule (id) VALUES (1)")


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "enabled": bool(r["enabled"]),
        "frequency": r["frequency"],
        "hour": r["hour"],
        "minute": r["minute"],
        "weekday": r["weekday"],
        "digestLimit": r["digest_limit"],
        "lastRunAt": r["last_run_at"],
    }


def get_schedule() -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM schedule WHERE id=1").fetchone()
    return _row(row)


def set_schedule(*, enabled: bool, frequency: str, hour: int, minute: int,
                 weekday: int, digest_limit: int) -> dict[str, Any]:
    if frequency not in FREQUENCIES:
        raise ValueError(f"잘못된 주기: {frequency} (허용: {', '.join(FREQUENCIES)})")
    hour = max(0, min(23, int(hour)))
    minute = max(0, min(59, int(minute)))
    weekday = max(0, min(6, int(weekday)))
    digest_limit = max(1, min(100, int(digest_limit)))
    with _conn() as conn:
        conn.execute(
            "UPDATE schedule SET enabled=?, frequency=?, hour=?, minute=?, weekday=?, digest_limit=? WHERE id=1",
            (1 if enabled else 0, frequency, hour, minute, weekday, digest_limit),
        )
    return get_schedule()


def mark_run(when: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE schedule SET last_run_at=? WHERE id=1", (when,))


def next_run(now: datetime, sched: dict[str, Any]) -> datetime:
    """현재 시각 기준 다음 실행 예정 시각."""
    target = now.replace(hour=sched["hour"], minute=sched["minute"], second=0, microsecond=0)
    if sched["frequency"] == "weekly":
        days = (sched["weekday"] - now.weekday()) % 7
        cand = target + timedelta(days=days)
        if cand <= now:
            cand += timedelta(days=7)
        return cand
    # daily
    return target if target > now else target + timedelta(days=1)


def due_now(now: datetime, sched: dict[str, Any], last_run: datetime | None) -> bool:
    """지금 실행해야 하는가(설정 활성 + 시각 일치 + 같은 날 미실행)."""
    if not sched["enabled"]:
        return False
    if now.hour != sched["hour"] or now.minute != sched["minute"]:
        return False
    if sched["frequency"] == "weekly" and now.weekday() != sched["weekday"]:
        return False
    if last_run and last_run.date() == now.date():
        return False  # 같은 날 중복 실행 방지
    return True


def crontab_expr(sched: dict[str, Any]) -> str:
    """동등한 crontab 식(외부 cron/launchd 용). cron 요일: 0=일 … 6=토."""
    dow = "*" if sched["frequency"] == "daily" else str((sched["weekday"] + 1) % 7)
    return f"{sched['minute']} {sched['hour']} * * {dow}"


def describe(sched: dict[str, Any]) -> str:
    """사람이 읽는 스케줄 설명."""
    t = f"{sched['hour']:02d}:{sched['minute']:02d}"
    if sched["frequency"] == "weekly":
        return f"매주 {WEEKDAY_KO[sched['weekday']]}요일 {t}"
    return f"매일 {t}"
