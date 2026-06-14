"""스케줄 파이프라인 테스트 (수집 → 다이제스트 생성·저장).

fetch 와 게이트웨이를 페이크로 치환해 네트워크 없이 검증한다.
"""

from __future__ import annotations

import asyncio
import json

from app import collection, config, fetcher, pipeline


class FakeGateway:
    def __init__(self, content: str):
        self._content = content

    async def chat(self, messages, **kwargs):
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


_DIGEST_JSON = json.dumps(
    {
        "items": [
            {
                "title": "수집 기반 항목",
                "source": "뉴스",
                "publishedAt": "2026-06-14",
                "summary": "...",
                "slsiRelevance": "...",
                "demandImpact": "...",
                "risk": "단일 출처 — 교차검증 필요",
                "impact": "medium",
                "tags": ["HBM"],
            }
        ]
    },
    ensure_ascii=False,
)


async def _fake_fetch(client, url, **kwargs):
    return {"url": url, "title": f"수집 {url}", "text": f"본문 ({url})"}


def test_collect_source_ingests(client, monkeypatch):
    # URL 소스 생성
    sid = client.post(
        "/collection/sources",
        json={"name": "뉴스원", "type": "news", "config": {"url": "https://a.com/x"}},
    ).json()["id"]
    source = collection.get_source(sid)
    monkeypatch.setattr(fetcher, "fetch_url", _fake_fetch)

    docs, errors = asyncio.run(pipeline.collect_source(source, client=None))  # client unused (fetch faked)
    assert len(docs) == 1
    assert errors == []
    assert docs[0]["sourceName"] == "뉴스원"


def test_run_collection_only_url_connectors(client, monkeypatch):
    client.post(
        "/collection/sources",
        json={"name": "URL뉴스", "type": "news", "config": {"url": "https://a.com/1"}},
    )
    # URL 없는 커넥터(시드된 것들) + 업로드는 건너뛰어야 한다
    monkeypatch.setattr(fetcher, "fetch_url", _fake_fetch)
    result = asyncio.run(pipeline.run_collection())
    assert result["ingested"] == 1
    assert [s["source"] for s in result["sources"]] == ["URL뉴스"]


def test_run_digest_saves_and_latest_loads(client, monkeypatch, isolated):
    # 본문 있는 문서 1건 업로드
    import io

    client.post(
        "/collection/upload",
        files={"file": ("d.txt", io.BytesIO("HBM 본문".encode()), "text/plain")},
    )
    monkeypatch.setattr(pipeline, "get_client", lambda: FakeGateway(_DIGEST_JSON))

    result = asyncio.run(pipeline.run_digest(issue_no=7, period="테스트"))
    assert result["issueNo"] == 7
    assert result["items"][0]["id"] == "d1"
    # 파일로 저장됨
    assert (config.DIGESTS_DIR / "latest.json").exists()
    # load_latest_digest 로 읽힘
    latest = pipeline.load_latest_digest()
    assert latest is not None
    assert latest["issueNo"] == 7
    assert "generatedAt" in latest


def test_run_pipeline_end_to_end(client, monkeypatch):
    client.post(
        "/collection/sources",
        json={"name": "URL뉴스", "type": "news", "config": {"url": "https://a.com/1"}},
    )
    monkeypatch.setattr(fetcher, "fetch_url", _fake_fetch)
    monkeypatch.setattr(pipeline, "get_client", lambda: FakeGateway(_DIGEST_JSON))

    result = asyncio.run(pipeline.run_pipeline(issue_no=1, period="자동"))
    assert result["collected"]["ingested"] == 1
    assert result["digest"] is not None
    assert result["digest"]["items"][0]["title"] == "수집 기반 항목"


def test_load_latest_none_when_absent(client):
    assert pipeline.load_latest_digest() is None


def test_digest_latest_endpoint(client):
    r = client.get("/digest/latest")
    assert r.status_code == 200
    assert r.json()["digest"] is None  # 아직 생성 전
