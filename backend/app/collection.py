"""데이터 수집 저장소.

소스(EDM/Confluence/뉴스/증권사/컨센서스/업로드) 메타데이터와 수집된 문서를
stdlib sqlite3 에 저장한다. 업로드 파일은 디스크(UPLOADS_DIR)에 저장한다.

현실성 구분:
  - 실제 동작: 소스 CRUD, 수동 업로드(파일 저장), 문서 목록/검색
  - 스텁: 커넥터 소스의 '수집 트리거'는 실행 기록 + 카운트만 갱신
           (실제 EDM/Confluence/뉴스 크롤링은 이후 단계에서 연동)
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

SOURCE_TYPES = ("edm", "confluence", "news", "broker", "consensus", "upload")
# 커넥터형 소스(트리거 가능). 'upload' 는 수동 업로드라 트리거 대상 아님.
CONNECTOR_TYPES = ("edm", "confluence", "news", "broker", "consensus")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def _conn() -> sqlite3.Connection:
    config.COLLECTION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.COLLECTION_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: 쓰기가 읽기를 블로킹하지 않게 해 동시성·처리량 개선.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db() -> None:
    """스키마 생성 + 최초 1회 기본 소스 시드(대시보드 목업과 동일한 5종)."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                type       TEXT NOT NULL,
                config     TEXT NOT NULL DEFAULT '{}',
                enabled    INTEGER NOT NULL DEFAULT 1,
                status     TEXT NOT NULL DEFAULT '대기',
                last_run   TEXT,
                count      INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id           TEXT PRIMARY KEY,
                source_id    TEXT,
                source_name  TEXT NOT NULL,
                title        TEXT NOT NULL,
                filename     TEXT,
                path         TEXT,
                topic        TEXT,
                published_at TEXT,
                status       TEXT NOT NULL DEFAULT '수집됨',
                created_at   TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
            );
            -- 목록/검색 경로의 필터·정렬 인덱스(문서 누적 시 풀스캔 방지).
            CREATE INDEX IF NOT EXISTS idx_documents_source  ON documents(source_id);
            CREATE INDEX IF NOT EXISTS idx_documents_topic   ON documents(topic);
            CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);

            -- 전문검색(FTS5): documents 의 외부 콘텐츠 인덱스. 트리거로 동기화.
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, filename, topic,
                content='documents', content_rowid='rowid'
            );
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, filename, topic)
                VALUES (new.rowid, new.title, new.filename, new.topic);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, filename, topic)
                VALUES ('delete', old.rowid, old.title, old.filename, old.topic);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, filename, topic)
                VALUES ('delete', old.rowid, old.title, old.filename, old.topic);
                INSERT INTO documents_fts(rowid, title, filename, topic)
                VALUES (new.rowid, new.title, new.filename, new.topic);
            END;
            """
        )
        cur = conn.execute("SELECT COUNT(*) AS n FROM sources")
        if cur.fetchone()["n"] == 0:
            seed = [
                ("EDM 수집", "edm", {"path": "EDM 루트 경로"}, "정상", "2026-06-12 06:00", 128),
                ("Confluence 동기화", "confluence", {"space": "MI", "base_url": ""}, "정상", "2026-06-12 06:10", 54),
                ("뉴스 크롤링", "news", {"keywords": ["반도체", "HBM", "파운드리"]}, "정상", "2026-06-12 07:00", 312),
                ("증권사 리포트 수집", "broker", {"sources": []}, "지연", "2026-06-11 18:00", 9),
                ("컨센서스 갱신 감지", "consensus", {"tickers": ["QCOM", "MTK"]}, "정상", "2026-06-12 08:00", 2),
            ]
            for name, type_, cfg, status, last_run, count in seed:
                conn.execute(
                    "INSERT INTO sources (id, name, type, config, enabled, status, last_run, count, created_at)"
                    " VALUES (?,?,?,?,1,?,?,?,?)",
                    (uuid.uuid4().hex, name, type_, json.dumps(cfg, ensure_ascii=False),
                     status, last_run, count, _now()),
                )


def _row_to_source(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "config": json.loads(row["config"] or "{}"),
        "enabled": bool(row["enabled"]),
        "status": row["status"],
        "lastRun": row["last_run"],
        "count": row["count"],
        "createdAt": row["created_at"],
    }


def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sourceId": row["source_id"],
        "sourceName": row["source_name"],
        "title": row["title"],
        "filename": row["filename"],
        "topic": row["topic"],
        "publishedAt": row["published_at"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


# ── 소스 ───────────────────────────────────────────────────────────────
def list_sources() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM sources ORDER BY created_at").fetchall()
    return [_row_to_source(r) for r in rows]


def create_source(name: str, type_: str, config: dict[str, Any] | None, enabled: bool) -> dict[str, Any]:
    if type_ not in SOURCE_TYPES:
        raise ValueError(f"잘못된 소스 타입: {type_} (허용: {', '.join(SOURCE_TYPES)})")
    sid = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, config, enabled, status, count, created_at)"
            " VALUES (?,?,?,?,?,?,0,?)",
            (sid, name, type_, json.dumps(config or {}, ensure_ascii=False),
             1 if enabled else 0, "대기", _now()),
        )
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    return _row_to_source(row)


def update_source(sid: str, *, name: str | None = None, config: dict[str, Any] | None = None,
                  enabled: bool | None = None) -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise KeyError(sid)
        new_name = name if name is not None else row["name"]
        new_config = json.dumps(config, ensure_ascii=False) if config is not None else row["config"]
        new_enabled = (1 if enabled else 0) if enabled is not None else row["enabled"]
        conn.execute(
            "UPDATE sources SET name=?, config=?, enabled=? WHERE id=?",
            (new_name, new_config, new_enabled, sid),
        )
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    return _row_to_source(row)


def delete_source(sid: str) -> None:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM sources WHERE id=?", (sid,))
        if cur.rowcount == 0:
            raise KeyError(sid)


def collect_source(sid: str) -> dict[str, Any]:
    """수집 트리거(스텁). 커넥터 소스의 실행 기록 + 카운트만 갱신한다."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise KeyError(sid)
        if row["type"] not in CONNECTOR_TYPES:
            raise ValueError("업로드 소스는 수집 트리거 대상이 아닙니다.")
        if not row["enabled"]:
            raise ValueError("비활성 소스는 수집할 수 없습니다.")
        # 스텁: 실제 크롤링 대신 실행 시각만 갱신 (신규 건수 0)
        conn.execute(
            "UPDATE sources SET status='정상', last_run=? WHERE id=?",
            (_now(), sid),
        )
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    return {"source": _row_to_source(row), "ingested": 0, "stub": True}


# ── 문서 ───────────────────────────────────────────────────────────────
def _fts_match(q: str) -> str | None:
    """사용자 검색어를 안전한 FTS5 MATCH 식으로 변환(토큰별 접두 매칭).

    각 토큰을 따옴표로 감싸(특수문자 무력화) 접두(*)로 매칭한다.
    예: 'HBM 시장' -> '"HBM"* "시장"*'
    """
    tokens = [t for t in re.split(r"\s+", q.strip()) if t]
    if not tokens:
        return None
    return " ".join('"' + t.replace('"', '""') + '"*' for t in tokens)


def list_documents(source_id: str | None = None, q: str | None = None,
                   topic: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    params: list[Any] = []
    match = _fts_match(q) if q else None
    if match:
        # FTS5 전문검색 + 필터/정렬. rowid 로 documents 와 조인.
        # MATCH 는 별칭이 아니라 FTS 테이블명을 좌변으로 써야 한다.
        sql = (
            "SELECT d.* FROM documents_fts "
            "JOIN documents d ON d.rowid = documents_fts.rowid "
            "WHERE documents_fts MATCH ?"
        )
        params.append(match)
    else:
        sql = "SELECT d.* FROM documents d WHERE 1=1"
    if source_id:
        sql += " AND d.source_id=?"
        params.append(source_id)
    if topic:
        sql += " AND d.topic=?"
        params.append(topic)
    sql += " ORDER BY d.created_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_document(r) for r in rows]


def count_documents() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]


def delete_document(doc_id: str) -> None:
    with _conn() as conn:
        row = conn.execute("SELECT path FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            raise KeyError(doc_id)
        if row["path"]:
            Path(row["path"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))


def _ensure_named_source(conn: sqlite3.Connection, name: str, type_: str) -> sqlite3.Row:
    """이름+타입으로 소스를 보장(없으면 생성). 업로드/인제스트 소스 귀속에 사용."""
    row = conn.execute(
        "SELECT * FROM sources WHERE name=? AND type=? LIMIT 1", (name, type_)
    ).fetchone()
    if row is not None:
        return row
    sid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO sources (id, name, type, config, enabled, status, count, created_at)"
        " VALUES (?,?,?,?,1,?,0,?)",
        (sid, name, type_, "{}", "정상", _now()),
    )
    return conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()


def _ensure_upload_source(conn: sqlite3.Connection) -> sqlite3.Row:
    """수동 업로드용 소스를 보장(없으면 생성)."""
    return _ensure_named_source(conn, "수동 업로드", "upload")


def allocate_upload(filename: str) -> tuple[str, Path, str]:
    """업로드 대상 경로를 예약한다. (doc_id, dest_path, safe_name).

    스트리밍 업로드: 호출자가 dest 에 청크로 직접 쓰고 register_upload 로 등록한다.
    """
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4().hex
    safe_name = Path(filename).name or "untitled"  # 경로 조작 방지
    dest = config.UPLOADS_DIR / f"{doc_id}__{safe_name}"
    return doc_id, dest, safe_name


def register_upload(doc_id: str, dest: Path, safe_name: str,
                    topic: str | None = None) -> dict[str, Any]:
    """이미 디스크에 쓰인 업로드 파일을 문서로 등록한다."""
    with _conn() as conn:
        src = _ensure_upload_source(conn)
        conn.execute(
            "INSERT INTO documents (id, source_id, source_name, title, filename, path, topic,"
            " published_at, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (doc_id, src["id"], src["name"], safe_name, safe_name, str(dest),
             topic, _today(), "수집됨", _now()),
        )
        conn.execute(
            "UPDATE sources SET count = count + 1, last_run=? WHERE id=?",
            (_now(), src["id"]),
        )
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_document(row)


def save_upload(filename: str, content: bytes, topic: str | None = None) -> dict[str, Any]:
    """바이트를 받아 저장+등록(프로그램/테스트용). 엔드포인트는 스트리밍을 쓴다."""
    doc_id, dest, safe_name = allocate_upload(filename)
    dest.write_bytes(content)
    return register_upload(doc_id, dest, safe_name, topic)


# 기본 COM 인제스트 소스 이름 (DRM 해제 상태로 추출된 문서의 귀속)
COM_SOURCE_NAME = "COM 인제스트 (DRM 해제)"


def ingest_text(title: str, text: str, *, topic: str | None = None,
                original_filename: str | None = None,
                source_name: str = COM_SOURCE_NAME) -> dict[str, Any]:
    """이미 추출된 평문 텍스트를 문서로 등록한다.

    Windows COM 인제스트 워커가 DRM 해제 상태로 추출한 본문을 여기로 보낸다.
    원본(암호화) 파일이 아니라 추출 텍스트를 .txt 로 저장한다.
    """
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4().hex
    safe_title = Path(title).name or "untitled"
    dest = config.UPLOADS_DIR / f"{doc_id}__{safe_title}.txt"
    dest.write_text(text, encoding="utf-8")
    with _conn() as conn:
        src = _ensure_named_source(conn, source_name, "upload")
        conn.execute(
            "INSERT INTO documents (id, source_id, source_name, title, filename, path, topic,"
            " published_at, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (doc_id, src["id"], src["name"], safe_title,
             original_filename or safe_title, str(dest), topic, _today(),
             "수집됨", _now()),
        )
        conn.execute(
            "UPDATE sources SET count = count + 1, last_run=? WHERE id=?",
            (_now(), src["id"]),
        )
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_document(row)
