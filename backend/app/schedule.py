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

from . import db

FREQUENCIES = ("daily", "weekly")
MAX_AUTO_RETRIES = 3  # 자동 실행 실패 시 하루 안에서 재시도할 최대 횟수
# 표시용 요일(월=0 … 일=6) — Python datetime.weekday() 기준
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _conn() -> sqlite3.Connection:
    return db.connect()  # 스레드별 재사용 커넥션(호출마다 connect+PRAGMA 제거)


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
                last_run_at TEXT,
                retry_enabled INTEGER NOT NULL DEFAULT 0,
                retry_minutes INTEGER NOT NULL DEFAULT 10
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO schedule (id) VALUES (1)")
        # 기존 DB(컬럼 추가 전 생성)에도 새 컬럼을 얹는다 — CREATE TABLE IF NOT EXISTS 는
        # 이미 있는 테이블의 스키마를 바꾸지 않으므로 ALTER 로 별도 보정.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(schedule)").fetchall()}
        if "retry_enabled" not in cols:
            conn.execute("ALTER TABLE schedule ADD COLUMN retry_enabled INTEGER NOT NULL DEFAULT 0")
        if "retry_minutes" not in cols:
            conn.execute("ALTER TABLE schedule ADD COLUMN retry_minutes INTEGER NOT NULL DEFAULT 10")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_run_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at   TEXT NOT NULL,
                trigger  TEXT NOT NULL,
                status   TEXT NOT NULL,
                error    TEXT,
                ingested INTEGER
            )
            """
        )


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "enabled": bool(r["enabled"]),
        "frequency": r["frequency"],
        "hour": r["hour"],
        "minute": r["minute"],
        "weekday": r["weekday"],
        "digestLimit": r["digest_limit"],
        "lastRunAt": r["last_run_at"],
        "retryEnabled": bool(r["retry_enabled"]),
        "retryMinutes": r["retry_minutes"],
    }


def get_schedule() -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM schedule WHERE id=1").fetchone()
    return _row(row)


def set_schedule(*, enabled: bool, frequency: str, hour: int, minute: int,
                 weekday: int, digest_limit: int,
                 retry_enabled: bool = False, retry_minutes: int = 10) -> dict[str, Any]:
    if frequency not in FREQUENCIES:
        raise ValueError(f"잘못된 주기: {frequency} (허용: {', '.join(FREQUENCIES)})")
    hour = max(0, min(23, int(hour)))
    minute = max(0, min(59, int(minute)))
    weekday = max(0, min(6, int(weekday)))
    digest_limit = max(1, min(100, int(digest_limit)))
    retry_minutes = max(1, min(120, int(retry_minutes)))
    with _conn() as conn:
        conn.execute(
            "UPDATE schedule SET enabled=?, frequency=?, hour=?, minute=?, weekday=?, digest_limit=?, "
            "retry_enabled=?, retry_minutes=? WHERE id=1",
            (1 if enabled else 0, frequency, hour, minute, weekday, digest_limit,
             1 if retry_enabled else 0, retry_minutes),
        )
    return get_schedule()


def mark_run(when: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE schedule SET last_run_at=? WHERE id=1", (when,))


def log_run(*, trigger: str, status: str, error: str | None = None,
            ingested: int | None = None) -> None:
    """실행 시도 결과(자동/수동, 성공/실패) 기록."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO schedule_run_log (ran_at, trigger, status, error, ingested) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), trigger, status, error, ingested),
        )


def recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    """최근 실행 이력(최신순)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ran_at, trigger, status, error, ingested FROM schedule_run_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "ranAt": r["ran_at"],
            "trigger": r["trigger"],
            "status": r["status"],
            "error": r["error"],
            "ingested": r["ingested"],
        }
        for r in rows
    ]


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


def retry_due(now: datetime, sched: dict[str, Any], runs: list[dict[str, Any]]) -> bool:
    """오늘 자동 실행이 실패했고 재시도 설정이 켜져 있으면, 재시도 간격이 지났는지 판정.

    runs 는 recent_runs() 출력(최신순)을 그대로 받는다 — 별도 재시도 카운터를 DB에
    두지 않고 오늘자 auto 로그의 연속 실패 개수로 계산해, 상태를 이중으로 관리하지
    않는다(log_run 이 유일한 진실 원천).
    """
    if not sched["enabled"] or not sched.get("retryEnabled"):
        return False
    today = now.strftime("%Y-%m-%d")
    todays_auto = [r for r in runs if r["trigger"] == "auto" and r["ranAt"].startswith(today)]
    if not todays_auto or todays_auto[0]["status"] != "failure":
        return False
    fail_count = 0
    for r in todays_auto:
        if r["status"] != "failure":
            break
        fail_count += 1
    if fail_count >= MAX_AUTO_RETRIES:
        return False
    last_at = datetime.strptime(todays_auto[0]["ranAt"], "%Y-%m-%d %H:%M:%S")
    retry_minutes = sched.get("retryMinutes", 10)
    return now.replace(tzinfo=None) >= last_at + timedelta(minutes=retry_minutes)


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
