"""수집 모듈(collection.py) 단위 테스트 — 가상 테스트 셋 사용."""

from __future__ import annotations

import pytest

from app import collection
from tests.fixtures import VIRTUAL_DOCUMENTS, VIRTUAL_SOURCES


def test_seed_creates_five_default_sources(isolated):
    sources = collection.list_sources()
    assert len(sources) == 5
    names = {s["name"] for s in sources}
    assert {"EDM 수집", "Confluence 동기화", "뉴스 크롤링"} <= names


def test_create_virtual_sources(isolated):
    for spec in VIRTUAL_SOURCES:
        created = collection.create_source(spec["name"], spec["type"], spec["config"], True)
        assert created["id"]
        assert created["enabled"] is True
        assert created["config"] == spec["config"]
    assert len(collection.list_sources()) == 5 + len(VIRTUAL_SOURCES)


def test_create_source_rejects_bad_type(isolated):
    with pytest.raises(ValueError):
        collection.create_source("나쁜소스", "invalid_type", {}, True)


def test_update_source_toggle_and_rename(isolated):
    s = collection.create_source("토글대상", "news", {}, True)
    updated = collection.update_source(s["id"], enabled=False, name="이름변경")
    assert updated["enabled"] is False
    assert updated["name"] == "이름변경"


def test_update_missing_source_raises(isolated):
    with pytest.raises(KeyError):
        collection.update_source("does-not-exist", enabled=False)


def test_collect_connector_is_stub(isolated):
    news = next(s for s in collection.list_sources() if s["type"] == "news")
    result = collection.collect_source(news["id"])
    assert result["stub"] is True
    assert result["ingested"] == 0
    assert result["source"]["status"] == "정상"
    assert result["source"]["lastRun"] is not None


def test_collect_disabled_source_fails(isolated):
    news = next(s for s in collection.list_sources() if s["type"] == "news")
    collection.update_source(news["id"], enabled=False)
    with pytest.raises(ValueError):
        collection.collect_source(news["id"])


def test_collect_upload_source_not_triggerable(isolated):
    up = collection.create_source("수동", "upload", {}, True)
    with pytest.raises(ValueError):
        collection.collect_source(up["id"])


def test_upload_saves_file_and_registers_document(isolated):
    name, body, topic = VIRTUAL_DOCUMENTS[0]
    doc = collection.save_upload(name, body.encode("utf-8"), topic)
    assert doc["title"] == name
    assert doc["topic"] == topic
    assert doc["sourceName"] == "수동 업로드"
    # 파일이 실제 디스크에 저장됐는지
    saved = list((isolated / "uploads").glob(f"*__{name}"))
    assert len(saved) == 1
    assert saved[0].read_text(encoding="utf-8") == body


def test_upload_path_traversal_is_sanitized(isolated):
    doc = collection.save_upload("../../evil.txt", b"x", None)
    assert doc["filename"] == "evil.txt"
    assert "/" not in doc["filename"]


def test_documents_search_and_filter(isolated):
    for name, body, topic in VIRTUAL_DOCUMENTS:
        collection.save_upload(name, body.encode("utf-8"), topic)
    assert len(collection.list_documents()) == len(VIRTUAL_DOCUMENTS)
    # 제목 검색
    hbm = collection.list_documents(q="HBM")
    assert len(hbm) == 1 and "HBM" in hbm[0]["title"]
    # 주제 필터
    fab = collection.list_documents(topic="파운드리")
    assert len(fab) == 1 and fab[0]["topic"] == "파운드리"


def test_fts_prefix_search(isolated):
    for name, body, topic in VIRTUAL_DOCUMENTS:
        collection.save_upload(name, body.encode("utf-8"), topic)
    # 접두 검색: '파운' → '파운드리' 문서 매칭
    hits = collection.list_documents(q="파운")
    assert len(hits) == 1 and "파운드리" in hits[0]["title"]


def test_fts_special_chars_do_not_crash(isolated):
    collection.save_upload("가상_HBM_전망.txt", b"x", "HBM")
    # 따옴표 등 특수문자가 섞여도 예외 없이 동작
    assert isinstance(collection.list_documents(q='HBM "전망"'), list)
    assert collection.list_documents(q="   ") == collection.list_documents()


def test_count_documents(isolated):
    assert collection.count_documents() == 0
    for name, body, topic in VIRTUAL_DOCUMENTS:
        collection.save_upload(name, body.encode("utf-8"), topic)
    assert collection.count_documents() == len(VIRTUAL_DOCUMENTS)


def test_delete_document_removes_file(isolated):
    name, body, topic = VIRTUAL_DOCUMENTS[1]
    doc = collection.save_upload(name, body.encode("utf-8"), topic)
    saved = list((isolated / "uploads").glob(f"*__{name}"))[0]
    assert saved.exists()
    collection.delete_document(doc["id"])
    assert not saved.exists()
    assert collection.list_documents() == []


def test_delete_source_then_gone(isolated):
    s = collection.create_source("삭제대상", "broker", {}, True)
    collection.delete_source(s["id"])
    assert all(x["id"] != s["id"] for x in collection.list_sources())
    with pytest.raises(KeyError):
        collection.delete_source(s["id"])


def test_rebuild_content_fts_indexes_title(isolated):
    # 본문에 없는, 제목에만 있는 핵심어로도 재색인 후 검색되어야 한다.
    collection.ingest_text("EUV 노광 장비 도입", "선단 공정 투자 확대 동향.", topic="장비")
    n = collection.rebuild_content_fts()
    assert n >= 1
    hits = collection.search_documents("EUV 노광")
    assert any("EUV" in d["title"] for d in hits)


def test_hybrid_search_falls_back_to_bm25_when_disabled(isolated):
    # MI_EMBEDDINGS 미설정 → 임베딩 비활성 → 하이브리드가 BM25 경로로 동작.
    collection.ingest_text("HBM 시장 전망", "AI 가속기 수요로 HBM 성장", topic="HBM")
    hits = collection.hybrid_search("HBM 수요", limit=5)
    assert any("HBM" in d["title"] for d in hits)
