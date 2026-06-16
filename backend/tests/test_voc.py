"""VOC(Voice of Customer) CRUD 테스트."""

from __future__ import annotations

import pytest

from app import voc


def test_add_and_list(isolated):
    voc.add_voc("A고객사", "HBM 납기 문의", channel="영업", sentiment="중립", priority="상")
    voc.add_voc("B고객사", "리포트 좋았음", channel="CS", sentiment="긍정", priority="하")
    items = voc.list_voc()
    assert len(items) == 2
    assert items[0]["status"] == "신규"
    # 감정 필터
    assert len(voc.list_voc(sentiment="긍정")) == 1


def test_invalid_values_are_normalized(isolated):
    v = voc.add_voc("C", "내용", channel="없는채널", sentiment="짱좋음", priority="최상")
    assert v["channel"] == "기타" and v["sentiment"] == "중립" and v["priority"] == "중"


def test_requires_customer_and_content(isolated):
    with pytest.raises(ValueError):
        voc.add_voc("", "내용")
    with pytest.raises(ValueError):
        voc.add_voc("고객", "  ")


def test_update_status_and_summary(isolated):
    v = voc.add_voc("A", "문의")
    voc.update_status(v["id"], "완료")
    assert voc.list_voc(status="완료")[0]["id"] == v["id"]
    with pytest.raises(ValueError):
        voc.update_status(v["id"], "이상한상태")
    summ = voc.voc_summary()
    assert summ["total"] == 1 and summ["byStatus"].get("완료") == 1


def test_delete(isolated):
    v = voc.add_voc("A", "문의")
    voc.delete_voc(v["id"])
    assert voc.list_voc() == []
    with pytest.raises(KeyError):
        voc.delete_voc(v["id"])


def test_voc_endpoints(client):
    created = client.post("/voc", json={"customer": "A고객사", "content": "납기 문의",
                                        "channel": "영업", "sentiment": "부정", "priority": "상"}).json()
    assert created["status"] == "신규"
    listing = client.get("/voc").json()
    assert listing["summary"]["total"] == 1
    assert client.patch(f"/voc/{created['id']}", json={"status": "검토중"}).json()["status"] == "검토중"
    assert client.delete(f"/voc/{created['id']}").status_code == 204
    assert client.post("/voc", json={"customer": "", "content": "x"}).status_code == 422  # pydantic min_length
    assert client.post("/voc", json={"customer": "A", "content": "   "}).status_code == 400  # add_voc 검증
