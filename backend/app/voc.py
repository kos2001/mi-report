"""VOC(Voice of Customer) 저장소.

고객/현장의 목소리(요청·불만·문의·피드백)를 기록·추적한다. 영업·CS·뉴스·리포트 등
다양한 채널에서 들어온 VOC 를 한 곳에 모아 감정·우선순위·처리상태로 관리한다.

수집과 동일한 SQLite 파일(config.COLLECTION_DB)을 쓰되 모듈은 분리한다(자체 _now/_conn).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from . import config

CHANNELS = ("영업", "CS", "고객사", "뉴스", "리포트", "기타")
SENTIMENTS = ("긍정", "중립", "부정")
PRIORITIES = ("상", "중", "하")
STATUSES = ("신규", "검토중", "완료")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _conn() -> sqlite3.Connection:
    config.COLLECTION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.COLLECTION_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_voc() -> None:
    """VOC 테이블 생성(멱등)."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS voc (
                id         TEXT PRIMARY KEY,
                customer   TEXT NOT NULL,
                channel    TEXT NOT NULL,
                content    TEXT NOT NULL,
                sentiment  TEXT NOT NULL,
                priority   TEXT NOT NULL,
                status     TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_voc_status ON voc(status, created_at DESC);
            """
        )


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "customer": r["customer"],
        "channel": r["channel"],
        "content": r["content"],
        "sentiment": r["sentiment"],
        "priority": r["priority"],
        "status": r["status"],
        "createdAt": r["created_at"],
    }


def add_voc(customer: str, content: str, *, channel: str = "기타",
            sentiment: str = "중립", priority: str = "중") -> dict[str, Any]:
    """VOC 항목을 추가한다. 채널/감정/우선순위는 허용값으로 보정한다."""
    if not customer.strip() or not content.strip():
        raise ValueError("고객명과 내용은 필수입니다.")
    channel = channel if channel in CHANNELS else "기타"
    sentiment = sentiment if sentiment in SENTIMENTS else "중립"
    priority = priority if priority in PRIORITIES else "중"
    vid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO voc (id, customer, channel, content, sentiment, priority, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (vid, customer.strip(), channel, content.strip(), sentiment, priority, "신규", _now()),
        )
        row = conn.execute("SELECT * FROM voc WHERE id=?", (vid,)).fetchone()
    return _row(row)


def list_voc(*, status: str | None = None, sentiment: str | None = None,
             limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM voc WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if sentiment:
        sql += " AND sentiment=?"
        params.append(sentiment)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row(r) for r in rows]


def update_status(vid: str, status: str) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"잘못된 상태: {status} (허용: {', '.join(STATUSES)})")
    with _conn() as conn:
        cur = conn.execute("UPDATE voc SET status=? WHERE id=?", (status, vid))
        if cur.rowcount == 0:
            raise KeyError(vid)
        row = conn.execute("SELECT * FROM voc WHERE id=?", (vid,)).fetchone()
    return _row(row)


def delete_voc(vid: str) -> None:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM voc WHERE id=?", (vid,))
        if cur.rowcount == 0:
            raise KeyError(vid)


def voc_summary() -> dict[str, Any]:
    """상태별·감정별 집계."""
    with _conn() as conn:
        st = conn.execute("SELECT status, COUNT(*) AS n FROM voc GROUP BY status").fetchall()
        se = conn.execute("SELECT sentiment, COUNT(*) AS n FROM voc GROUP BY sentiment").fetchall()
        total = conn.execute("SELECT COUNT(*) AS n FROM voc").fetchone()["n"]
    return {
        "total": total,
        "byStatus": {r["status"]: r["n"] for r in st},
        "bySentiment": {r["sentiment"]: r["n"] for r in se},
    }
