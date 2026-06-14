"""Confluence 커넥터 테스트.

페이지 파싱은 네트워크 없이, 수집 흐름은 fetch_pages 를 페이크로 치환해 검증.
"""

from __future__ import annotations

import asyncio

from app import collection, confluence, pipeline, profiles

_PAYLOAD = {
    "results": [
        {
            "id": "111",
            "title": "HBM4 메모",
            "body": {"storage": {"value": "<h2>요약</h2><p>HBM4 12단 채택 공식화.</p>"}},
            "_links": {"webui": "/spaces/MI/pages/111/HBM4"},
        },
        {
            "id": "222",
            "title": "경쟁사 콜",
            "body": {"storage": {"value": "<p>프리미엄 AP ASP 상승 지속.</p>"}},
            "_links": {"webui": "/spaces/MI/pages/222/Call"},
        },
    ]
}


# ── 순수 파싱 ─────────────────────────────────────────────────────────────
def test_parse_pages_extracts_text_and_url():
    base = "https://x.atlassian.net/wiki"
    pages = confluence.parse_pages(base, _PAYLOAD)
    assert len(pages) == 2
    assert pages[0]["title"] == "HBM4 메모"
    assert "HBM4 12단 채택 공식화" in pages[0]["text"]
    assert "<h2>" not in pages[0]["text"]  # 태그 제거
    assert pages[0]["url"] == base + "/spaces/MI/pages/111/HBM4"


def test_config_from_source(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_EMAIL", "a@b.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")
    base, email, token = confluence.config_from_source(
        {"config": {"base_url": "https://x.atlassian.net/wiki/"}}
    )
    assert base == "https://x.atlassian.net/wiki"  # 끝 슬래시 제거
    assert email == "a@b.com" and token == "tok"


# ── fetch_pages (페이크 httpx) ─────────────────────────────────────────────
class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class FakeHttp:
    def __init__(self, payload):
        self._p = payload
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResp(self._p)


def test_fetch_pages():
    http = FakeHttp(_PAYLOAD)
    pages = asyncio.run(
        confluence.fetch_pages(http, "https://x.atlassian.net/wiki", "a@b.com", "tok", limit=10)
    )
    assert len(pages) == 2
    # Basic 인증 헤더 + body-format=storage 요청 확인
    url, kw = http.calls[0]
    assert "body-format=storage" in url
    assert kw["headers"]["Authorization"].startswith("Basic ")


# ── 수집 흐름(재동기화) ────────────────────────────────────────────────────
def test_collect_confluence_source_syncs(client, monkeypatch):
    # confluence 소스 생성
    sid = client.post(
        "/collection/sources",
        json={"name": "위키", "type": "confluence",
              "config": {"base_url": "https://x.atlassian.net/wiki"}},
    ).json()["id"]
    monkeypatch.setenv("CONFLUENCE_EMAIL", "a@b.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")

    async def fake_fetch(c, base, email, token, **kw):
        return confluence.parse_pages(base, _PAYLOAD)

    monkeypatch.setattr(confluence, "fetch_pages", fake_fetch)

    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_confluence_source(source, client=None))
    assert errors == []
    assert len(docs) == 2
    assert {d["title"] for d in docs} == {"HBM4 메모", "경쟁사 콜"}

    # 재수집해도 중복되지 않고 교체(재동기화)된다
    docs2, _ = asyncio.run(pipeline.collect_confluence_source(source, client=None))
    assert len(docs2) == 2
    all_docs = client.get("/collection/documents", params={"source": sid}).json()["documents"]
    assert len(all_docs) == 2  # 누적 아님


def test_collect_confluence_missing_creds(client, monkeypatch):
    sid = client.post(
        "/collection/sources",
        json={"name": "위키2", "type": "confluence", "config": {"base_url": "https://x/wiki"}},
    ).json()["id"]
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    # 실제 프로파일 .env 가 자격증명을 다시 채우지 않도록 로더를 막는다
    monkeypatch.setattr(profiles, "load_profile", lambda *a, **k: None)
    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_confluence_source(source, client=None))
    assert docs == []
    assert errors and "설정 필요" in errors[0]["error"]
