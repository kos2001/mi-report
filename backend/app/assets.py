"""지식 자산 + 자기 개선 저장소.

생성물 영속화(지식 자산화): AI 가 생성한 다이제스트·주제 요약·경쟁사 분석·리포트를
주차별로 저장한다. 같은 종류·대상의 동일 ISO 주차 생성물은 최신 결과로 교체한다.
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
                id               TEXT PRIMARY KEY,
                kind             TEXT NOT NULL,
                title            TEXT NOT NULL,
                ref              TEXT,
                payload          TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                ungrounded_count INTEGER NOT NULL DEFAULT 0,
                unsupported_count INTEGER NOT NULL DEFAULT 0
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
        # 기존 DB(컬럼 추가 전 생성)에도 새 컬럼을 얹는다 — schedule.py 와 같은 관례.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(artifacts)").fetchall()}
        if "ungrounded_count" not in cols:
            conn.execute("ALTER TABLE artifacts ADD COLUMN ungrounded_count INTEGER NOT NULL DEFAULT 0")
        if "unsupported_count" not in cols:
            conn.execute("ALTER TABLE artifacts ADD COLUMN unsupported_count INTEGER NOT NULL DEFAULT 0")


def _row_to_artifact(row: sqlite3.Row, *, with_payload: bool) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "ref": row["ref"],
        "createdAt": row["created_at"],
        "ungroundedCount": row["ungrounded_count"],
        "unsupportedCount": row["unsupported_count"],
    }
    if with_payload:
        out["payload"] = json.loads(row["payload"])
    return out


def _quality_counts(payload: dict[str, Any]) -> tuple[int, int]:
    """생성물의 환각 방어 신호(미근거 수치·근거 없는 서술)를 payload 에서 뽑는다.

    report.py 는 unsupportedClaims 대신 overviewUnsupportedClaims 를 쓰므로 둘 다 본다.
    """
    ungrounded = len(payload.get("ungroundedNumbers") or [])
    unsupported = len(payload.get("unsupportedClaims") or payload.get("overviewUnsupportedClaims") or [])
    return ungrounded, unsupported


def _iso_week(value: str) -> tuple[int, int] | None:
    """저장 시각 문자열을 ISO (연도, 주차)로 변환한다."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    iso = parsed.date().isocalendar()
    return iso.year, iso.week


def save_artifact(kind: str, title: str, ref: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    """생성물을 저장한다.

    같은 종류·ref의 동일 ISO 주차 생성물은 한 건만 유지한다. 새 생성이 성공한 뒤
    한 트랜잭션에서 기존 건을 제거하고 새 결과를 넣으므로, 생성 실패 시 이전 결과는
    보존된다. 다른 주차의 결과는 이력으로 계속 누적된다.
    """
    aid = uuid.uuid4().hex
    ungrounded, unsupported = _quality_counts(payload)
    created_at = _now()
    current_week = _iso_week(created_at)
    with _conn() as conn:
        previous = conn.execute(
            "SELECT id, created_at FROM artifacts WHERE kind=? AND ref IS ?",
            (kind, ref),
        ).fetchall()
        replace_ids = [r["id"] for r in previous if _iso_week(r["created_at"]) == current_week]
        if replace_ids:
            conn.executemany("DELETE FROM artifacts WHERE id=?", [(old_id,) for old_id in replace_ids])
        conn.execute(
            "INSERT INTO artifacts (id, kind, title, ref, payload, created_at, ungrounded_count, unsupported_count) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (aid, kind, title, ref, json.dumps(payload, ensure_ascii=False), created_at, ungrounded, unsupported),
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
    sql = ("SELECT id, kind, title, ref, created_at, ungrounded_count, unsupported_count "
           "FROM artifacts WHERE 1=1")
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


def feedback_summary_by_kind() -> dict[str, dict[str, int]]:
    """종류(다이제스트/주제/경쟁사/리포트)별 👍/👎 집계 — 품질 대시보드용."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT kind, rating, COUNT(*) AS n FROM feedback GROUP BY kind, rating"
        ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["kind"], {"up": 0, "down": 0})[r["rating"]] = r["n"]
    return out


def recent_negative_feedback(kind: str, limit: int = 5) -> list[str]:
    """이 종류의 최근 👎 피드백 메모(빈 메모 제외, 최신순) — 다음 생성 프롬프트에 반영."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT note FROM feedback WHERE kind=? AND rating='down' AND note != '' "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    return [r["note"] for r in rows]


def quality_summary(limit_flagged: int = 10) -> dict[str, Any]:
    """자기개선 loop 대시보드 — 종류별 생성 건수·피드백·근거검증 실패 건수 + 최근 플래그된 생성물."""
    with _conn() as conn:
        counts = conn.execute(
            "SELECT kind, COUNT(*) AS n, "
            "SUM(CASE WHEN ungrounded_count > 0 OR unsupported_count > 0 THEN 1 ELSE 0 END) AS flagged "
            "FROM artifacts GROUP BY kind"
        ).fetchall()
        flagged_rows = conn.execute(
            "SELECT id, kind, title, created_at, ungrounded_count, unsupported_count FROM artifacts "
            "WHERE ungrounded_count > 0 OR unsupported_count > 0 "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit_flagged,),
        ).fetchall()

    fb = feedback_summary_by_kind()
    by_kind: dict[str, Any] = {}
    for r in counts:
        k = r["kind"]
        kind_fb = fb.get(k, {"up": 0, "down": 0})
        by_kind[k] = {
            "count": r["n"], "flaggedCount": r["flagged"] or 0,
            "up": kind_fb["up"], "down": kind_fb["down"],
        }
    for k in ARTIFACT_KINDS:
        by_kind.setdefault(k, {"count": 0, "flaggedCount": 0, "up": 0, "down": 0})

    return {
        "byKind": by_kind,
        "recentFlagged": [
            {
                "id": r["id"], "kind": r["kind"], "title": r["title"], "createdAt": r["created_at"],
                "ungroundedCount": r["ungrounded_count"], "unsupportedCount": r["unsupported_count"],
            }
            for r in flagged_rows
        ],
    }
