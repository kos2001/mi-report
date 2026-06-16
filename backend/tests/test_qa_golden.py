"""Q&A 골든 평가셋 DB CRUD + 시드 테스트."""

from __future__ import annotations

import pytest

from app import qa_golden


def test_seed_defaults_on_init(isolated):
    assert qa_golden.count() > 0  # init_db 가 코드 기본 셋 시드
    ans = qa_golden.list_qa(kind="answerable")
    neg = qa_golden.list_qa(kind="negative")
    assert ans and neg
    assert ans[0]["expectedIds"]  # 답변형은 근거 라벨 포함


def test_add_and_delete(isolated):
    before = qa_golden.count()
    v = qa_golden.add_qa("새 질문?", kind="answerable", expected_ids=["hbm_demand"], keywords=["HBM"])
    assert qa_golden.count() == before + 1
    qa_golden.delete_qa(v["id"])
    assert qa_golden.count() == before
    with pytest.raises(KeyError):
        qa_golden.delete_qa(v["id"])


def test_invalid_inputs(isolated):
    with pytest.raises(ValueError):
        qa_golden.add_qa("q", kind="bad")
    with pytest.raises(ValueError):
        qa_golden.add_qa("  ")


def test_endpoints(client):
    listing = client.get("/qa-golden").json()
    assert listing["count"] > 0
    created = client.post("/qa-golden", json={
        "question": "엔드포인트 질문?", "kind": "answerable",
        "expectedIds": ["cxl"], "keywords": ["메모리"],
    }).json()
    assert created["expectedIds"] == ["cxl"]
    assert client.delete(f"/qa-golden/{created['id']}").status_code == 204
    assert client.post("/qa-golden", json={"question": "", "kind": "answerable"}).status_code == 422


def test_forbidden_field_and_numeric_seed(isolated):
    # add_qa 가 forbidden 을 저장/반환한다
    v = qa_golden.add_qa("수치 질문?", kind="answerable",
                         expected_ids=["competitor_q"], keywords=["29.1%"], forbidden=["29%", "30%"])
    assert v["forbidden"] == ["29%", "30%"]
    # 시드에 수치 정밀도 질문(forbidden 보유)이 포함됐다
    with_forbidden = [i for i in qa_golden.list_qa(kind="answerable") if i["forbidden"]]
    assert with_forbidden, "수치 정밀도(forbidden) 질문이 시드돼야 한다"
