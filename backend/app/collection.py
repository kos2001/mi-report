"""데이터 수집 저장소.

소스(EDM/Confluence/뉴스/증권사/컨센서스/업로드) 메타데이터와 수집된 문서를
stdlib sqlite3 에 저장한다. 업로드 파일은 디스크(UPLOADS_DIR)에 저장한다.

현실성 구분:
  - 실제 동작: 소스 CRUD, 수동 업로드(파일 저장), 문서 목록/검색
  - 스텁: 커넥터 소스의 '수집 트리거'는 실행 기록 + 카운트만 갱신
           (실제 EDM/Confluence/뉴스 크롤링은 이후 단계에서 연동)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import assets, config, db, embeddings, qa_golden, schedule, synonyms, voc

SOURCE_TYPES = ("edm", "confluence", "sec", "dart", "hankyung", "news", "broker", "consensus", "upload")
# 커넥터형 소스(트리거 가능). 'upload' 는 수동 업로드라 트리거 대상 아님.
CONNECTOR_TYPES = ("edm", "confluence", "sec", "dart", "hankyung", "news", "broker", "consensus")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def _conn() -> sqlite3.Connection:
    return db.connect()  # 스레드별 재사용 커넥션(호출마다 connect+PRAGMA 제거)


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

            -- 캐시 무효화 버전(프로세스 간 공유). 벡터 행렬 인메모리 캐시가 이 값으로
            -- 최신성을 확인한다. 쓰기 트랜잭션에서 함께 증가시킨다.
            CREATE TABLE IF NOT EXISTS cache_version (
                name    TEXT PRIMARY KEY,
                version INTEGER NOT NULL
            );

            -- 의미 임베딩(하이브리드 검색용). vec 는 float32 raw bytes, model 로 차원/모델 추적.
            CREATE TABLE IF NOT EXISTS documents_embeddings (
                doc_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                model  TEXT NOT NULL,
                vec    BLOB NOT NULL
            );
            """
        )
        _migrate_content_hash(conn)
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
                # 실제 SEC EDGAR 경쟁사 IR(퀄컴) — '지금 수집'이 공시·재무를 API 로 가져온다.
                ("경쟁사 IR · SEC", "sec",
                 {"cik": "0000804328", "name": "Qualcomm"}, "정상", "2026-06-12 06:30", 0),
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
    schedule.init_schedule()


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
        _bump_vec_version(conn)  # 문서 삭제 → 임베딩 CASCADE 삭제 → 벡터 캐시 무효화


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
    # 임베딩(네트워크/모델 호출 가능)은 쓰기 트랜잭션 밖에서 계산 — 잠금 시간 최소화
    embedding = _compute_embedding(title, topic, text)
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
        _insert_embedding(conn, doc_id, embedding)  # 의미 임베딩(활성 시)
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
    """디스크 경로의 텍스트를 읽는다(비텍스트/없음이면 None).

    max_chars 가 주어지면 파일 전체가 아니라 필요한 앞부분만 읽는다(UTF-8 은 문자당
    최대 4바이트 → max_chars*4 바이트면 충분). 인제스트 문서는 수 MB 까지 커지는데
    LLM 컨텍스트엔 앞 4천 자만 쓰므로, 전체 읽기는 그만큼 낭비된 I/O 였다.
    디코딩은 strict 를 유지한다(바이너리 업로드는 계속 None) — 다만 앞부분만 읽으면
    마지막 문자가 잘릴 수 있으므로, 끝 4바이트 안에서 난 디코드 오류만 절단으로 보고
    그 지점까지를 쓴다. 그보다 앞에서 깨지면 실제 비텍스트로 판단해 None.
    """
    if not path:
        return None
    p = Path(path)
    try:
        if max_chars:
            with p.open("rb") as fh:
                raw = fh.read(max_chars * 4)
            try:
                text = raw.decode("utf-8").strip()
            except UnicodeDecodeError as e:
                if e.start < len(raw) - 4:
                    return None  # 앞부분부터 깨짐 → 비텍스트(.docx 등)
                text = raw[: e.start].decode("utf-8").strip()
        else:
            text = p.read_text(encoding="utf-8").strip()
    except (UnicodeDecodeError, OSError):  # 없음/권한/비텍스트
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


def _migrate_content_hash(conn: sqlite3.Connection) -> None:
    """documents.content_sha256 컬럼 추가 + 기존 행 백필(멱등).

    인제스트 멱등성(동일 제목+본문 재전송 시 중복 등록 방지)에 쓴다.
    백필은 hash 가 NULL 인 행만 디스크 본문을 읽어 1회 수행된다.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
    if "content_sha256" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN content_sha256 TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_sha256)"
    )
    rows = conn.execute(
        "SELECT id, path, title FROM documents "
        "WHERE content_sha256 IS NULL AND path IS NOT NULL"
    ).fetchall()
    for r in rows:
        # 원문 바이트를 그대로 읽는다. read_text 경유(_read_path_text)는 유니버설
        # 뉴라인 변환('\r'→'\n')과 strip 을 해 인제스트 시 원문 해시와 어긋난다
        # (Word 추출 텍스트는 '\r' 문단 구분 — 정규화하면 dedup 이 영영 안 맞는다).
        try:
            text = Path(r["path"]).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text:
            continue
        conn.execute(
            "UPDATE documents SET content_sha256=? WHERE id=?",
            (_content_hash(r["title"], text), r["id"]),
        )


def _content_hash(title: str, text: str) -> str:
    """멱등 키: 제목+본문 SHA-256 (같은 본문이라도 제목이 다르면 별개 문서).

    title 은 저장 형태(safe_title = Path(title).name)로 정규화해 넣는다 —
    백필이 저장된 행에서 같은 키를 재계산할 수 있어야 한다.
    """
    safe = Path(title).name or "untitled"
    return hashlib.sha256(f"{safe}\n\x00{text}".encode("utf-8")).hexdigest()


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
# 임베딩 입력 상한(문자). 임베딩 모델은 앞부분만 반영하므로(MiniLM 512토큰 절단,
# bge-m3 는 길이만큼 비용·지연 증가) 본문 전체를 보내지 않는다. FTS 색인은 전문 유지.
EMBED_MAX_CHARS = int(os.environ.get("MI_EMBED_MAX_CHARS", "8000") or 8000)


def _embed_doc_text(title: str | None, topic: str | None, text: str | None) -> str:
    """임베딩 대상 텍스트(제목+주제+본문 앞부분)를 구성."""
    body = "\n".join(p.strip() for p in (title, topic, text) if p and p.strip())
    return body[:EMBED_MAX_CHARS]


def _compute_embedding(title: str | None, topic: str | None,
                       text: str | None) -> tuple[str, bytes] | None:
    """임베딩 벡터를 계산해 (model, bytes) 반환(비활성/실패 시 None).

    네트워크/모델 호출이 있을 수 있으므로 쓰기 트랜잭션 밖에서 호출한다
    (트랜잭션이 잠금을 쥔 채 임베딩을 기다리면 병렬 수집이 서로 블로킹된다).
    """
    body = _embed_doc_text(title, topic, text)
    if not body:
        return None
    return _compute_embeddings([body])[0]


def _insert_embedding(conn: sqlite3.Connection, doc_id: str,
                      computed: tuple[str, bytes] | None) -> None:
    """미리 계산된 임베딩을 저장(None 이면 무동작)."""
    if computed is None:
        return
    conn.execute(
        "INSERT OR REPLACE INTO documents_embeddings(doc_id, model, vec) VALUES(?,?,?)",
        (doc_id, computed[0], computed[1]),
    )
    _bump_vec_version(conn)  # 벡터 캐시 무효화


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
    # 배치 임베딩(네트워크/모델 호출)은 트랜잭션 밖에서 — 잠금 시간 최소화
    mat = embeddings.embed(texts, is_query=False)
    if mat is None:
        return 0
    with _conn() as conn:
        for did, vec in zip(ids, mat):
            conn.execute(
                "INSERT OR REPLACE INTO documents_embeddings(doc_id, model, vec) VALUES(?,?,?)",
                (did, embeddings.model_name(), vec.tobytes()),
            )
        _bump_vec_version(conn)  # 벡터 캐시 무효화
    return len(ids)


# 문서 벡터 행렬 프로세스 캐시 — 질의마다 전체 임베딩을 DB 에서 읽어 numpy 로 만드는
# 비용(20k 문서 × 1024차원에서 약 46ms, 코퍼스 크기에 선형)을 제거한다. L2 정규화까지
# 미리 해 두므로 질의당 비용은 행렬-벡터 곱 한 번이다.
#
# 무효화 규약: (cache_version 행, MAX(rowid)) — 둘 다 O(1) 조회다.
# 임베딩을 쓰거나 문서를 삭제하는 경로가 _bump_vec_version(conn) 으로 DB 버전을 올리고,
# 그 값이 트랜잭션과 함께 커밋되므로 같은 DB 를 쓰는 다른 프로세스(tools/ 스크립트)도
# 자동으로 무효화된다. MAX(rowid) 는 그 호출을 빼먹은 쓰기에 대한 예비 감지.
# (임베딩 행 수를 키로 쓰면 COUNT(*) 가 4KB 블롭 페이지를 전부 훑어 캐시보다 비싸다.)
# 쓰기 경로에 새 임베딩 저장을 추가하면 _bump_vec_version(conn) 도 함께 호출할 것.
_vec_lock = threading.Lock()
_vec_cache: dict[str, tuple[tuple, list[str], Any]] = {}


def _bump_vec_version(conn: sqlite3.Connection) -> None:
    """임베딩/문서 쓰기와 같은 트랜잭션에서 벡터 캐시 버전을 올린다."""
    conn.execute(
        "INSERT INTO cache_version(name, version) VALUES('vectors', 1) "
        "ON CONFLICT(name) DO UPDATE SET version = version + 1"
    )


def _vec_cache_key(conn: sqlite3.Connection) -> tuple:
    ver = conn.execute(
        "SELECT version FROM cache_version WHERE name='vectors'"
    ).fetchone()
    mx = conn.execute("SELECT MAX(rowid) AS mx FROM documents_embeddings").fetchone()
    return (ver["version"] if ver else 0, mx["mx"] if mx else None)


def _all_doc_vectors(conn: sqlite3.Connection):
    """전체 문서 임베딩을 (ids, 정규화 행렬) 로 반환(캐시). 없으면 (None, None)."""
    import numpy as np

    key = _vec_cache_key(conn)
    if key[1] is None:  # 임베딩 없음
        return None, None
    path = str(config.COLLECTION_DB)
    cached = _vec_cache.get(path)
    if cached is not None and cached[0] == key:
        return cached[1], cached[2]
    rows = conn.execute("SELECT doc_id, vec FROM documents_embeddings").fetchall()
    if not rows:
        return None, None
    ids = [r["doc_id"] for r in rows]
    mat = np.frombuffer(b"".join(r["vec"] for r in rows), dtype="float32").reshape(len(rows), -1)
    unit = mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
    with _vec_lock:
        _vec_cache[path] = (key, ids, unit)
    return ids, unit


def _filter_mask(conn: sqlite3.Connection, ids: list[str], *, topic: str | None,
                 source_id: str | None):
    """topic/source_id 필터에 해당하는 문서만 True 인 마스크(필터 없으면 None).

    벡터 행렬은 전체를 캐시하고 점수 단계에서 마스킹한다(필터별 행렬 사본 방지).
    """
    if not topic and not source_id:
        return None
    import numpy as np

    sql = "SELECT id FROM documents WHERE 1=1"
    params: list[Any] = []
    if source_id:
        sql += " AND source_id=?"
        params.append(source_id)
    if topic:
        sql += " AND topic=?"
        params.append(topic)
    allowed = {r["id"] for r in conn.execute(sql, params)}
    return np.fromiter((d in allowed for d in ids), dtype=bool, count=len(ids))


def _top_ids(ids: list[str], sims, k: int) -> list[str]:
    """유사도 상위 k 개 문서 id(내림차순). 전체 정렬 대신 부분 선택(argpartition).

    RRF 는 두 순위 리스트의 상위만 의미가 있으므로 dense 순위도 k(=pool)까지만 만든다
    (20k 문서에서 전체 argsort 8.4ms → 1.4ms). -inf(필터 제외)는 결과에서 뺀다.
    """
    import numpy as np

    n = len(ids)
    if k >= n:
        order = np.argsort(-sims)
    else:
        part = np.argpartition(-sims, k)[:k]
        order = part[np.argsort(-sims[part])]
    return [ids[i] for i in order if np.isfinite(sims[i])]


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
    return hybrid_search_multi(
        [query], limit=limit, topic=topic, source_id=source_id, pool=pool
    )[0]


def hybrid_search_multi(queries: list[str], *, limit: int = 8, topic: str | None = None,
                        source_id: str | None = None,
                        pool: int = 30) -> list[list[dict[str, Any]]]:
    """여러 질의를 한 번의 임베딩 호출·한 번의 벡터 로드로 검색(질의별 결과 리스트).

    질의당 임베딩 왕복 1회씩 들던 것을 배치 1회로 줄인다. 원격 임베딩(bge-m3)은
    왕복이 300~500ms 라, 그라운딩처럼 질문·답변 2개 질의를 쓰는 경로에서 그대로 절약된다.
    폴백 규약은 hybrid_search 와 동일 — 어떤 단계가 실패해도 질의별 BM25 결과를 돌려준다.
    """
    bm25_lists = [
        search_documents(q, limit=pool, topic=topic, source_id=source_id) for q in queries
    ]
    fallback = [b[:limit] for b in bm25_lists]
    if not embeddings.active():
        return fallback  # 폴백 1: 임베딩 비활성
    try:
        import numpy as np

        qmat = embeddings.embed(list(queries), is_query=True)
        with _conn() as conn:
            ids, unit = _all_doc_vectors(conn)
            mask = (
                _filter_mask(conn, ids, topic=topic, source_id=source_id)
                if ids is not None else None
            )
        # 폴백 2: 임베딩/벡터 없음(임베딩 호출 실패 포함) 또는 배치 응답 개수 불일치
        if qmat is None or ids is None or len(qmat) != len(queries):
            return fallback
        fused_ids: list[list[str]] = []
        for i, bm25 in enumerate(bm25_lists):
            qv = qmat[i]
            sims = unit @ (qv / (float(np.linalg.norm(qv)) + 1e-9))
            if mask is not None:
                sims = np.where(mask, sims, -np.inf)
            fused = _rrf([[d["id"] for d in bm25], _top_ids(ids, sims, pool)])
            fused_ids.append([k for k, _ in sorted(fused.items(), key=lambda x: -x[1])[:limit]])
        docs = {d["id"]: d for bm25 in bm25_lists for d in bm25}
        missing = list({i for lst in fused_ids for i in lst if i not in docs})
        if missing:  # dense 로만 올라온 문서의 메타데이터를 한 번의 쿼리로 채운다
            with _conn() as conn:
                qmarks = ",".join("?" * len(missing))
                rows = conn.execute(
                    f"SELECT * FROM documents WHERE id IN ({qmarks})", missing
                ).fetchall()
            for r in rows:
                docs[r["id"]] = _row_to_document(r)
        return [[docs[i] for i in lst if i in docs] for lst in fused_ids]
    except Exception:
        return fallback  # 폴백 3: dense 단계 예외 → 어휘 검색으로 안전 복귀


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


def _contents_for_ids(ids: list[str], *, max_chars: int = 4000) -> dict[str, str]:
    """여러 문서의 본문을 한 번의 쿼리(경로 일괄 조회) + 파일 읽기로 가져온다.

    문서마다 read_document_text 를 부르던 N+1 조회를 제거한다. 본문이 없거나
    비텍스트인 문서는 결과에서 빠진다.
    """
    if not ids:
        return {}
    qmarks = ",".join("?" * len(ids))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT id, path FROM documents WHERE id IN ({qmarks})", ids
        ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        text = _read_path_text(r["path"], max_chars=max_chars)
        if text:
            out[r["id"]] = text
    return out


def _docs_with_content(hits: list[dict[str, Any]], *, max_chars: int = 4000) -> list[dict[str, Any]]:
    """문서 메타 목록에 본문을 붙여 LLM 입력 형태로 반환(본문 없는 문서는 제외)."""
    texts = _contents_for_ids([d["id"] for d in hits], max_chars=max_chars)
    return [
        {
            "id": d["id"],
            "title": d["title"],
            "source": d["sourceName"],
            "publishedAt": d["publishedAt"],
            "content": texts[d["id"]],
        }
        for d in hits
        if d["id"] in texts
    ]


def documents_for_rag(query: str, *, limit: int = 8, topic: str | None = None,
                      source_id: str | None = None, max_chars: int = 4000) -> list[dict[str, Any]]:
    """RAG 입력: 질문 관련 문서를 본문 BM25 로 검색해 본문과 함께 반환.

    본문 매칭이 없으면 최근 문서로 폴백한다(질문이 색인 토큰과 안 겹칠 때).
    임베딩이 활성화되면 BM25+의미(dense) 하이브리드로 회수한다.
    """
    hits = hybrid_search(query, limit=limit, topic=topic, source_id=source_id)
    if not hits:
        hits = list_documents(source_id=source_id, topic=topic, limit=limit)
    return _docs_with_content(hits, max_chars=max_chars)


def documents_for_rag_multi(queries: list[str], *, limit: int = 8, topic: str | None = None,
                            source_id: str | None = None,
                            max_chars: int = 4000) -> list[dict[str, Any]]:
    """여러 질의의 RAG 문서를 한 번에 모아 중복 없이 반환(앞 질의 우선).

    질의별로 documents_for_rag 를 반복하던 것과 결과는 같고, 임베딩 호출·벡터 로드는
    1회로 줄고 겹친 문서의 본문 파일 읽기도 한 번만 한다(그라운딩: 질문+답변 2질의).
    """
    if not queries:
        return []
    seen: dict[str, dict[str, Any]] = {}
    for hits in hybrid_search_multi(queries, limit=limit, topic=topic, source_id=source_id):
        for d in hits:
            seen.setdefault(d["id"], d)
    if not seen:  # 매칭 없음 → 최근 문서 폴백(documents_for_rag 와 동일)
        for d in list_documents(source_id=source_id, topic=topic, limit=limit):
            seen.setdefault(d["id"], d)
    return _docs_with_content(list(seen.values()), max_chars=max_chars)


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
    return _docs_with_content(docs)


_HANKYUNG_TITLE = re.compile(r"\[증권사 리포트\]\s*(.+?)\((\w+)\)")


def competitor_candidates() -> list[dict[str, str]]:
    """수집된 데이터에서 분석 가능한 경쟁사 후보 {name, ticker, via} 를 도출한다.

    - sec/dart 소스: config.name(+ticker) → 추적 대상 기업.
    - 한경 컨센서스 문서: 제목 '[증권사 리포트] 회사명(코드)' 에서 회사명·종목코드.
    이름(소문자) 기준 중복 제거.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(name: str, ticker: str, via: str) -> None:
        name = (name or "").strip()
        key = name.lower()
        if not name or key in seen:
            return
        seen.add(key)
        out.append({"name": name, "ticker": (ticker or "").strip(), "via": via})

    for s in list_sources():
        if s["type"] in ("sec", "dart"):
            cfg = s.get("config") or {}
            add(str(cfg.get("name") or s["name"]), str(cfg.get("ticker") or ""), s["type"])
    # 한경 리포트 등 컨센서스 문서의 종목
    for d in list_documents(topic="컨센서스", limit=200):
        m = _HANKYUNG_TITLE.search(d.get("title", ""))
        if m:
            add(m.group(1), m.group(2), "hankyung")
    return out


def documents_for_competitor(name: str, ticker: str = "", *, limit: int = 8,
                             max_chars: int = 4000) -> list[dict[str, Any]]:
    """경쟁사 분석용 문서 검색.

    회사명·티커를 하이브리드(BM25+의미)로 검색해 해당 기업의 한경 컨센서스 리포트·IR·
    실적 문서를 관련도순으로 모은다(임베딩 비활성 시 BM25 폴백). 키워드 필터보다
    정확히 '그 회사' 문서를 끌어와 분석을 실데이터에 근거하게 한다.
    """
    query = " ".join(p for p in [name, ticker, "실적 컨센서스 목표주가 투자의견"] if p)
    return _docs_with_content(hybrid_search(query, limit=limit), max_chars=max_chars)


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
        _bump_vec_version(conn)  # 임베딩 CASCADE 삭제 → 벡터 캐시 무효화


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
        _bump_vec_version(conn)  # 임베딩 CASCADE 삭제 → 벡터 캐시 무효화
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
    return ingest_texts([{
        "title": title, "text": text, "topic": topic,
        "original_filename": original_filename, "source_name": source_name,
    }])[0]


def _compute_embeddings(bodies: list[str]) -> list[tuple[str, bytes] | None]:
    """여러 본문의 임베딩을 한 번의 배치 호출로 계산한다(비활성/실패 시 전부 None).

    문서당 API 왕복 1회 대신 배치 1회 — 배치 인제스트 처리량의 핵심.
    쓰기 트랜잭션 밖에서 호출할 것(잠금 시간 최소화).
    """
    if not bodies or not embeddings.active():
        return [None] * len(bodies)
    mat = embeddings.embed(bodies, is_query=False)
    if mat is None:
        return [None] * len(bodies)
    name = embeddings.model_name()
    return [(name, vec.tobytes()) for vec in mat]


def ingest_texts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """추출 텍스트 여러 건을 일괄 등록한다(임베딩 배치 1회 + 단일 트랜잭션).

    멱등성: (제목+본문) 해시가 이미 등록돼 있으면 삽입하지 않고 기존 문서를
    "deduped": True 로 반환한다(워커 재실행·재전송 시 중복 방지). 이때 topic 등
    메타데이터는 갱신하지 않는다.

    items 각 항목: {title, text, topic?, original_filename?, source_name?}
    반환은 입력 순서와 동일한 문서 목록.
    """
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any] | None] = [None] * len(items)
    hashes = [_content_hash(it["title"], it["text"]) for it in items]
    new_idx: list[int] = []
    dup_of: dict[int, int] = {}  # 같은 배치 안의 중복 → 첫 항목 인덱스
    first_by_hash: dict[str, int] = {}
    with _conn() as conn:
        for i, h in enumerate(hashes):
            if h in first_by_hash:
                dup_of[i] = first_by_hash[h]
                continue
            row = conn.execute(
                "SELECT * FROM documents WHERE content_sha256=? LIMIT 1", (h,)
            ).fetchone()
            if row is not None:
                doc = _row_to_document(row)
                doc["deduped"] = True
                out[i] = doc
            else:
                first_by_hash[h] = i
                new_idx.append(i)

    # 새 문서만 임베딩(배치 1회) — 네트워크/모델 호출은 트랜잭션 밖에서
    bodies = [
        _embed_doc_text(items[i]["title"], items[i].get("topic"), items[i]["text"])
        for i in new_idx
    ]
    embs = _compute_embeddings(bodies)

    # 파일 쓰기도 트랜잭션 밖에서(쓰기 잠금을 쥔 채 디스크 I/O 금지).
    # newline="" : 쓰기 시 개행 변환 방지 — 저장 바이트가 원문과 같아야
    # content_sha256 백필이 같은 해시를 재계산할 수 있다.
    prepared: list[tuple[int, str, str, Path]] = []  # (item idx, doc_id, safe_title, dest)
    for i in new_idx:
        doc_id = uuid.uuid4().hex
        safe_title = Path(items[i]["title"]).name or "untitled"
        dest = config.UPLOADS_DIR / f"{doc_id}__{safe_title}.txt"
        dest.write_text(items[i]["text"], encoding="utf-8", newline="")
        prepared.append((i, doc_id, safe_title, dest))

    try:
        with _conn() as conn:
            # 쓰기 잠금 선점: '없음 확인 → 삽입' 사이에 다른 커밋이 끼어드는
            # check-then-act 레이스를 막는다(아래 재확인과 함께 동시 중복 차단).
            conn.execute("BEGIN IMMEDIATE")
            for (i, doc_id, safe_title, dest), emb in zip(prepared, embs):
                it = items[i]
                row = conn.execute(
                    "SELECT * FROM documents WHERE content_sha256=? LIMIT 1", (hashes[i],)
                ).fetchone()
                if row is not None:  # 동시 요청이 방금 등록 — 잠금 아래 재확인으로 감지
                    doc = _row_to_document(row)
                    doc["deduped"] = True
                    out[i] = doc
                    dest.unlink(missing_ok=True)
                    continue
                src = _ensure_named_source(
                    conn, it.get("source_name") or COM_SOURCE_NAME, "upload"
                )
                conn.execute(
                    "INSERT INTO documents (id, source_id, source_name, title, filename,"
                    " path, topic, published_at, status, created_at, content_sha256)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, src["id"], src["name"], safe_title,
                     it.get("original_filename") or safe_title, str(dest),
                     it.get("topic"), _today(), "수집됨", _now(), hashes[i]),
                )
                conn.execute(
                    "UPDATE sources SET count = count + 1, last_run=? WHERE id=?",
                    (_now(), src["id"]),
                )
                _index_content(conn, doc_id, it["text"],
                               title=it["title"], topic=it.get("topic"))
                _insert_embedding(conn, doc_id, emb)
                row = conn.execute(
                    "SELECT * FROM documents WHERE id=?", (doc_id,)
                ).fetchone()
                out[i] = _row_to_document(row)
    except Exception:
        # 트랜잭션 롤백 시 미리 써 둔 파일을 회수(고아 .txt 잔존 방지)
        for _i, _d, _s, dest in prepared:
            dest.unlink(missing_ok=True)
        raise

    for i, first in dup_of.items():  # 배치 내 중복은 첫 항목의 문서를 돌려준다
        doc = dict(out[first] or {})
        doc["deduped"] = True
        out[i] = doc
    return [d for d in out if d is not None]
