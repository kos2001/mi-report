"""FastAPI 엔드포인트 통합 테스트 (TestClient, 가상 테스트 셋).

게이트웨이 프록시(/chat·/runs·/gateway/*)는 외부 의존이라 여기서 제외하고,
결정적인 수집/프로파일/헬스 경로만 검증한다.
"""

from __future__ import annotations

import io

from tests.fixtures import VIRTUAL_DOCUMENTS, VIRTUAL_SOURCES


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_profiles_endpoint(client):
    r = client.get("/profiles")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == "hermes"
    assert any(p["name"] == "hermes" for p in body["profiles"])


def test_sources_seeded(client):
    r = client.get("/collection/sources")
    assert r.status_code == 200
    assert len(r.json()["sources"]) == 5


def test_source_lifecycle(client):
    spec = VIRTUAL_SOURCES[0]
    # create
    r = client.post("/collection/sources", json={"name": spec["name"], "type": spec["type"], "config": spec["config"]})
    assert r.status_code == 201
    sid = r.json()["id"]
    # patch disable
    r = client.patch(f"/collection/sources/{sid}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    # collect on disabled -> 400
    r = client.post(f"/collection/sources/{sid}/collect")
    assert r.status_code == 400
    # re-enable + collect -> stub ok
    client.patch(f"/collection/sources/{sid}", json={"enabled": True})
    r = client.post(f"/collection/sources/{sid}/collect")
    assert r.status_code == 200 and r.json()["stub"] is True
    # delete
    assert client.delete(f"/collection/sources/{sid}").status_code == 204


def test_create_source_bad_type_400(client):
    r = client.post("/collection/sources", json={"name": "x", "type": "nope"})
    assert r.status_code == 422  # pydantic Literal 검증


def test_upload_and_documents_flow(client):
    # 가상 문서 업로드
    for name, body, topic in VIRTUAL_DOCUMENTS:
        r = client.post(
            "/collection/upload",
            files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
            data={"topic": topic},
        )
        assert r.status_code == 201
        assert r.json()["topic"] == topic

    # 전체 목록
    r = client.get("/collection/documents")
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert len(docs) == len(VIRTUAL_DOCUMENTS)

    # 검색
    r = client.get("/collection/documents", params={"q": "HBM"})
    assert len(r.json()["documents"]) == 1

    # 삭제
    target = docs[0]["id"]
    assert client.delete(f"/collection/documents/{target}").status_code == 204
    assert len(client.get("/collection/documents").json()["documents"]) == len(VIRTUAL_DOCUMENTS) - 1


def test_delete_missing_returns_404(client):
    assert client.delete("/collection/sources/nope").status_code == 404
    assert client.delete("/collection/documents/nope").status_code == 404


def test_com_ingest_endpoint_registers_extracted_text(client):
    """COM 워커가 보내는 추출 텍스트 등록 경로."""
    r = client.post(
        "/collection/ingest",
        json={
            "title": "가상_DRM문서_요약",
            "text": "DRM 해제 상태로 추출된 본문 (테스트용 허구).",
            "topic": "HBM",
            "original_filename": "가상_DRM문서.docx",
        },
    )
    assert r.status_code == 201
    doc = r.json()
    assert doc["title"] == "가상_DRM문서_요약"
    assert doc["topic"] == "HBM"
    assert "COM 인제스트" in doc["sourceName"]

    # 문서 목록 + 검색에 반영
    found = client.get("/collection/documents", params={"q": "DRM문서"}).json()["documents"]
    assert len(found) == 1
