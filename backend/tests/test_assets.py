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


def test_delete_artifact(client):
    a = assets.save_artifact("digest", "제1호", "1", {"items": [1, 2]})
    assert assets.count_artifacts() == 1
    assets.delete_artifact(a["id"])
    assert assets.count_artifacts() == 0
    with pytest.raises(KeyError):
        assets.get_artifact(a["id"])


def test_delete_artifact_missing_raises(isolated):
    with pytest.raises(KeyError):
        assets.delete_artifact("nope")


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


# ── 자기개선 loop: 품질 집계 + 피드백 재반영 ─────────────────────────────────
def test_save_artifact_stores_quality_counts(client):
    a = assets.save_artifact("digest", "제1호", "1", {
        "ungroundedNumbers": ["999", "888"], "unsupportedClaims": ["근거 없는 주장"],
    })
    full = assets.get_artifact(a["id"])
    assert full["ungroundedCount"] == 2
    assert full["unsupportedCount"] == 1


def test_save_artifact_reads_report_style_unsupported_field(client):
    # report.py 는 unsupportedClaims 대신 overviewUnsupportedClaims 를 쓴다.
    a = assets.save_artifact("report", "제1호 리포트", "1", {
        "ungroundedNumbers": [], "overviewUnsupportedClaims": ["a", "b"],
    })
    full = assets.get_artifact(a["id"])
    assert full["ungroundedCount"] == 0
    assert full["unsupportedCount"] == 2


def test_save_artifact_zero_counts_when_clean(client):
    a = assets.save_artifact("digest", "제1호", "1", {"ungroundedNumbers": [], "unsupportedClaims": []})
    full = assets.get_artifact(a["id"])
    assert full["ungroundedCount"] == 0 and full["unsupportedCount"] == 0


def test_list_artifacts_includes_quality_counts(client):
    assets.save_artifact("digest", "제1호", "1", {"ungroundedNumbers": ["1"], "unsupportedClaims": []})
    items = assets.list_artifacts(kind="digest")
    assert items[0]["ungroundedCount"] == 1 and items[0]["unsupportedCount"] == 0


def test_feedback_summary_by_kind(client):
    assets.add_feedback("digest", "1", "up")
    assets.add_feedback("digest", "1", "down")
    assets.add_feedback("topic", "HBM", "up")
    s = assets.feedback_summary_by_kind()
    assert s["digest"] == {"up": 1, "down": 1}
    assert s["topic"] == {"up": 1, "down": 0}


def test_recent_negative_feedback_returns_notes_newest_first(client):
    assets.add_feedback("digest", "1", "down", "수치가 틀림")
    assets.add_feedback("digest", "1", "up", "좋음")  # up 은 제외
    assets.add_feedback("digest", "2", "down", "")  # 빈 메모는 제외
    assets.add_feedback("digest", "3", "down", "출처 누락")
    notes = assets.recent_negative_feedback("digest", limit=5)
    assert notes == ["출처 누락", "수치가 틀림"]


def test_recent_negative_feedback_respects_limit(client):
    for i in range(5):
        assets.add_feedback("digest", str(i), "down", f"이유{i}")
    assert len(assets.recent_negative_feedback("digest", limit=2)) == 2


def test_quality_summary_aggregates_per_kind(client):
    assets.save_artifact("digest", "제1호", "1", {"ungroundedNumbers": ["1", "2"], "unsupportedClaims": []})
    assets.save_artifact("digest", "제2호", "2", {"ungroundedNumbers": [], "unsupportedClaims": []})
    assets.add_feedback("digest", "1", "down", "수치 오류")
    assets.add_feedback("digest", "2", "up")

    s = assets.quality_summary()
    digest_stats = s["byKind"]["digest"]
    assert digest_stats["count"] == 2
    assert digest_stats["flaggedCount"] == 1
    assert digest_stats["up"] == 1 and digest_stats["down"] == 1
    assert len(s["recentFlagged"]) == 1
    assert s["recentFlagged"][0]["title"] == "제1호"


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


def test_artifacts_delete_endpoint(client):
    a = assets.save_artifact("report", "제1호 리포트", "1", {"overview": "요약"})
    r = client.delete(f"/artifacts/{a['id']}")
    assert r.status_code == 204
    assert client.get(f"/artifacts/{a['id']}").status_code == 404
    assert client.delete("/artifacts/nope").status_code == 404


def test_quality_summary_endpoint(client):
    assets.save_artifact("digest", "제1호", "1", {"ungroundedNumbers": ["1"], "unsupportedClaims": []})
    assets.add_feedback("digest", "1", "down", "수치 오류")
    r = client.get("/quality/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["byKind"]["digest"]["flaggedCount"] == 1
    assert body["byKind"]["digest"]["down"] == 1
    assert body["recentFlagged"][0]["title"] == "제1호"


def test_feedback_endpoint(client):
    r = client.post("/feedback", json={"kind": "digest", "ref": "1", "rating": "up", "note": "유용"})
    assert r.status_code == 201
    assert r.json()["rating"] == "up"
    assert client.post("/feedback", json={"kind": "digest", "ref": "1", "rating": "bad"}).status_code == 422
    assert client.get("/feedback/summary").json()["up"] >= 1
