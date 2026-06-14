"""Jira 커넥터 테스트.

ADF→텍스트, 이슈 파싱은 네트워크 없이, 수집 흐름은 fetch_issues 를 페이크로 치환해 검증.
"""

from __future__ import annotations

import asyncio

from app import collection, jira, pipeline


def _adf(*paras: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paras
        ],
    }


_PAYLOAD = {
    "issues": [
        {
            "key": "MIR-1",
            "fields": {
                "summary": "HBM4 12단 전환 의사결정",
                "issuetype": {"name": "의사결정"},
                "description": _adf("HBM4 12단 베이스 다이로 전환한다.", "근거: 양산 2027 상반기."),
            },
        },
        {
            "key": "MIR-2",
            "fields": {
                "summary": "주간 MI 미팅 메모",
                "issuetype": {"name": "미팅메모"},
                "description": _adf("경쟁사 Q 콜 요약 공유.", "액션: 파운드리 동향 추적."),
            },
        },
        {
            "key": "MIR-3",
            "fields": {
                "summary": "2026 H2 프로젝트 계획",
                "issuetype": {"name": "프로젝트계획"},
                "description": None,  # 설명 없는 이슈 → summary 로 폴백
            },
        },
    ]
}


# ── 순수 파싱 ─────────────────────────────────────────────────────────────
def test_adf_to_text_extracts_paragraphs():
    txt = jira.adf_to_text(_adf("첫 문단", "둘째 문단"))
    assert "첫 문단" in txt and "둘째 문단" in txt
    assert txt.count("\n") >= 2  # 문단마다 줄바꿈


def test_parse_issues_title_type_and_url():
    base = "https://x.atlassian.net"
    issues = jira.parse_issues(base, _PAYLOAD)
    assert len(issues) == 3
    assert issues[0]["title"] == "[의사결정] HBM4 12단 전환 의사결정"
    assert "양산 2027" in issues[0]["text"]
    assert issues[0]["url"] == "https://x.atlassian.net/browse/MIR-1"
    # 설명 없으면 summary 로 폴백
    assert issues[2]["text"] == "2026 H2 프로젝트 계획"


def test_config_from_source_strips_wiki_and_defaults_to_confluence_creds(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_EMAIL", "a@b.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")
    base, project, email, token = jira.config_from_source(
        {"config": {"base_url": "https://x.atlassian.net/wiki", "project_key": "MIR"}}
    )
    assert base == "https://x.atlassian.net"  # /wiki 제거 → 사이트 루트
    assert project == "MIR"
    assert email == "a@b.com" and token == "tok"


# ── fetch_issues (페이크 httpx) ────────────────────────────────────────────
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

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResp(self._p)


def test_fetch_issues_uses_jql_and_auth():
    http = FakeHttp(_PAYLOAD)
    issues = asyncio.run(
        jira.fetch_issues(http, "https://x.atlassian.net", "MIR", "a@b.com", "tok", limit=10)
    )
    assert len(issues) == 3
    url, kw = http.calls[0]
    assert url.endswith("/rest/api/3/search/jql")
    assert 'project = "MIR"' in kw["json"]["jql"]
    assert kw["headers"]["Authorization"].startswith("Basic ")


# ── 수집 흐름(재동기화) ────────────────────────────────────────────────────
def test_collect_jira_source_syncs(client, monkeypatch):
    sid = client.post(
        "/collection/sources",
        json={"name": "Jira MI", "type": "jira",
              "config": {"base_url": "https://x.atlassian.net", "project_key": "MIR"}},
    ).json()["id"]
    monkeypatch.setenv("CONFLUENCE_EMAIL", "a@b.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")

    async def fake_fetch(c, base, project, email, token, **kw):
        return jira.parse_issues(base, _PAYLOAD)

    monkeypatch.setattr(jira, "fetch_issues", fake_fetch)

    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_jira_source(source, client=None))
    assert errors == []
    assert len(docs) == 3
    assert any(d["title"].startswith("[의사결정]") for d in docs)

    # 재수집해도 누적되지 않고 교체(재동기화)
    asyncio.run(pipeline.collect_jira_source(source, client=None))
    all_docs = client.get("/collection/documents", params={"source": sid}).json()["documents"]
    assert len(all_docs) == 3


def test_collect_jira_missing_config(client, monkeypatch):
    sid = client.post(
        "/collection/sources",
        json={"name": "Jira2", "type": "jira", "config": {"base_url": "https://x.atlassian.net"}},
    ).json()["id"]  # project_key 누락
    monkeypatch.setenv("CONFLUENCE_EMAIL", "a@b.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")
    source = collection.get_source(sid)
    docs, errors = asyncio.run(pipeline.collect_jira_source(source, client=None))
    assert docs == []
    assert errors and "설정 필요" in errors[0]["error"]
