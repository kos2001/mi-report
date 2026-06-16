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

from . import assets, config, embeddings, qa_golden, synonyms, voc

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

            -- 본문 전문검색(FTS5): RAG 검색용. 외부 콘텐츠가 아니라 본문을 직접 보관·색인한다
            -- (본문은 디스크 파일에 있고 DB 엔 없으므로 별도 테이블로 색인). doc_id 로 documents 와 조인.
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_content_fts USING fts5(doc_id UNINDEXED, body);

            -- 의미 임베딩(하이브리드 검색용). vec 는 float32 raw bytes, model 로 차원/모델 추적.
            CREATE TABLE IF NOT EXISTS documents_embeddings (
                doc_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                model  TEXT NOT NULL,
                vec    BLOB NOT NULL
            );
            """
        )
        _backfill_content_fts(conn)
        cur = conn.execute("SELECT COUNT(*) AS n FROM sources")
        if cur.fetchone()["n"] == 0:
            seed = [
                ("EDM 수집", "edm", {"path": "EDM 루트 경로"}, "정상", "2026-06-12 06:00", 128),
                # 실제 Confluence Cloud(wiki) — '지금 수집'이 API 로 페이지를 가져온다.
                # 자격증명은 .env 의 CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN.
                ("Confluence 동기화", "confluence",
                 {"base_url": "https://oseokkim2001-1776691210112.atlassian.net/wiki"},
                 "정상", "2026-06-12 06:10", 54),
                # 실제 뉴스 섹션(네이버 IT/과학) — '지금 수집'이 실제 fetch.
                ("뉴스 크롤링", "news",
                 {"url": "https://news.naver.com/section/105", "keywords": ["반도체", "HBM", "파운드리"]},
                 "정상", "2026-06-12 07:00", 312),
                # 실제 증권사 리포트 집계 사이트(한경 컨센서스) — '지금 수집'이 실제 fetch.
                ("증권사 리포트 수집", "broker", {"url": "https://consensus.hankyung.com/"}, "정상", "2026-06-12 18:00", 9),
                ("컨센서스 갱신 감지", "consensus", {"tickers": ["QCOM", "MTK"]}, "정상", "2026-06-12 08:00", 2),
            ]
            for name, type_, cfg, status, last_run, count in seed:
                conn.execute(
                    "INSERT INTO sources (id, name, type, config, enabled, status, last_run, count, created_at)"
                    " VALUES (?,?,?,?,1,?,?,?,?)",
                    (uuid.uuid4().hex, name, type_, json.dumps(cfg, ensure_ascii=False),
                     status, last_run, count, _now()),
                )
    # 지식 자산(생성물·피드백) + VOC + Q&A 골든 평가셋 테이블도 함께 초기화
    assets.init_assets()
    voc.init_voc()
    qa_golden.init_qa_golden()
    qa_golden.seed_defaults()  # 비어 있으면 코드 기본 셋 시드(멱등)


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
    """소스와 그 소스로 수집된 문서(파일·본문 FTS 포함)를 함께 삭제한다.

    문서를 고아로 남기지 않는다(이전 FK SET NULL 동작 → 잔존 문서가 RAG 에 남던 문제).
    """
    with _conn() as conn:
        if conn.execute("SELECT 1 FROM sources WHERE id=?", (sid,)).fetchone() is None:
            raise KeyError(sid)
        rows = conn.execute(
            "SELECT id, path FROM documents WHERE source_id=?", (sid,)
        ).fetchall()
        for r in rows:
            if r["path"]:
                Path(r["path"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM documents WHERE id=?", (r["id"],))
            _index_content(conn, r["id"], None)
        conn.execute("DELETE FROM sources WHERE id=?", (sid,))


def get_source(sid: str) -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    if row is None:
        raise KeyError(sid)
    return _row_to_source(row)


_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def source_urls(source: dict[str, Any]) -> list[str]:
    """소스에서 수집 대상 URL 목록을 뽑는다.

    우선순위: config.url(문자열) / config.urls(리스트) > URL 처럼 보이는 소스 이름.
    스킴이 없으면 https:// 를 붙인다. URL 이 없으면 빈 리스트(→ 스텁 수집).
    """
    cfg = source.get("config") or {}
    raw: list[str] = []
    one = cfg.get("url")
    if isinstance(one, str) and one.strip():
        raw.append(one.strip())
    many = cfg.get("urls")
    if isinstance(many, list):
        raw += [u.strip() for u in many if isinstance(u, str) and u.strip()]
    if not raw:
        name = (source.get("name") or "").strip()
        # 이름이 URL 처럼 보이면(점 포함, 공백 없음) 수집 대상으로 본다.
        if name and " " not in name and "." in name:
            raw.append(name)
    return [u if _URL_SCHEME_RE.match(u) else f"https://{u}" for u in raw]


def mark_source_status(sid: str, status: str) -> dict[str, Any]:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE sources SET status=?, last_run=? WHERE id=?", (status, _now(), sid)
        )
        if cur.rowcount == 0:
            raise KeyError(sid)
        row = conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    return _row_to_source(row)


def add_crawled_document(
    source_id: str, source_name: str, title: str, text: str,
    *, url: str | None = None, topic: str | None = None,
) -> dict[str, Any]:
    """수집한 페이지 본문을 문서로 저장하고 소스 카운트를 갱신한다."""
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4().hex
    safe_title = (Path(title).name or "untitled").strip()[:120] or "untitled"
    dest = config.UPLOADS_DIR / f"{doc_id}__{safe_title}.txt"
    body = f"# {title}\n원본: {url}\n\n{text}" if url else text
    dest.write_text(body, encoding="utf-8")
    with _conn() as conn:
        conn.execute(
            "INSERT INTO documents (id, source_id, source_name, title, filename, path, topic,"
            " published_at, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (doc_id, source_id, source_name, safe_title, url or safe_title, str(dest),
             topic, _today(), "수집됨", _now()),
        )
        conn.execute(
            "UPDATE sources SET count = count + 1, status='정상', last_run=? WHERE id=?",
            (_now(), source_id),
        )
        _index_content(conn, doc_id, text, title=title, topic=topic)  # 제목+주제+본문 색인
        store_embedding(conn, doc_id, title=title, topic=topic, text=text)  # 의미 임베딩(활성 시)
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_document(row)


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
def _fts_match(q: str, *, op: str = "AND") -> str | None:
    """사용자 검색어를 안전한 FTS5 MATCH 식으로 변환(토큰별 접두 매칭).

    각 토큰을 따옴표로 감싸(특수문자 무력화) 접두(*)로 매칭한다.
    op="AND"(기본): 모든 토큰 포함(정밀 검색). 예: 'HBM 시장' -> '"HBM"* "시장"*'
    op="OR": 한 토큰이라도 포함(재현율 우선, RAG 검색용). BM25 가 관련도로 정렬한다.
    """
    tokens = [t for t in re.split(r"\s+", q.strip()) if t]
    if not tokens:
        return None
    joiner = " OR " if op == "OR" else " "
    return joiner.join('"' + t.replace('"', '""') + '"*' for t in tokens)


def _read_path_text(path: str | None, *, max_chars: int | None = None) -> str | None:
    """디스크 경로의 텍스트를 읽는다(비텍스트/없음이면 None)."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8").strip()
    except (UnicodeDecodeError, OSError):
        return None
    if not text:
        return None
    return text[:max_chars] if max_chars else text


def _index_content(conn: sqlite3.Connection, doc_id: str, text: str | None,
                   *, title: str | None = None, topic: str | None = None) -> None:
    """본문 FTS 색인 갱신(있으면 교체). RAG 검색이 제목·주제·본문까지 매칭하도록.

    제목·주제를 본문 앞에 함께 색인한다(핵심어가 제목에만 있는 경우의 회수율 개선).
    """
    conn.execute("DELETE FROM documents_content_fts WHERE doc_id=?", (doc_id,))
    body = "\n".join(p.strip() for p in (title, topic, text) if p and p.strip())
    if body:
        conn.execute(
            "INSERT INTO documents_content_fts(doc_id, body) VALUES(?,?)", (doc_id, body)
        )


def _backfill_content_fts(conn: sqlite3.Connection) -> None:
    """본문 FTS 에 아직 없는 문서를 디스크에서 읽어 색인(기존 DB 마이그레이션)."""
    rows = conn.execute(
        "SELECT d.id, d.path, d.title, d.topic FROM documents d "
        "LEFT JOIN documents_content_fts f ON f.doc_id = d.id "
        "WHERE f.doc_id IS NULL"
    ).fetchall()
    for r in rows:
        text = _read_path_text(r["path"])
        body = "\n".join(
            p.strip() for p in (r["title"], r["topic"], text) if p and p.strip()
        )
        if body:
            conn.execute(
                "INSERT INTO documents_content_fts(doc_id, body) VALUES(?,?)", (r["id"], body)
            )


def rebuild_content_fts() -> int:
    """모든 문서의 본문 FTS 를 제목+주제+본문으로 재구축한다(일회성 유지보수).

    기존에 본문만 색인된 문서를 제목·주제 포함으로 갱신해 회수율 개선을 소급 적용한다.
    재색인된 문서 수를 반환한다.
    """
    n = 0
    with _conn() as conn:
        rows = conn.execute("SELECT id, path, title, topic FROM documents").fetchall()
        for r in rows:
            text = _read_path_text(r["path"])
            _index_content(conn, r["id"], text, title=r["title"], topic=r["topic"])
            n += 1
    return n


# ── 의미 임베딩 + 하이브리드 검색 ───────────────────────────────────────
def _embed_doc_text(title: str | None, topic: str | None, text: str | None) -> str:
    """임베딩 대상 텍스트(제목+주제+본문)를 구성."""
    return "\n".join(p.strip() for p in (title, topic, text) if p and p.strip())


def store_embedding(conn: sqlite3.Connection, doc_id: str, *, title: str | None = None,
                    topic: str | None = None, text: str | None = None) -> None:
    """문서 임베딩을 계산·저장(임베딩 비활성/실패 시 무동작)."""
    if not embeddings.active():
        return
    body = _embed_doc_text(title, topic, text)
    if not body:
        return
    mat = embeddings.embed([body], is_query=False)
    if mat is None:
        return
    conn.execute(
        "INSERT OR REPLACE INTO documents_embeddings(doc_id, model, vec) VALUES(?,?,?)",
        (doc_id, embeddings.model_name(), mat[0].tobytes()),
    )


def rebuild_embeddings() -> int:
    """모든 문서의 임베딩을 (재)계산·저장한다(배치). 임베딩 비활성 시 0 반환."""
    if not embeddings.active():
        return 0
    with _conn() as conn:
        rows = conn.execute("SELECT id, path, title, topic FROM documents").fetchall()
        ids, texts = [], []
        for r in rows:
            body = _embed_doc_text(r["title"], r["topic"], _read_path_text(r["path"]))
            if body:
                ids.append(r["id"])
                texts.append(body)
        if not texts:
            return 0
        mat = embeddings.embed(texts, is_query=False)
        if mat is None:
            return 0
        for did, vec in zip(ids, mat):
            conn.execute(
                "INSERT OR REPLACE INTO documents_embeddings(doc_id, model, vec) VALUES(?,?,?)",
                (did, embeddings.model_name(), vec.tobytes()),
            )
    return len(ids)


def _load_doc_vectors(conn: sqlite3.Connection, *, topic: str | None = None,
                      source_id: str | None = None):
    """저장된 문서 임베딩을 (ids, matrix) 로 로드(필터 적용). 없으면 (None, None)."""
    import numpy as np

    sql = (
        "SELECT e.doc_id AS doc_id, e.vec AS vec FROM documents_embeddings e "
        "JOIN documents d ON d.id = e.doc_id WHERE 1=1"
    )
    params: list[Any] = []
    if source_id:
        sql += " AND d.source_id=?"
        params.append(source_id)
    if topic:
        sql += " AND d.topic=?"
        params.append(topic)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return None, None
    ids = [r["doc_id"] for r in rows]
    mat = np.frombuffer(b"".join(r["vec"] for r in rows), dtype="float32").reshape(len(rows), -1)
    return ids, mat


def _rrf(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion: 여러 순위 리스트를 결합(상위일수록 큰 점수)."""
    out: dict[str, float] = {}
    for rl in rank_lists:
        for pos, idx in enumerate(rl):
            out[idx] = out.get(idx, 0.0) + 1.0 / (k + pos)
    return out


def hybrid_search(query: str, *, limit: int = 8, topic: str | None = None,
                  source_id: str | None = None, pool: int = 30) -> list[dict[str, Any]]:
    """BM25(어휘) + 의미 임베딩(dense)을 RRF 로 결합한 하이브리드 검색.

    어휘가 안 겹치는 패러프레이즈도 dense 가 회수하고, 정확한 키워드는 BM25 가 잡는다.
    BM25 폴백 절차: 임베딩이 비활성이거나, 질의 임베딩/벡터 로드/dense 계산이 실패하면
    항상 BM25(어휘) 결과로 폴백한다(임베딩 장애가 검색을 막지 않음).
    """
    bm25 = search_documents(query, limit=pool, topic=topic, source_id=source_id)
    if not embeddings.active():
        return bm25[:limit]  # 폴백 1: 임베딩 비활성
    try:
        import numpy as np

        qmat = embeddings.embed([query], is_query=True)
        with _conn() as conn:
            ids, mat = _load_doc_vectors(conn, topic=topic, source_id=source_id)
        if qmat is None or ids is None:
            return bm25[:limit]  # 폴백 2: 임베딩/벡터 없음(임베딩 호출 실패 포함)
        qv = qmat[0]
        sims = mat @ qv / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv) + 1e-9)
        dense_order = [ids[i] for i in np.argsort(-sims)]
        fused = _rrf([[d["id"] for d in bm25], dense_order])
        top_ids = [i for i, _ in sorted(fused.items(), key=lambda x: -x[1])[:limit]]
        docs = {d["id"]: d for d in bm25}
        missing = [i for i in top_ids if i not in docs]
        if missing:
            with _conn() as conn:
                qmarks = ",".join("?" * len(missing))
                rows = conn.execute(
                    f"SELECT * FROM documents WHERE id IN ({qmarks})", missing
                ).fetchall()
            for r in rows:
                docs[r["id"]] = _row_to_document(r)
        return [docs[i] for i in top_ids if i in docs]
    except Exception:
        return bm25[:limit]  # 폴백 3: dense 단계 예외 → 어휘 검색으로 안전 복귀


def search_documents(query: str, *, limit: int = 8, topic: str | None = None,
                     source_id: str | None = None) -> list[dict[str, Any]]:
    """본문 BM25 검색. 질문과 관련도 높은 순으로 문서를 반환(매칭 없으면 빈 리스트).

    RAG 회수율을 위해 OR 매칭(한 토큰이라도 포함)을 쓰고 BM25 로 관련도 정렬한다.
    도메인 동의어로 질의를 확장해 동의어/약어 격차를 메운다.
    """
    match = _fts_match(synonyms.expand_query(query), op="OR") if query else None
    if not match:
        return []
    params: list[Any] = [match]
    sql = (
        "SELECT d.*, bm25(documents_content_fts) AS rank "
        "FROM documents_content_fts "
        "JOIN documents d ON d.id = documents_content_fts.doc_id "
        "WHERE documents_content_fts MATCH ?"
    )
    if source_id:
        sql += " AND d.source_id=?"
        params.append(source_id)
    if topic:
        sql += " AND d.topic=?"
        params.append(topic)
    sql += " ORDER BY rank LIMIT ?"  # bm25: 값이 작을수록 관련도 높음
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_document(r) for r in rows]


def documents_for_rag(query: str, *, limit: int = 8, topic: str | None = None,
                      source_id: str | None = None, max_chars: int = 4000) -> list[dict[str, Any]]:
    """RAG 입력: 질문 관련 문서를 본문 BM25 로 검색해 본문과 함께 반환.

    본문 매칭이 없으면 최근 문서로 폴백한다(질문이 색인 토큰과 안 겹칠 때).
    임베딩이 활성화되면 BM25+의미(dense) 하이브리드로 회수한다.
    """
    hits = hybrid_search(query, limit=limit, topic=topic, source_id=source_id)
    if not hits:
        hits = list_documents(source_id=source_id, topic=topic, limit=limit)
    out: list[dict[str, Any]] = []
    for d in hits:
        text = read_document_text(d["id"], max_chars=max_chars)
        if not text:
            continue
        out.append(
            {
                "id": d["id"],
                "title": d["title"],
                "source": d["sourceName"],
                "publishedAt": d["publishedAt"],
                "content": text,
            }
        )
    return out


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


def today() -> str:
    """오늘 날짜(YYYY-MM-DD). 생성물 메타데이터(updatedAt 등)에 사용."""
    return _today()


def now() -> str:
    """현재 시각(YYYY-MM-DD HH:MM). 생성물 타임스탬프에 사용."""
    return _now()


def list_topics() -> list[dict[str, Any]]:
    """문서에 부여된 주제 목록 + 건수(내림차순). 비어 있는 주제는 제외."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT topic, COUNT(*) AS n FROM documents "
            "WHERE topic IS NOT NULL AND topic != '' "
            "GROUP BY topic ORDER BY n DESC, topic"
        ).fetchall()
    return [{"topic": r["topic"], "count": r["n"]} for r in rows]


def read_document_text(doc_id: str, *, max_chars: int = 4000) -> str | None:
    """문서의 저장 본문을 읽는다(텍스트만, 길이 제한). 없거나 비텍스트면 None.

    업로드/인제스트 문서는 디스크(path)에 저장된다. 바이너리(.docx 등)는 여기서
    추출하지 않고 None 을 반환한다(추출은 COM 워커 등 인제스트 단계의 책임).
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT path FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
    if row is None:
        raise KeyError(doc_id)
    return _read_path_text(row["path"], max_chars=max_chars)


def documents_for_digest(
    limit: int = 20,
    source_id: str | None = None,
    topic: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """LLM 입력용: 최근 문서 중 읽을 수 있는 본문이 있는 것만 묶어 반환."""
    docs = list_documents(source_id=source_id, q=q, topic=topic, limit=limit)
    out: list[dict[str, Any]] = []
    for d in docs:
        text = read_document_text(d["id"])
        if not text:
            continue
        out.append(
            {
                "id": d["id"],
                "title": d["title"],
                "source": d["sourceName"],
                "publishedAt": d["publishedAt"],
                "content": text,
            }
        )
    return out


def get_document(doc_id: str) -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if row is None:
        raise KeyError(doc_id)
    return _row_to_document(row)


def set_topic(doc_id: str, topic: str) -> dict[str, Any]:
    """문서의 주제를 갱신한다(자동 분류 결과 반영). FTS 트리거가 색인을 동기화."""
    with _conn() as conn:
        cur = conn.execute("UPDATE documents SET topic=? WHERE id=?", (topic, doc_id))
        if cur.rowcount == 0:
            raise KeyError(doc_id)
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_document(row)


def list_untagged_ids(limit: int = 50) -> list[str]:
    """주제가 비어 있는 문서 id 목록(최신순). 일괄 자동 분류 대상."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id FROM documents WHERE topic IS NULL OR topic='' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [r["id"] for r in rows]


def delete_document(doc_id: str) -> None:
    with _conn() as conn:
        row = conn.execute("SELECT path FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            raise KeyError(doc_id)
        if row["path"]:
            Path(row["path"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        _index_content(conn, doc_id, None)  # 본문 FTS 에서도 제거


def delete_documents_by_source(source_id: str) -> int:
    """소스의 모든 문서를 삭제한다(커넥터 재동기화용). 삭제 건수 반환."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, path FROM documents WHERE source_id=?", (source_id,)
        ).fetchall()
        for r in rows:
            if r["path"]:
                Path(r["path"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM documents WHERE id=?", (r["id"],))
            _index_content(conn, r["id"], None)
        conn.execute("UPDATE sources SET count=0 WHERE id=?", (source_id,))
    return len(rows)


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
        # 업로드 파일이 텍스트면 본문 RAG 검색 색인(바이너리는 None → 건너뜀)
        _index_content(conn, doc_id, _read_path_text(str(dest)))
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
        _index_content(conn, doc_id, text, title=title, topic=topic)  # 제목+주제+본문 색인
        store_embedding(conn, doc_id, title=title, topic=topic, text=text)  # 의미 임베딩(활성 시)
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _row_to_document(row)
