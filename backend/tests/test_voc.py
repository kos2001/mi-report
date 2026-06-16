"""VOC(이 서비스에 대한 사용자 피드백) CRUD 테스트."""

from __future__ import annotations

import pytest

from app import voc


def test_add_and_list(isolated):
    voc.add_voc("사용자A", "다이제스트 메일 발송이 안 돼요", area="다이제스트",
                category="버그", sentiment="부정", priority="상")
    voc.add_voc("사용자B", "리포트 템플릿 좋아요", area="리포트",
                category="칭찬", sentiment="긍정", priority="하")
    items = voc.list_voc()
    assert len(items) == 2
    assert items[0]["status"] == "신규"
    assert items[0]["reporter"] and items[0]["area"] and items[0]["category"]
    assert len(voc.list_voc(sentiment="긍정")) == 1


def test_invalid_values_are_normalized(isolated):
    v = voc.add_voc("U", "내용", area="없는영역", category="없는유형",
                    sentiment="짱좋음", priority="최상")
    assert v["area"] == "기타" and v["category"] == "문의"
    assert v["sentiment"] == "중립" and v["priority"] == "중"


def test_requires_reporter_and_content(isolated):
    with pytest.raises(ValueError):
        voc.add_voc("", "내용")
    with pytest.raises(ValueError):
        voc.add_voc("사용자", "  ")


def test_update_status_and_summary(isolated):
    v = voc.add_voc("U", "문서 Q&A 개선 요청", area="문서Q&A", category="기능요청")
    voc.update_status(v["id"], "완료")
    assert voc.list_voc(status="완료")[0]["id"] == v["id"]
    with pytest.raises(ValueError):
        voc.update_status(v["id"], "이상한상태")
    summ = voc.voc_summary()
    assert summ["total"] == 1 and summ["byStatus"].get("완료") == 1


def test_delete(isolated):
    v = voc.add_voc("U", "문의")
    voc.delete_voc(v["id"])
    assert voc.list_voc() == []
    with pytest.raises(KeyError):
        voc.delete_voc(v["id"])


def test_voc_endpoints(client):
    created = client.post("/voc", json={
        "reporter": "사용자A", "content": "수집 트리거가 느려요",
        "area": "데이터수집", "category": "버그", "sentiment": "부정", "priority": "상",
    }).json()
    assert created["status"] == "신규" and created["area"] == "데이터수집"
    listing = client.get("/voc").json()
    assert listing["summary"]["total"] == 1
    assert client.patch(f"/voc/{created['id']}", json={"status": "검토중"}).json()["status"] == "검토중"
    assert client.delete(f"/voc/{created['id']}").status_code == 204
    assert client.post("/voc", json={"reporter": "", "content": "x"}).status_code == 422
    assert client.post("/voc", json={"reporter": "U", "content": "   "}).status_code == 400
