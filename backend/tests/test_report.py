"""주간 MI 리포트 통합 생성 테스트.

오케스트레이션이 다이제스트·주제·총평 호출을 순서대로 수행하는지, 결과를
조립하는지 검증한다. 페이크 클라이언트는 시스템 프롬프트로 호출 종류를 구분해
각기 다른 응답을 돌려준다(네트워크 없음).
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app import main, report

_DIGEST_JSON = json.dumps(
    {
        "items": [
            {
                "title": "HBM4 채택 공식화",
                "source": "뉴스",
                "publishedAt": "2026-06-10",
                "summary": "...",
                "slsiRelevance": "...",
                "demandImpact": "...",
                "risk": "단일 출처 — 교차검증 필요",
                "impact": "high",
                "tags": ["HBM"],
            }
        ]
    },
    ensure_ascii=False,
)

_TOPIC_JSON = json.dumps(
    {
        "category": "수요/시황",
        "summary": "HBM 수요 강세.",
        "insight": "S.LSI 시사점.",
        "history": [{"date": "2026-06-10", "event": "채택", "source": "뉴스"}],
    },
    ensure_ascii=False,
)

_OVERVIEW = "이번 주는 HBM4 채택과 수요 강세가 핵심 흐름입니다."


class RoutingFakeClient:
    """시스템 프롬프트로 호출 종류를 구분해 알맞은 캔드 응답을 돌려준다."""

    def __init__(self):
        self.kinds: list[str] = []

    async def chat(self, messages, **kwargs):
        sys = messages[0]["content"]
        if "뉴스 다이제스트" in sys:
            kind, content = "digest", _DIGEST_JSON
        elif "주제 이력" in sys:
            kind, content = "topic", _TOPIC_JSON
        elif "Top Priority(기회)" in sys:
            kind, content = "priority_risk", '{"priorities": [], "risks": []}'
        elif "관리포인트를 1~3개" in sys:
            kind, content = "critical_point", '{"criticalPoints": []}'
        elif "사실검증 agent다" in sys:
            kind, content = "audit", '{"unsupported": []}'
        elif "총평" in sys:
            kind, content = "overview", _OVERVIEW
        else:
            kind, content = "other", "{}"
        self.kinds.append(kind)
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_build_overview_messages_includes_digest_and_topics():
    digest_obj = {"issueNo": 47, "items": [{"title": "HBM4 채택"}]}
    topics = [{"title": "HBM 수요", "summary": "강세"}]
    msgs = report.build_overview_messages(digest_obj, topics)
    assert "총평" in msgs[0]["content"]
    assert "HBM4 채택" in msgs[1]["content"]
    assert "HBM 수요" in msgs[1]["content"]


def test_generate_report_orchestrates_all_parts():
    client = RoutingFakeClient()
    digest_docs = [{"title": "d", "source": "뉴스", "publishedAt": "2026-06-10", "content": "본문"}]
    topic_docs = {"HBM 수요": [{"title": "t", "source": "뉴스", "publishedAt": "2026-06-10", "content": "본문"}]}
    result = asyncio.run(
        report.generate_report(
            client,
            digest_docs=digest_docs,
            topic_docs=topic_docs,
            issue_no=47,
            period="2026.06.08 – 06.11",
            generated_at="2026-06-13",
        )
    )
    assert result["issueNo"] == 47
    assert result["overview"] == _OVERVIEW
    assert result["digest"]["items"][0]["title"] == "HBM4 채택 공식화"
    assert len(result["topics"]) == 1
    assert result["topics"][0]["title"] == "HBM 수요"
    assert result["priorities"] == [] and result["risks"] == []
    assert result["criticalPoints"] == []
    assert result["overviewUnsupportedClaims"] == []
    # 병렬 그룹(다이제스트/priority-risk/critical-point/주제) → 총평 → 총평 검증.
    # 마지막 둘은 리포트 총평 생성→검증(overview, audit) 순서가 고정이고, 그 앞은 병렬이라
    # 순서가 뒤섞일 수 있다. 다이제스트·주제 요약 자체도 각각 audit 을 한 번씩 더 부른다.
    assert client.kinds.count("digest") == 1
    assert client.kinds.count("priority_risk") == 1
    assert client.kinds.count("critical_point") == 1
    assert client.kinds.count("topic") == 1
    assert client.kinds.count("audit") == 3  # 다이제스트 감사 + 주제 요약 감사 + 총평 감사


def test_generate_report_emits_progress_for_every_stage():
    client = RoutingFakeClient()
    digest_docs = [{"title": "d", "source": "뉴스", "publishedAt": "2026-06-10", "content": "본문"}]
    topic_docs = {"HBM 수요": [{"title": "t", "source": "뉴스", "publishedAt": "2026-06-10", "content": "본문"}]}
    events = []

    async def on_progress(ev):
        events.append(ev["tool"])

    asyncio.run(report.generate_report(
        client, digest_docs=digest_docs, topic_docs=topic_docs,
        issue_no=1, period="", generated_at="2026-06-13", on_progress=on_progress,
    ))
    seen = set(events)
    for stage in (
        "digest_generate", "digest_audit", "priority_risk", "critical_point",
        "topic_generate:HBM 수요", "topic_audit:HBM 수요",
        "report_overview", "report_overview_audit",
    ):
        assert stage in seen, f"{stage} 단계 progress 이벤트 누락"
    # 총평은 병렬 분석이 다 끝난 뒤에만 시작된다(그 자료를 총평 프롬프트에 넣으므로).
    assert events.index("report_overview") > events.index("priority_risk")
    assert client.kinds[-2:] == ["overview", "audit"]


def test_generate_report_rolls_up_ungrounded_numbers():
    # 총평이 문서에 없는 수치(777)를 지어냄 → 리포트 수준으로 롤업 + 마크다운 경고.
    class F:
        async def chat(self, messages, **kw):
            sys = messages[0]["content"]
            if "뉴스 다이제스트" in sys:
                c = _DIGEST_JSON
            elif "주제 이력" in sys:
                c = _TOPIC_JSON
            elif "Top Priority(기회)" in sys:
                c = '{"priorities": [], "risks": []}'
            elif "관리포인트를 1~3개" in sys:
                c = '{"criticalPoints": []}'
            elif "사실검증 agent다" in sys:
                c = '{"unsupported": []}'
            else:
                c = "이번 주 매출 777억으로 급증했습니다."
            return {"choices": [{"message": {"content": c}}]}

    digest_docs = [{"title": "d", "source": "뉴스", "publishedAt": "2026-06-10", "content": "HBM 채택"}]
    topic_docs = {"HBM": [{"title": "t", "source": "뉴스", "publishedAt": "2026-06-10", "content": "HBM 수요"}]}
    res = asyncio.run(report.generate_report(
        F(), digest_docs=digest_docs, topic_docs=topic_docs,
        issue_no=1, period="P", generated_at="2026-06-13"))
    assert res["overviewGrounded"] is False and "777" in res["overviewUngroundedNumbers"]
    assert res["numbersGrounded"] is False and "777" in res["ungroundedNumbers"]
    md = report.render_report_markdown(res)
    assert "검토 필요" in md and "777" in md
    assert md.startswith("# ")  # 제목은 맨 앞 유지, 경고는 그 다음 줄


def test_generate_report_empty_raises():
    with pytest.raises(ValueError):
        asyncio.run(
            report.generate_report(
                RoutingFakeClient(),
                digest_docs=[],
                topic_docs={},
                issue_no=1,
                period="",
                generated_at="2026-06-13",
            )
        )


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_report_generate_endpoint(client, monkeypatch):
    _upload(client, "hbm.txt", "HBM4 채택 공식화. 수요 강세.", "HBM 수요")
    monkeypatch.setattr(main, "get_client", lambda profile=None: RoutingFakeClient())
    r = client.post("/report/generate", json={"issueNo": 48, "period": "이번 주"})
    assert r.status_code == 200
    body = r.json()
    assert body["issueNo"] == 48
    assert body["overview"] == _OVERVIEW
    assert body["digest"] is not None
    assert len(body["topics"]) >= 1


def test_report_generate_stream_endpoint(client, monkeypatch):
    _upload(client, "hbm.txt", "HBM4 채택 공식화. 수요 강세.", "HBM 수요")
    monkeypatch.setattr(main, "get_client", lambda profile=None: RoutingFakeClient())
    r = client.post("/report/generate/stream", json={"issueNo": 48, "period": "이번 주"})
    assert r.status_code == 200
    events = [json.loads(ln[6:]) for ln in r.text.splitlines() if ln.startswith("data: ")]
    tools = {e["tool"] for e in events if e["type"] == "progress"}
    assert "report_overview" in tools and "report_overview_audit" in tools
    assert events[-1]["type"] == "done" and events[-1]["issueNo"] == 48


def test_report_generate_no_documents_422(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: RoutingFakeClient())
    r = client.post("/report/generate", json={})
    assert r.status_code == 422


# ── 문서(Markdown) 렌더 + 템플릿 ──────────────────────────────────────────
_SAMPLE_REPORT = {
    "generatedAt": "2026-06-15",
    "period": "6월 2주",
    "issueNo": 53,
    "overview": "이번 주 핵심은 HBM4 전환.",
    "digest": {
        "issueNo": 53,
        "items": [
            {"title": "HBM4 12단 전환", "impact": "high", "summary": "양산 2027",
             "slsiRelevance": "베이스 다이 기회", "demandImpact": "수요 증가", "risk": "패키징 병목"},
        ],
    },
    "topics": [
        {"title": "HBM 수요", "category": "수요/시황", "summary": "가파른 증가", "insight": "캐파 병목"},
    ],
}


def test_render_report_markdown_default_template():
    from app import report
    md = report.render_report_markdown(_SAMPLE_REPORT)
    assert "주간 MI 리포트 제53호" in md
    assert "6월 2주" in md and "2026-06-15" in md
    assert "이번 주 핵심은 HBM4 전환." in md
    assert "HBM4 12단 전환" in md and "패키징 병목" in md  # 다이제스트 항목 렌더
    assert "HBM 수요" in md and "인사이트" in md            # 주제 렌더
    assert "{{" not in md  # 모든 토큰 치환됨


def test_render_report_markdown_custom_template():
    from app import report
    tmpl = "제{{issue_no}}호 / {{period}}\n총평: {{overview}}"
    md = report.render_report_markdown(_SAMPLE_REPORT, template=tmpl)
    assert md.startswith("제53호 / 6월 2주")
    assert "총평: 이번 주 핵심은 HBM4 전환." in md
    assert "다이제스트" not in md  # 템플릿에 없는 섹션은 나오지 않음


def test_report_render_endpoint_uses_existing_report_without_generation(client):
    response = client.post(
        "/report/render",
        json={"report": _SAMPLE_REPORT, "template": "# 제{{issue_no}}호\n{{overview}}"},
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "MI리포트_제53호.md"
    assert response.json()["markdown"] == "# 제53호\n이번 주 핵심은 HBM4 전환."


def test_render_report_markdown_empty_sections():
    from app import report
    md = report.render_report_markdown(
        {"issueNo": 1, "period": "", "generatedAt": "", "overview": "", "digest": None, "topics": []}
    )
    assert "생성된 다이제스트 항목이 없습니다" in md
    assert "요약된 주제가 없습니다" in md
