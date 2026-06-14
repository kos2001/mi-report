"""테스트 격리 설정.

각 테스트는 임시 데이터 디렉토리(SQLite + 업로드)를 사용해 실제 데이터를 건드리지 않는다.
config.COLLECTION_DB / UPLOADS_DIR 를 tmp 경로로 패치한 뒤 스키마를 새로 만든다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import collection, config
from app.main import app


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "COLLECTION_DB", data_dir / "collection.db")
    monkeypatch.setattr(config, "UPLOADS_DIR", data_dir / "uploads")
    monkeypatch.setattr(config, "DIGESTS_DIR", data_dir / "digests")
    collection.init_db()  # 빈 tmp DB 에 스키마 + 기본 소스 시드
    return data_dir


@pytest.fixture
def client(isolated):
    # startup 훅이 init_db 를 다시 부르지만 동일 tmp DB 라 안전(IF NOT EXISTS)
    with TestClient(app) as c:
        yield c
