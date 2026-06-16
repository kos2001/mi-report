"""문서 Q&A 골든 평가셋 저장소(DB).

평가용 골든 Q&A(질문 → 근거 문서 라벨·정답 키워드, 또는 거부형)를 DB 에 영속해
런타임에 추가·조회·삭제할 수 있게 한다. 코드 기본 셋(tests/eval_data)을 최초 1회
시드하고, 이후엔 API 로 질문을 늘려갈 수 있다(평가셋 자산화).

수집과 동일한 SQLite 파일을 쓰되 모듈은 분리한다(자체 _now/_conn).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from . import config

KINDS = ("answerable", "negative")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _conn() -> sqlite3.Connection:
    config.COLLECTION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.COLLECTION_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_qa_golden() -> None:
    """골든 Q&A 테이블 생성(멱등)."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS qa_golden (
                id           TEXT PRIMARY KEY,
                question     TEXT NOT NULL,
                kind         TEXT NOT NULL,
                expected_ids TEXT NOT NULL,   -- JSON: 근거 문서 라벨 목록
                keywords     TEXT NOT NULL,   -- JSON: 정답 키워드 목록
                note         TEXT,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_qa_golden_kind ON qa_golden(kind, created_at DESC);
            """
        )


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "question": r["question"],
        "kind": r["kind"],
        "expectedIds": json.loads(r["expected_ids"]),
        "keywords": json.loads(r["keywords"]),
        "note": r["note"] or "",
        "createdAt": r["created_at"],
    }


def add_qa(question: str, *, kind: str = "answerable",
           expected_ids: list[str] | None = None, keywords: list[str] | None = None,
           note: str = "") -> dict[str, Any]:
    if not question.strip():
        raise ValueError("질문은 필수입니다.")
    if kind not in KINDS:
        raise ValueError(f"잘못된 kind: {kind} (허용: {', '.join(KINDS)})")
    qid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO qa_golden (id, question, kind, expected_ids, keywords, note, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (qid, question.strip(), kind,
             json.dumps(expected_ids or [], ensure_ascii=False),
             json.dumps(keywords or [], ensure_ascii=False), note, _now()),
        )
        row = conn.execute("SELECT * FROM qa_golden WHERE id=?", (qid,)).fetchone()
    return _row(row)


def list_qa(kind: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    sql = "SELECT * FROM qa_golden WHERE 1=1"
    params: list[Any] = []
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row(r) for r in rows]


def delete_qa(qid: str) -> None:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM qa_golden WHERE id=?", (qid,))
        if cur.rowcount == 0:
            raise KeyError(qid)


def count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM qa_golden").fetchone()["n"]


def seed_defaults() -> int:
    """비어 있으면 코드 기본 셋(tests/eval_data)을 시드한다. 추가된 건수 반환."""
    if count() > 0:
        return 0
    try:
        from tests.eval_data import QA_NEGATIVES, QA_QUERIES
    except Exception:
        return 0
    n = 0
    for q, exp, kws in QA_QUERIES:
        add_qa(q, kind="answerable", expected_ids=list(exp), keywords=list(kws))
        n += 1
    for q in QA_NEGATIVES:
        add_qa(q, kind="negative")
        n += 1
    return n
