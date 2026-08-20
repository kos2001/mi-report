"""지식 자산 + 자기 개선 저장소.

생성물 영속화(지식 자산화): AI 가 생성한 다이제스트·주제 요약·경쟁사 분석·리포트를
시점별로 누적 저장해, 휘발성 출력이 아니라 '쌓이는 자산'이 되게 한다.
피드백(자기 개선): 생성물에 대한 👍/👎·메모를 저장해 이후 품질 개선의 신호로 쓴다.

수집과 동일한 SQLite 파일(config.COLLECTION_DB)을 쓰되 모듈은 분리한다.
순환 import 방지를 위해 collection 에 의존하지 않는다(자체 _now/_conn).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from . import db

ARTIFACT_KINDS = ("digest", "topic", "competitor", "report")
RATINGS = ("up", "down")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _conn() -> sqlite3.Connection:
    return db.connect()  # 스레드별 재사용 커넥션(호출마다 connect+PRAGMA 제거)


def init_assets() -> None:
    """생성물·피드백 테이블 생성(멱등)."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id         TEXT PRIMARY KEY,
                kind       TEXT NOT NULL,
                title      TEXT NOT NULL,
                ref        TEXT,
                payload    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(kind, created_at DESC);
            CREATE TABLE IF NOT EXISTS feedback (
                id         TEXT PRIMARY KEY,
                kind       TEXT NOT NULL,
                ref        TEXT,
                rating     TEXT NOT NULL,
                note       TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_feedback_kind ON feedback(kind, created_at DESC);
            """
        )


def _row_to_artifact(row: sqlite3.Row, *, with_payload: bool) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "ref": row["ref"],
        "createdAt": row["created_at"],
    }
    if with_payload:
        out["payload"] = json.loads(row["payload"])
    return out


def save_artifact(kind: str, title: str, ref: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    """생성물을 저장한다(시점별 누적). 같은 ref 라도 새 버전으로 쌓인다."""
    aid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO artifacts (id, kind, title, ref, payload, created_at) VALUES (?,?,?,?,?,?)",
            (aid, kind, title, ref, json.dumps(payload, ensure_ascii=False), _now()),
        )
        row = conn.execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()
    return _row_to_artifact(row, with_payload=False)


def save_artifact_safe(kind: str, title: str, ref: str | None, payload: dict[str, Any]) -> None:
    """저장 실패가 생성 흐름을 막지 않도록 감싼 버전(엔드포인트 자동 저장용)."""
    try:
        save_artifact(kind, title, ref, payload)
    except Exception:
        pass


def list_artifacts(kind: str | None = None, ref: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT id, kind, title, ref, created_at FROM artifacts WHERE 1=1"
    params: list[Any] = []
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    if ref:
        sql += " AND ref=?"
        params.append(ref)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_artifact(r, with_payload=False) for r in rows]


def get_artifact(aid: str) -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()
    if row is None:
        raise KeyError(aid)
    return _row_to_artifact(row, with_payload=True)


def delete_artifact(aid: str) -> None:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM artifacts WHERE id=?", (aid,))
        if cur.rowcount == 0:
            raise KeyError(aid)


def count_artifacts() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM artifacts").fetchone()["n"]


def add_feedback(kind: str, ref: str | None, rating: str, note: str = "") -> dict[str, Any]:
    if rating not in RATINGS:
        raise ValueError(f"잘못된 rating: {rating} (허용: {', '.join(RATINGS)})")
    fid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO feedback (id, kind, ref, rating, note, created_at) VALUES (?,?,?,?,?,?)",
            (fid, kind, ref, rating, note, _now()),
        )
        row = conn.execute("SELECT * FROM feedback WHERE id=?", (fid,)).fetchone()
    return {
        "id": row["id"], "kind": row["kind"], "ref": row["ref"],
        "rating": row["rating"], "note": row["note"], "createdAt": row["created_at"],
    }


def feedback_summary() -> dict[str, Any]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT rating, COUNT(*) AS n FROM feedback GROUP BY rating"
        ).fetchall()
    counts = {r["rating"]: r["n"] for r in rows}
    return {"up": counts.get("up", 0), "down": counts.get("down", 0)}
