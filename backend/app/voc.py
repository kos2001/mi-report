"""VOC(Voice of Customer) 저장소 — 이 서비스(MI Report)에 대한 사용자 의견.

대시보드·수집·다이제스트·Q&A·리포트 등 각 기능 영역에 대한 사용자의 의견·요청·버그·
개선 제안을 기록·추적한다(제품 피드백). 감정·우선순위·유형·처리상태로 관리한다.

수집과 동일한 SQLite 파일(config.COLLECTION_DB)을 쓰되 모듈은 분리한다(자체 _now/_conn).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from . import db

# 이 서비스의 기능 영역(피드백 대상)
CHANNELS = ("대시보드", "데이터수집", "다이제스트", "주제", "경쟁사", "문서Q&A", "리포트", "기타")
# 피드백 유형
CATEGORIES = ("기능요청", "버그", "개선", "문의", "칭찬")
SENTIMENTS = ("긍정", "중립", "부정")
PRIORITIES = ("상", "중", "하")
STATUSES = ("신규", "검토중", "완료")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _conn() -> sqlite3.Connection:
    return db.connect()  # 스레드별 재사용 커넥션(호출마다 connect+PRAGMA 제거)


def init_voc() -> None:
    """VOC 테이블 생성(멱등) + 기존 DB 컬럼 마이그레이션."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS voc (
                id         TEXT PRIMARY KEY,
                customer   TEXT NOT NULL,            -- 작성자(사용자)
                channel    TEXT NOT NULL,            -- 기능 영역
                category   TEXT NOT NULL DEFAULT '문의',  -- 유형(기능요청/버그/개선/문의/칭찬)
                content    TEXT NOT NULL,
                sentiment  TEXT NOT NULL,
                priority   TEXT NOT NULL,
                status     TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_voc_status ON voc(status, created_at DESC);
            """
        )
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(voc)").fetchall()}
        if "category" not in cols:
            conn.execute("ALTER TABLE voc ADD COLUMN category TEXT NOT NULL DEFAULT '문의'")


def _row(r: sqlite3.Row) -> dict[str, Any]:
    keys = r.keys()
    return {
        "id": r["id"],
        "reporter": r["customer"],            # 작성자(컬럼명 customer 유지, 의미는 작성자)
        "area": r["channel"],                 # 기능 영역(컬럼명 channel 유지)
        "category": r["category"] if "category" in keys else "문의",
        "content": r["content"],
        "sentiment": r["sentiment"],
        "priority": r["priority"],
        "status": r["status"],
        "createdAt": r["created_at"],
    }


def add_voc(reporter: str, content: str, *, area: str = "기타", category: str = "문의",
            sentiment: str = "중립", priority: str = "중") -> dict[str, Any]:
    """VOC(서비스 피드백) 항목을 추가한다. 영역/유형/감정/우선순위는 허용값으로 보정한다."""
    if not reporter.strip() or not content.strip():
        raise ValueError("작성자와 내용은 필수입니다.")
    area = area if area in CHANNELS else "기타"
    category = category if category in CATEGORIES else "문의"
    sentiment = sentiment if sentiment in SENTIMENTS else "중립"
    priority = priority if priority in PRIORITIES else "중"
    vid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO voc (id, customer, channel, category, content, sentiment, priority, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (vid, reporter.strip(), area, category, content.strip(), sentiment, priority, "신규", _now()),
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
