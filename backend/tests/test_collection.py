"""수집 모듈(collection.py) 단위 테스트 — 가상 테스트 셋 사용."""

from __future__ import annotations

import pytest

from app import collection
from tests.fixtures import VIRTUAL_DOCUMENTS, VIRTUAL_SOURCES


def test_seed_creates_default_sources(isolated):
    sources = collection.list_sources()
    assert len(sources) == 6
    names = {s["name"] for s in sources}
    assert {"EDM 수집", "Confluence 동기화", "뉴스 크롤링", "경쟁사 IR · SEC"} <= names


def test_create_virtual_sources(isolated):
    for spec in VIRTUAL_SOURCES:
        created = collection.create_source(spec["name"], spec["type"], spec["config"], True)
        assert created["id"]
        assert created["enabled"] is True
        assert created["config"] == spec["config"]
    assert len(collection.list_sources()) == 6 + len(VIRTUAL_SOURCES)


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


def test_ingest_texts_batch_and_dedup(isolated):
    """배치 등록 + (제목+본문) 해시 멱등성: 재전송·배치 내 중복은 기존 문서 반환."""
    before = collection.count_documents()
    docs = collection.ingest_texts([
        {"title": "A", "text": "본문 A"},
        {"title": "B", "text": "본문 B"},
        {"title": "A", "text": "본문 A"},  # 같은 배치 안의 중복
    ])
    assert len(docs) == 3
    assert docs[2]["deduped"] is True and docs[2]["id"] == docs[0]["id"]
    assert collection.count_documents() == before + 2

    again = collection.ingest_text("A", "본문 A")  # 재전송(워커 재실행 모사)
    assert again["deduped"] is True and again["id"] == docs[0]["id"]
    assert collection.count_documents() == before + 2

    other = collection.ingest_text("A", "본문이 달라진 A")  # 내용 변경 → 새 문서
    assert "deduped" not in other
    assert collection.count_documents() == before + 3


def test_ingest_texts_single_embedding_batch(isolated, monkeypatch):
    """배치 인제스트는 문서당 임베딩 호출이 아니라 배치 1회 호출이어야 한다."""
    import numpy as np

    from app import embeddings

    calls: list[int] = []

    def fake_embed(texts, is_query=False):
        calls.append(len(texts))
        return np.ones((len(texts), 4), dtype="float32")

    monkeypatch.setattr(embeddings, "active", lambda: True)
    monkeypatch.setattr(embeddings, "model_name", lambda: "test-model")
    monkeypatch.setattr(embeddings, "embed", fake_embed)

    collection.ingest_texts([{"title": f"T{i}", "text": f"본문 {i}"} for i in range(5)])
    assert calls == [5]


def test_content_hash_backfill_matches_raw_reingest(isolated):
    """백필 해시는 원문(개행·공백 무변형) 기준이어야 재전송 dedup 과 맞는다.

    Word COM 텍스트는 '\\r' 문단 구분과 말미 공백을 포함한다 — 정규화된
    텍스트로 백필하면 레거시 문서 dedup 이 영영 안 맞는 회귀를 방지.
    """
    text = "문단1\r문단2\r\n끝  \n"
    doc = collection.ingest_text("리포트", text)
    with collection._conn() as conn:  # 마이그레이션 이전 상태(해시 없음)로 되돌림
        conn.execute("UPDATE documents SET content_sha256=NULL WHERE id=?", (doc["id"],))
        collection._migrate_content_hash(conn)
    again = collection.ingest_text("리포트", text)
    assert again.get("deduped") is True and again["id"] == doc["id"]


def test_ingest_texts_removes_files_on_failure(isolated, monkeypatch):
    """트랜잭션 실패(롤백) 시 미리 써 둔 .txt 가 고아로 남지 않아야 한다."""
    from app import config

    def boom(*a, **k):
        raise RuntimeError("소스 조회 실패")

    monkeypatch.setattr(collection, "_ensure_named_source", boom)
    with pytest.raises(RuntimeError):
        collection.ingest_texts([{"title": "X", "text": "본문"}])
    assert not list(config.UPLOADS_DIR.glob("*X*"))


def test_embed_doc_text_caps_length(isolated):
    """임베딩 입력은 상한까지만 자른다(모델이 앞부분만 쓰므로 비용·지연 절감)."""
    body = collection._embed_doc_text("제목", None, "가" * (collection.EMBED_MAX_CHARS * 2))
    assert len(body) == collection.EMBED_MAX_CHARS
    assert body.startswith("제목")


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


def test_hybrid_search_falls_back_to_bm25_on_embedding_error(isolated, monkeypatch):
    # 임베딩이 활성이지만 호출이 실패하면 BM25(어휘) 결과로 폴백해야 한다.
    from app import embeddings
    collection.ingest_text("HBM4 시장 전망", "AI 가속기 수요로 HBM 성장", topic="HBM")
    monkeypatch.setattr(embeddings, "active", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("embedding endpoint down")

    monkeypatch.setattr(embeddings, "embed", boom)
    hits = collection.hybrid_search("HBM4 수요", limit=5)
    assert any("HBM4" in d["title"] for d in hits)  # 폴백으로 회수


def _stub_embeddings(monkeypatch, vectors: dict[str, list[float]], dim: int = 4):
    """임베딩을 결정적 로컬 스텁으로 대체하고 호출 배치 크기를 기록해 반환한다.

    vectors: 텍스트 접두어 → 벡터. 매칭 없으면 영벡터에 가까운 기본값.
    """
    import numpy as np

    from app import embeddings

    calls: list[int] = []

    def fake_embed(texts, is_query=False):
        calls.append(len(texts))
        out = []
        for t in texts:
            vec = next((v for k, v in vectors.items() if t.startswith(k)), None)
            out.append(vec if vec else [1e-3] * dim)
        return np.asarray(out, dtype="float32")

    monkeypatch.setattr(embeddings, "active", lambda: True)
    monkeypatch.setattr(embeddings, "model_name", lambda: "test-model")
    monkeypatch.setattr(embeddings, "embed", fake_embed)
    return calls


def test_add_crawled_documents_single_embedding_batch(isolated, monkeypatch):
    """커넥터 일괄 수집은 문서당 임베딩 왕복이 아니라 배치 1회여야 한다."""
    calls = _stub_embeddings(monkeypatch, {})
    src = collection.create_source("뉴스 배치", "news", {"url": "https://x/y"}, True)
    items = [{"title": f"페이지 {i}", "text": f"본문 {i}", "url": f"https://x/{i}"}
             for i in range(6)]
    docs = collection.add_crawled_documents(src["id"], src["name"], items)
    assert [d["title"] for d in docs] == [f"페이지 {i}" for i in range(6)]
    assert calls == [6]  # 배치 1회
    assert collection.get_source(src["id"])["count"] == 6  # 카운트도 일괄 반영
    # 본문은 URL 헤더와 함께 저장되고 검색 색인에도 들어간다
    assert "본문 3" in (collection.read_document_text(docs[3]["id"]) or "")
    assert any(d["id"] == docs[3]["id"] for d in collection.search_documents("페이지"))


def test_add_crawled_documents_rolls_back_files_on_failure(isolated, monkeypatch):
    """트랜잭션 실패 시 미리 써 둔 .txt 가 고아로 남지 않아야 한다."""
    from app import config

    src = collection.create_source("뉴스 실패", "news", {"url": "https://x/y"}, True)
    monkeypatch.setattr(collection, "_index_content",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("색인 실패")))
    with pytest.raises(RuntimeError):
        collection.add_crawled_documents(
            src["id"], src["name"], [{"title": "T", "text": "본문", "url": "https://x/1"}]
        )
    assert not list(config.UPLOADS_DIR.glob("*__T.txt"))


def test_hybrid_search_multi_uses_one_embedding_call(isolated, monkeypatch):
    """질의 N개를 검색해도 임베딩 호출은 배치 1회여야 한다(원격 왕복 절감)."""
    calls = _stub_embeddings(monkeypatch, {})
    collection.ingest_text("HBM 시장 전망", "AI 가속기 수요로 HBM 성장", topic="HBM")
    calls.clear()  # 적재 시의 문서 임베딩 호출 제외
    out = collection.hybrid_search_multi(["HBM 수요", "파운드리 가격", "메모리 재고"], limit=5)
    assert len(out) == 3
    assert calls == [3]


def test_documents_for_rag_multi_dedups_and_prefers_first_query(isolated, monkeypatch):
    """여러 질의 결과를 앞 질의 우선으로 중복 없이 합친다(본문도 1회만 읽음)."""
    _stub_embeddings(monkeypatch, {})
    collection.ingest_text("HBM 시장 전망", "AI 가속기 수요로 HBM 성장", topic="HBM")
    collection.ingest_text("파운드리 가동률", "선단 공정 가동률 상승", topic="파운드리")
    docs = collection.documents_for_rag_multi(["HBM 수요", "파운드리 가동률"], limit=5)
    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids))  # 중복 없음
    assert "HBM" in docs[0]["title"]  # 첫 질의 결과가 앞에


def test_vector_cache_invalidated_by_delete(isolated, monkeypatch):
    """벡터 캐시가 삭제된 문서를 계속 회수하면 안 된다(캐시 무효화 회귀 가드)."""
    _stub_embeddings(monkeypatch, {"HBM": [1.0, 0.0, 0.0, 0.0]})
    doc = collection.ingest_text("HBM 시장 전망", "AI 가속기 수요로 HBM 성장", topic="HBM")
    assert any(d["id"] == doc["id"] for d in collection.hybrid_search("HBM 수요", limit=5))
    collection.delete_document(doc["id"])
    assert all(d["id"] != doc["id"] for d in collection.hybrid_search("HBM 수요", limit=5))


def test_vector_cache_sees_newly_ingested_doc(isolated, monkeypatch):
    """캐시 이후에 적재된 문서도 dense 경로에서 회수돼야 한다."""
    _stub_embeddings(monkeypatch, {"질의": [1.0, 0.0, 0.0, 0.0], "신규": [1.0, 0.0, 0.0, 0.0]})
    collection.ingest_text("기존 문서", "무관한 본문")
    collection.hybrid_search("질의", limit=5)  # 캐시 채우기
    fresh = collection.ingest_text("신규 문서", "신규 본문")
    hits = collection.hybrid_search("질의", limit=5)  # 어휘로는 안 걸리는 질의
    assert any(d["id"] == fresh["id"] for d in hits)


def test_vector_cache_invalidated_when_row_counts_repeat(isolated, monkeypatch):
    """마지막 행 삭제 후 삽입 — (행 수, MAX(rowid)) 가 같은 값으로 되돌아오는 경우.

    이 경우까지 무효화하는 것이 쓰기 버전 카운터의 존재 이유다(캐시가 삭제된 문서를
    돌려주거나 새 문서를 놓치면 회귀).
    """
    _stub_embeddings(monkeypatch, {"질의": [1.0, 0.0, 0.0, 0.0], "신규": [1.0, 0.0, 0.0, 0.0]})
    collection.ingest_text("문서 A", "본문 A")
    gone = collection.ingest_text("문서 B", "본문 B")
    collection.hybrid_search("질의", limit=5)  # 캐시 채우기 (행 2, MAX(rowid) 2)
    collection.delete_document(gone["id"])
    fresh = collection.ingest_text("신규 문서", "신규 본문")  # 다시 행 2, MAX(rowid) 2
    ids = [d["id"] for d in collection.hybrid_search("질의", limit=5)]
    assert fresh["id"] in ids and gone["id"] not in ids


def test_read_path_text_prefix_read(isolated):
    """max_chars 는 파일 앞부분만 읽는다 — 멀티바이트 경계가 깨지지 않고,
    바이너리는 계속 None(비텍스트 판정)."""
    from app import config

    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    text_file = config.UPLOADS_DIR / "long.txt"
    text_file.write_text("가나다라마바사" * 500, encoding="utf-8")
    out = collection._read_path_text(str(text_file), max_chars=10)
    assert out == "가나다라마바사가나다"  # 잘린 경계에 깨진 문자 없음

    bin_file = config.UPLOADS_DIR / "blob.docx"
    bin_file.write_bytes(b"PK\x03\x04" + bytes(range(128, 256)) * 20)
    assert collection._read_path_text(str(bin_file), max_chars=4000) is None
    assert collection._read_path_text(str(config.UPLOADS_DIR / "없음.txt"), max_chars=10) is None


def test_documents_for_competitor_finds_company_docs(isolated):
    # 한경 리포트 스타일 문서 + 무관 문서
    collection.ingest_text("[증권사 리포트] 삼성물산(028260) 지분가치 재평가",
                           "삼성물산 목표주가 상향, 투자의견 매수 유지. 배당 확대.", topic="컨센서스")
    collection.ingest_text("[증권사 리포트] SK스퀘어(402340) 동향",
                           "SK스퀘어 SK하이닉스 지분가치 부각.", topic="컨센서스")
    docs = collection.documents_for_competitor("삼성물산", "028260", limit=5)
    assert any("삼성물산" in d["title"] for d in docs)  # 그 회사 문서를 회수


def test_competitor_candidates_from_data(isolated):
    # 시드(Qualcomm)와 겹치지 않는 회사로 — config.ticker 가 후보에 실리는지 확인
    collection.create_source("SEC AVGO", "sec", {"cik": "0001730168", "name": "Broadcom", "ticker": "AVGO"}, True)
    collection.ingest_text("[증권사 리포트] 삼성물산(028260) 지분가치", "내용", topic="컨센서스")
    cands = collection.competitor_candidates()
    by = {c["name"]: c for c in cands}
    assert "Broadcom" in by and by["Broadcom"]["ticker"] == "AVGO"
    assert "삼성물산" in by and by["삼성물산"]["ticker"] == "028260"
    assert "Qualcomm" in by  # 시드된 SEC 도 포함
