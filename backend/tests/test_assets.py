"""지식 자산(생성물 누적) + 자기 개선(피드백) 테스트."""

from __future__ import annotations

import pytest

from app import assets


# ── 저장소 단위 ────────────────────────────────────────────────────────────
def test_save_and_list_and_get(client):
    a = assets.save_artifact("digest", "제1호", "1", {"items": [1, 2]})
    assets.save_artifact("topic", "HBM 수요", "HBM 수요", {"summary": "x"})
    assert assets.count_artifacts() == 2

    digests = assets.list_artifacts(kind="digest")
    assert len(digests) == 1 and digests[0]["title"] == "제1호"
    # 목록엔 payload 미포함, 단건 조회엔 포함
    assert "payload" not in digests[0]
    full = assets.get_artifact(a["id"])
    assert full["payload"]["items"] == [1, 2]


def test_artifact_versions_accumulate(client):
    assets.save_artifact("topic", "HBM 수요", "HBM 수요", {"v": 1})
    assets.save_artifact("topic", "HBM 수요", "HBM 수요", {"v": 2})
    hist = assets.list_artifacts(kind="topic", ref="HBM 수요")
    assert len(hist) == 2  # 같은 ref 라도 버전으로 누적


def test_feedback_add_and_summary(client):
    assets.add_feedback("digest", "1", "up", "좋음")
    assets.add_feedback("digest", "1", "down")
    assets.add_feedback("topic", "HBM 수요", "up")
    s = assets.feedback_summary()
    assert s == {"up": 2, "down": 1}


def test_feedback_bad_rating_raises(client):
    with pytest.raises(ValueError):
        assets.add_feedback("digest", "1", "love")


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def test_artifacts_endpoints(client):
    a = assets.save_artifact("report", "제1호 리포트", "1", {"overview": "요약"})
    r = client.get("/artifacts", params={"kind": "report"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(x["id"] == a["id"] for x in body["artifacts"])

    one = client.get(f"/artifacts/{a['id']}")
    assert one.status_code == 200
    assert one.json()["payload"]["overview"] == "요약"

    assert client.get("/artifacts/nope").status_code == 404


def test_feedback_endpoint(client):
    r = client.post("/feedback", json={"kind": "digest", "ref": "1", "rating": "up", "note": "유용"})
    assert r.status_code == 201
    assert r.json()["rating"] == "up"
    assert client.post("/feedback", json={"kind": "digest", "ref": "1", "rating": "bad"}).status_code == 422
    assert client.get("/feedback/summary").json()["up"] >= 1
