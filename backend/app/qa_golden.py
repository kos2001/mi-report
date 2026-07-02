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

from . import db

KINDS = ("answerable", "negative")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _conn() -> sqlite3.Connection:
    return db.connect()  # 스레드별 재사용 커넥션(호출마다 connect+PRAGMA 제거)


def init_qa_golden() -> None:
    """골든 Q&A 테이블 생성(멱등) + 기존 DB 컬럼 마이그레이션."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS qa_golden (
                id           TEXT PRIMARY KEY,
                question     TEXT NOT NULL,
                kind         TEXT NOT NULL,
                expected_ids TEXT NOT NULL,   -- JSON: 근거 문서 라벨 목록
                keywords     TEXT NOT NULL,   -- JSON: 정답(반드시 포함) 키워드/수치
                forbidden    TEXT NOT NULL DEFAULT '[]',  -- JSON: 나오면 안 되는 값(반올림/왜곡/환각)
                note         TEXT,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_qa_golden_kind ON qa_golden(kind, created_at DESC);
            """
        )
        # 기존 테이블에 forbidden 컬럼이 없으면 추가(마이그레이션).
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(qa_golden)").fetchall()}
        if "forbidden" not in cols:
            conn.execute("ALTER TABLE qa_golden ADD COLUMN forbidden TEXT NOT NULL DEFAULT '[]'")


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "question": r["question"],
        "kind": r["kind"],
        "expectedIds": json.loads(r["expected_ids"]),
        "keywords": json.loads(r["keywords"]),
        "forbidden": json.loads(r["forbidden"] if "forbidden" in r.keys() else "[]"),
        "note": r["note"] or "",
        "createdAt": r["created_at"],
    }


def add_qa(question: str, *, kind: str = "answerable",
           expected_ids: list[str] | None = None, keywords: list[str] | None = None,
           forbidden: list[str] | None = None, note: str = "") -> dict[str, Any]:
    if not question.strip():
        raise ValueError("질문은 필수입니다.")
    if kind not in KINDS:
        raise ValueError(f"잘못된 kind: {kind} (허용: {', '.join(KINDS)})")
    qid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO qa_golden (id, question, kind, expected_ids, keywords, forbidden, note, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (qid, question.strip(), kind,
             json.dumps(expected_ids or [], ensure_ascii=False),
             json.dumps(keywords or [], ensure_ascii=False),
             json.dumps(forbidden or [], ensure_ascii=False), note, _now()),
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
        from tests.eval_data import (
            NUMERIC_NEGATIVES,
            NUMERIC_QUERIES,
            QA_NEGATIVES,
            QA_QUERIES,
        )
    except Exception:
        return 0
    n = 0
    for q, exp, kws in QA_QUERIES:
        add_qa(q, kind="answerable", expected_ids=list(exp), keywords=list(kws))
        n += 1
    for q, exp, inc, forb in NUMERIC_QUERIES:  # 수치 정밀도: 정확 수치 포함 + 반올림/왜곡 금지
        add_qa(q, kind="answerable", expected_ids=list(exp), keywords=list(inc),
               forbidden=list(forb), note="numeric")
        n += 1
    for q in QA_NEGATIVES:
        add_qa(q, kind="negative")
        n += 1
    for q in NUMERIC_NEGATIVES:
        add_qa(q, kind="negative", note="numeric")
        n += 1
    return n
