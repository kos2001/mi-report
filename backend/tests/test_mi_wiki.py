"""MI Report LLM Wiki 증분 갱신·컨텍스트 테스트."""

from __future__ import annotations

from app import mi_wiki


def _payload(week: str, title: str, *, tag: str = "HBM", generated_at: str = "2026-08-20 10:00"):
    return {
        "week": week,
        "period": "주간",
        "generatedAt": generated_at,
        "sourceDocCount": 2,
        "items": [{
            "title": title,
            "source": "증권사",
            "publishedAt": "2026-08-20",
            "summary": f"{title} 요약",
            "slsiRelevance": "컨트롤러 기회",
            "demandImpact": "수요 증가",
            "risk": "단일 출처",
            "impact": "high",
            "tags": [tag],
        }],
        "unsupportedClaims": [],
    }


def test_init_wiki_creates_schema_and_meta(isolated):
    root = mi_wiki.init_wiki()
    assert root is not None
    assert (root / "SCHEMA.md").exists()
    assert (root / "index.md").exists()
    assert (root / "log.md").exists()


def test_update_digest_replaces_same_week_and_accumulates_other_weeks(isolated):
    root = mi_wiki.wiki_path()
    first = mi_wiki.update_digest(_payload("2026년 33주차", "이전 전망"))
    second = mi_wiki.update_digest(_payload("2026년 33주차", "수정 전망", generated_at="2026-08-20 11:00"))
    mi_wiki.update_digest(_payload("2026년 34주차", "이번 전망"))

    assert first is not None and second is not None
    assert first == second
    assert "수정 전망" in second.read_text()
    assert "이전 전망" not in second.read_text()
    weekly = list((root / "weekly").glob("*.md"))
    assert len(weekly) == 2
    index = (root / "index.md").read_text()
    assert "2026년 33주차" in index and "2026년 34주차" in index


def test_update_digest_builds_concept_page_with_provenance(isolated):
    mi_wiki.update_digest(_payload("2026년 34주차", "HBM4 채택"))
    concept = mi_wiki.wiki_path() / "concepts" / "hbm.md"
    text = concept.read_text()
    assert "HBM4 채택" in text
    assert "증권사 / 2026-08-20" in text
    assert "[[weekly/2026-W34|2026년 34주차]]" in text


def test_replacing_week_removes_stale_concept_page(isolated):
    mi_wiki.update_digest(_payload("2026년 34주차", "HBM4 채택", tag="HBM"))
    stale = mi_wiki.wiki_path() / "concepts" / "hbm.md"
    assert stale.exists()

    mi_wiki.update_digest(_payload("2026년 34주차", "온디바이스 AI", tag="AI"))

    assert not stale.exists()
    assert (mi_wiki.wiki_path() / "concepts" / "ai.md").exists()


def test_digest_context_excludes_current_week(isolated):
    mi_wiki.update_digest(_payload("2026년 33주차", "이전 전망"))
    mi_wiki.update_digest(_payload("2026년 34주차", "현재 전망"))

    context = mi_wiki.digest_context(current_week="2026년 34주차")
    assert "이전 전망" in context
    assert "현재 전망" not in context


def test_wiki_can_be_disabled(isolated, monkeypatch):
    monkeypatch.setenv("MI_WIKI_ENABLED", "0")
    assert mi_wiki.init_wiki() is None
    assert mi_wiki.update_digest(_payload("2026년 34주차", "비활성")) is None
    assert mi_wiki.digest_context(current_week="2026년 34주차") == ""
