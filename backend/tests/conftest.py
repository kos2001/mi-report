"""테스트 격리 설정.

각 테스트는 임시 데이터 디렉토리(SQLite + 업로드)를 사용해 실제 데이터를 건드리지 않는다.
config.COLLECTION_DB / UPLOADS_DIR 를 tmp 경로로 패치한 뒤 스키마를 새로 만든다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import collection, config
from app.main import app


@pytest.fixture(autouse=True)
def _offline_llm_env(monkeypatch):
    """테스트는 네트워크 없이 결정적으로 — 임베딩/리랭크/LLM 설정을 안전값으로 고정.

    시작 훅(load_profile)이 실제 프로파일 .env(openrouter/rerank/키)를 로드해도
    '이미 있는 값 보존' 규칙 때문에 여기서 설정한 값이 유지된다.
    개별 테스트가 필요하면 자체 monkeypatch 로 덮어쓴다.
    """
    monkeypatch.setenv("MI_EMBED_BACKEND", "fastembed")  # 로컬(네트워크 X)
    monkeypatch.setenv("MI_RERANK_MODEL", "")            # 리랭크 비활성 → LLM 폴백
    monkeypatch.setenv("OPENROUTER_API_KEY", "")         # openrouter 임베딩/리랭크 비활성
    monkeypatch.setenv("MI_EMBEDDINGS", "")              # 임베딩 기본 off(필요 테스트가 켬)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "COLLECTION_DB", data_dir / "collection.db")
    monkeypatch.setattr(config, "UPLOADS_DIR", data_dir / "uploads")
    monkeypatch.setenv("MI_WIKI_ENABLED", "1")
    monkeypatch.setenv("MI_WIKI_PATH", str(data_dir / "wiki"))
    collection.init_db()  # 빈 tmp DB 에 스키마 + 기본 소스 시드
    return data_dir


@pytest.fixture
def client(isolated):
    # startup 훅이 init_db 를 다시 부르지만 동일 tmp DB 라 안전(IF NOT EXISTS)
    with TestClient(app) as c:
        yield c
