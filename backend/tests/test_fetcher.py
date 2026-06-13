"""URL 수집 테스트.

HTML→텍스트 추출은 네트워크 없이, collect 엔드포인트는 fetch_url 을 페이크로
치환해 검증한다(실제 네트워크 없음).
"""

from __future__ import annotations

import asyncio

from app import collection, fetcher

# head 에 void 태그(meta/link)를 넣어 'void 태그가 skip_depth 를 망가뜨려 본문을
# 통째로 건너뛰던' 회귀를 덮는다.
_HTML = """
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<link rel="stylesheet" href="/a.css">
<title>HBM4 채택 공식화</title>
<style>.x{color:red}</style><script>var a=1;</script></head>
<body>
  <h1>HBM4 12단</h1>
  <p>차세대 AI 가속기에 HBM4 12단이 채택됐다.</p>
  <script>track();</script>
  <p>2027년 상반기 양산 목표.</p>
</body></html>
"""


# ── 순수 추출 ─────────────────────────────────────────────────────────────
def test_extract_title_and_text():
    title, text = fetcher.extract_text_from_html(_HTML)
    assert title == "HBM4 채택 공식화"
    assert "HBM4 12단이 채택됐다" in text
    assert "2027년 상반기 양산 목표" in text


def test_extract_drops_script_and_style():
    _, text = fetcher.extract_text_from_html(_HTML)
    assert "var a=1" not in text
    assert "track()" not in text
    assert "color:red" not in text


def test_fetch_url_extracts_html():
    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = _HTML

        def raise_for_status(self):
            pass

    class FakeClient:
        async def get(self, url, **kwargs):
            return FakeResp()

    result = asyncio.run(fetcher.fetch_url(FakeClient(), "https://example.com/a"))
    assert result["url"] == "https://example.com/a"
    assert result["title"] == "HBM4 채택 공식화"
    assert "HBM4 12단이 채택됐다" in result["text"]


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
async def _fake_fetch(client, url, **kwargs):
    return {"url": url, "title": f"수집된 페이지 {url}", "text": f"본문 내용 ({url})"}


def test_collect_with_url_ingests_document(client, monkeypatch):
    # config.url 을 가진 뉴스 소스 생성
    r = client.post(
        "/collection/sources",
        json={"name": "테스트 뉴스", "type": "news", "config": {"url": "https://example.com/article"}},
    )
    sid = r.json()["id"]
    monkeypatch.setattr(fetcher, "fetch_url", _fake_fetch)

    r = client.post(f"/collection/sources/{sid}/collect")
    assert r.status_code == 200
    body = r.json()
    assert body["stub"] is False
    assert body["ingested"] == 1
    assert body["documents"][0]["sourceName"] == "테스트 뉴스"

    # 실제 문서로 저장되어 목록·본문 조회 가능
    docs = client.get("/collection/documents").json()["documents"]
    assert any(d["sourceName"] == "테스트 뉴스" for d in docs)


def test_collect_uses_name_as_url_fallback(client, monkeypatch):
    # 이름이 URL 처럼 보이면 그것을 수집 대상으로
    r = client.post("/collection/sources", json={"name": "www.naver.com", "type": "news"})
    sid = r.json()["id"]
    captured = {}

    async def capture_fetch(c, url, **kw):
        captured["url"] = url
        return {"url": url, "title": "네이버", "text": "본문"}

    monkeypatch.setattr(fetcher, "fetch_url", capture_fetch)
    r = client.post(f"/collection/sources/{sid}/collect")
    assert r.status_code == 200
    assert captured["url"] == "https://www.naver.com"  # 스킴 자동 보정


def test_collect_without_url_is_stub(client):
    # URL 없는 소스(이름에 공백)는 기존 스텁 동작
    r = client.post("/collection/sources", json={"name": "수동 뉴스 소스", "type": "news"})
    sid = r.json()["id"]
    r = client.post(f"/collection/sources/{sid}/collect")
    assert r.status_code == 200
    body = r.json()
    assert body["stub"] is True
    assert body["ingested"] == 0


def test_collect_all_urls_fail_returns_502(client, monkeypatch):
    r = client.post(
        "/collection/sources",
        json={"name": "깨진 소스", "type": "news", "config": {"url": "https://example.com/x"}},
    )
    sid = r.json()["id"]

    async def empty_fetch(c, url, **kw):
        return {"url": url, "title": "", "text": ""}  # 빈 본문

    monkeypatch.setattr(fetcher, "fetch_url", empty_fetch)
    r = client.post(f"/collection/sources/{sid}/collect")
    assert r.status_code == 502


def test_source_urls_helper():
    assert collection.source_urls({"name": "x", "config": {"url": "http://a.com"}}) == ["http://a.com"]
    assert collection.source_urls({"name": "www.naver.com", "config": {}}) == ["https://www.naver.com"]
    assert collection.source_urls({"name": "뉴스 크롤링", "config": {}}) == []
    assert collection.source_urls(
        {"name": "x", "config": {"urls": ["a.com", "https://b.com"]}}
    ) == ["https://a.com", "https://b.com"]
