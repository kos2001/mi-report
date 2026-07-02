"""SQLite 커넥션 공유 헬퍼 — 스레드별 커넥션 재사용.

기존에는 모든 저장소 함수가 호출마다 connect + PRAGMA(WAL/synchronous) 를 반복했다.
WAL 전환은 파일 I/O 를 동반하므로, 같은 스레드에서는 커넥션을 재사용해 그 비용을
없앤다. 커넥션은 DB 경로별로 캐시된다(테스트가 config.COLLECTION_DB 를 tmp 경로로
바꾸면 자동으로 새 커넥션을 연다).

사용 규약: 호출부는 `with connect() as conn:` 트랜잭션 블록만 사용한다(커넥션을
직접 close 하지 않는다). sqlite3 컨텍스트 매니저는 커밋/롤백만 하고 닫지 않으므로
재사용과 안전하게 결합된다.
"""

from __future__ import annotations

import sqlite3
import threading

from . import config

_local = threading.local()


def connect() -> sqlite3.Connection:
    """현재 스레드의 재사용 커넥션을 반환한다(없으면 생성)."""
    path = str(config.COLLECTION_DB)
    conns: dict[str, sqlite3.Connection] = getattr(_local, "conns", {})
    conn = conns.get(path)
    if conn is not None:
        return conn
    config.COLLECTION_DB.parent.mkdir(parents=True, exist_ok=True)
    # timeout: 동시 쓰기(수집 병렬화) 시 잠금 대기 여유
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: 쓰기가 읽기를 블로킹하지 않게 해 동시성·처리량 개선.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conns[path] = conn
    _local.conns = conns
    return conn
