"""다이제스트 생성 테스트.

순수 로직(프롬프트 구성·파싱·검증)은 네트워크 없이, 엔드포인트는 페이크
게이트웨이 클라이언트를 주입해 검증한다(실제 게이트웨이 의존 없음).
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json

import pytest

from app import agentchat, digest, main
from app.gateway import LLMError
from app.schemas import DigestItemOut


# ── 페이크 게이트웨이 클라이언트 ──────────────────────────────────────────
class FakeClient:
    """주어진 content 를 chat completion 으로 돌려주는 페이크."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple] = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


_VALID_RESPONSE = json.dumps(
    {
        "items": [
            {
                "title": "차세대 AI 가속기 HBM4 채택",
                "source": "기술 뉴스",
                "publishedAt": "2026-06-10",
                "summary": "HBM4 채택 공식화.",
                "slsiRelevance": "HBM 컨트롤러 IP 수주 기회.",
                "demandImpact": "선단 패키징 캐파 경쟁 심화.",
                "risk": "단일 출처 — 교차검증 필요.",
                "impact": "high",
                "tags": ["HBM", "AI가속기"],
            }
        ]
    },
    ensure_ascii=False,
)


# ── 순수 로직 ─────────────────────────────────────────────────────────────
def test_build_messages_includes_doc_content():
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문A"}]
    msgs = digest.build_messages(docs)
    assert msgs[0]["role"] == "system"
    assert "MI" in msgs[0]["content"]
    assert "본문A" in msgs[1]["content"]
    assert "T1" in msgs[1]["content"]


def test_build_messages_includes_feedback_notes():
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문A"}]
    msgs = digest.build_messages(docs, feedback_notes=["과거에 수치를 지어냄"])
    assert "과거에 수치를 지어냄" in msgs[0]["content"]


def test_build_messages_includes_wiki_as_secondary_context():
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문A"}]
    msgs = digest.build_messages(docs, wiki_context="[2026년 33주차] HBM 수요 강세")
    prompt = msgs[1]["content"]
    assert "이전 주차 LLM Wiki 맥락" in prompt
    assert "HBM 수요 강세" in prompt
    assert "Wiki만을 근거로 새 항목을 만들지 마라" in prompt


def test_parse_items_plain_json():
    items = digest.parse_items(_VALID_RESPONSE)
    assert len(items) == 1
    assert isinstance(items[0], DigestItemOut)
    assert items[0].impact == "high"
    assert items[0].tags == ["HBM", "AI가속기"]


def test_parse_items_strips_code_fence():
    fenced = "```json\n" + _VALID_RESPONSE + "\n```"
    items = digest.parse_items(fenced)
    assert len(items) == 1
    assert items[0].title.startswith("차세대")


def test_parse_items_invalid_raises():
    with pytest.raises(ValueError):
        digest.parse_items("죄송하지만 JSON 이 없습니다.")


def test_parse_items_bad_json_raises():
    with pytest.raises(ValueError):
        digest.parse_items('{"items": [oops not json]}')


def test_current_week_label_formats_year_and_iso_week():
    label = digest.current_week_label(datetime.date(2026, 8, 20))
    assert label == "2026년 34주차"


def test_generate_digest_assigns_ids_and_metadata():
    client = FakeClient(_VALID_RESPONSE)
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]
    result = asyncio.run(
        digest.generate_digest(client, docs, period="2026.06.08 – 06.11")
    )
    assert result["week"] == digest.current_week_label()
    assert result["mailedAt"] is None  # 초안
    assert result["generated"] is True
    assert result["sourceDocCount"] == 1
    assert result["items"][0]["id"] == "d1"
    assert result["items"][0]["impact"] == "high"
    assert result["unsupportedClaims"] == []
    assert len(client.calls) == 2  # 다이제스트 생성 + 총평 검증(audit)


def test_generate_digest_retries_once_after_malformed_json():
    class MalformedThenValidClient:
        def __init__(self):
            self.calls = []

        async def chat(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            if len(self.calls) == 1:
                content = '{"items":[{"title":"깨진 "인용" 제목"}]}'
            elif len(self.calls) == 2:
                content = _VALID_RESPONSE
            else:
                content = '{"unsupported":[]}'
            return {"choices": [{"message": {"content": content}}]}

    client = MalformedThenValidClient()
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]
    result = asyncio.run(digest.generate_digest(client, docs, period="P"))

    assert result["items"][0]["title"] == "차세대 AI 가속기 HBM4 채택"
    assert len(client.calls) == 3  # 최초 생성 + JSON 재생성 + 서술 검증
    retry_messages, retry_kwargs = client.calls[1]
    assert "JSON 문법 검증에 실패" in retry_messages[1]["content"]
    assert retry_kwargs["temperature"] == 0.0


def test_generate_digest_raises_after_second_malformed_json():
    client = FakeClient('{"items":[{"title":"깨진 "인용" 제목"}]}')
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]

    with pytest.raises(ValueError, match="JSON 자동 재생성 후에도 파싱 실패"):
        asyncio.run(digest.generate_digest(client, docs, period="P"))
    assert len(client.calls) == 2


def test_generate_digest_emits_progress_events():
    client = FakeClient(_VALID_RESPONSE)
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]
    events = []

    async def on_progress(ev):
        events.append((ev["tool"], ev["status"]))

    asyncio.run(digest.generate_digest(
        client, docs, period="", on_progress=on_progress,
    ))
    assert events == [
        ("digest_generate", "running"), ("digest_generate", "completed"),
        ("digest_audit", "running"), ("digest_audit", "completed"),
    ]


def test_generate_digest_flags_unsupported_claims():
    # summary 에 원문이 뒷받침하지 않는 추세 주장 → 독립 검증 agent 가 잡는다.
    class RoutingFakeClient:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                content = json.dumps({"items": [{
                    "title": "T", "source": "뉴스", "publishedAt": "2026-06-01",
                    "summary": "3주 연속 수요가 악화되고 있다.", "slsiRelevance": "-",
                    "demandImpact": "-", "risk": "-", "impact": "medium", "tags": [],
                }]}, ensure_ascii=False)
            else:
                content = json.dumps({
                    "unsupported": [{"claim": "3주 연속 수요가 악화되고 있다", "why": "원문에 추세 언급 없음"}],
                }, ensure_ascii=False)
            return {"choices": [{"message": {"content": content}}]}

    docs = [{"title": "T", "source": "뉴스", "publishedAt": "2026-06-01", "content": "수요 관련 보도."}]
    result = asyncio.run(digest.generate_digest(RoutingFakeClient(), docs, period=""))
    assert result["unsupportedClaims"] == ["3주 연속 수요가 악화되고 있다"]


def test_generate_digest_empty_docs_raises():
    with pytest.raises(ValueError):
        asyncio.run(digest.generate_digest(FakeClient(""), [], period=""))


def test_generate_digest_flags_ungrounded_numbers():
    # 문서엔 35.2% 만 있고 LLM 이 1,234억(미근거)을 지어냄 → 플래그.
    resp = json.dumps({"items": [{
        "title": "HBM4 12단 채택", "source": "기술뉴스", "publishedAt": "2026-06-10",
        "summary": "점유율 35.2% 기록, 매출 1,234억원 전망.", "slsiRelevance": "HBM 컨트롤러.",
        "demandImpact": "수요 강세.", "risk": "단일 출처.", "impact": "high", "tags": [],
    }]}, ensure_ascii=False)
    docs = [{"title": "HBM4 12단 채택", "source": "기술뉴스",
             "publishedAt": "2026-06-10", "content": "HBM4 12단 채택. 점유율 35.2% 기록."}]
    res = asyncio.run(digest.generate_digest(FakeClient(resp), docs, period="P"))
    item = res["items"][0]
    assert "1234" in item["ungroundedNumbers"]   # 지어낸 수치
    assert "35.2" not in item["ungroundedNumbers"]  # 문서 근거 수치는 통과
    assert item["numbersGrounded"] is False
    assert item["sourceVerified"] is True           # 출처명 일치
    assert res["numbersGrounded"] is False and "1234" in res["ungroundedNumbers"]


def test_generate_digest_flags_unverified_source():
    # 출처명 불일치 + 제목 무관 → 거짓 출처 귀속으로 플래그.
    resp = json.dumps({"items": [{
        "title": "전혀 무관한 제목 XYZ", "source": "조작된출처", "publishedAt": "2026-06-10",
        "summary": "내용.", "slsiRelevance": "", "demandImpact": "", "risk": "",
        "impact": "low", "tags": [],
    }]}, ensure_ascii=False)
    docs = [{"title": "HBM4 12단 채택", "source": "기술뉴스",
             "publishedAt": "2026-06-10", "content": "HBM4 채택."}]
    res = asyncio.run(digest.generate_digest(FakeClient(resp), docs, period="P"))
    assert res["items"][0]["sourceVerified"] is False
    assert res["unverifiedSourceCount"] == 1


def test_generate_digest_verifies_publisher_from_aggregator_title():
    """수집기 이름과 실제 발행처가 달라도 문서 title/content로 출처를 추적한다."""
    resp = json.dumps({"items": [{
        "title": "서진시스템 단기 악재 해소·본격 개선 전망",
        "source": "한경 컨센서스",
        "publishedAt": "2026-08-20",
        "summary": "서진시스템의 실적 개선 전망.",
        "slsiRelevance": "반도체 장비",
        "demandImpact": "테스트 장비 수요 변화",
        "risk": "단일 출처 — 교차검증 필요",
        "impact": "medium",
        "tags": ["서진시스템"],
    }]}, ensure_ascii=False)
    docs = [{
        "title": "한경 컨센서스",
        "source": "컨센서스 갱신 감지",
        "publishedAt": "2026-08-20",
        "content": "서진시스템(178320) 단기 악재 해소, 좋아질 일만 남았다.",
    }]

    res = asyncio.run(digest.generate_digest(FakeClient(resp), docs, period="P"))

    assert res["items"][0]["sourceVerified"] is True
    assert res["unverifiedSourceCount"] == 0


# ── 엔드포인트 (페이크 클라이언트 주입) ────────────────────────────────────
@pytest.fixture(autouse=True)
def _stub_agent_comment(monkeypatch):
    """다이제스트 생성에 자동 통합된 hermes 에이전트 코멘트가 테스트에서 실제
    hermes(MI_LLM_*)를 타지 않도록 기본은 미설정 처리. 통합을 검증하는 테스트는
    개별적으로 재정의한다."""
    async def _unset(week, period, items):
        raise LLMError(503, "hermes 미설정(테스트)")

    monkeypatch.setattr(agentchat, "digest_comment", _unset)


def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_digest_generate_endpoint(client, monkeypatch):
    # 본문 있는 문서 업로드
    _upload(client, "hbm_news.txt", "HBM4 12단 채택 공식화. AI 가속기 수요 강세.", "HBM")
    # 게이트웨이를 페이크로 치환
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))

    r = client.post("/digest/generate", json={"period": "2026.06.08 – 06.11"})
    assert r.status_code == 200
    body = r.json()
    assert body["week"] == digest.current_week_label()
    assert body["sourceDocCount"] == 1
    assert body["items"][0]["id"] == "d1"
    assert body["items"][0]["impact"] == "high"
    # hermes 미설정(테스트 기본 스텁)이어도 다이제스트 생성 자체는 성공 — 코멘트만 빠진다
    assert body["agentComment"] is None


def test_digest_generate_endpoint_includes_auto_agent_comment(client, monkeypatch):
    _upload(client, "hbm_news.txt", "HBM4 12단 채택 공식화. AI 가속기 수요 강세.", "HBM")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))

    captured: dict = {}

    async def fake_digest_comment(week, period, items):
        captured["week"] = week
        captured["items"] = items
        return {"answer": "초안 검토 완료.", "sessionId": "s1",
                "numbersGrounded": True, "sources": []}

    monkeypatch.setattr(agentchat, "digest_comment", fake_digest_comment)

    r = client.post("/digest/generate", json={"period": "2026.06.08 – 06.11"})
    assert r.status_code == 200
    body = r.json()
    # 다이제스트 생성 시점에 에이전트 코멘트가 자동으로 붙는다 — 별도 버튼 클릭 불필요
    assert body["agentComment"]["answer"] == "초안 검토 완료."
    assert captured["week"] == body["week"]
    assert captured["items"][0]["title"] == body["items"][0]["title"]


def test_digest_generate_stream_endpoint(client, monkeypatch):
    _upload(client, "hbm_news.txt", "HBM4 12단 채택 공식화. AI 가속기 수요 강세.", "HBM")
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))

    r = client.post("/digest/generate/stream", json={"period": ""})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(ln[6:]) for ln in r.text.splitlines() if ln.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "progress" and types[-1] == "done"
    tools = [e["tool"] for e in events if e["type"] == "progress"]
    assert tools == [
        "digest_generate", "digest_generate", "digest_audit", "digest_audit",
        "digest_agent_comment", "digest_agent_comment",
    ]
    assert events[-1]["week"] == digest.current_week_label()
    assert events[-1]["agentComment"] is None  # hermes 미설정(테스트 기본 스텁)


def test_digest_generate_stream_no_documents_emits_error(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/digest/generate/stream", json={})
    assert r.status_code == 200  # SSE 자체는 200 — 실패는 이벤트로 전달
    events = [json.loads(ln[6:]) for ln in r.text.splitlines() if ln.startswith("data: ")]
    assert events == [{"type": "error", "status": 422, "detail": "본문이 있는 수집 문서가 없습니다. 먼저 문서를 업로드/수집하세요."}]


def test_digest_generate_no_documents_422(client, monkeypatch):
    # 본문 있는 문서가 없으면 게이트웨이를 부르지 않고 422
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/digest/generate", json={})
    assert r.status_code == 422


def test_digest_generate_bad_llm_output_502(client, monkeypatch):
    _upload(client, "doc.txt", "어떤 본문.", None)
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient("JSON 아님"))
    r = client.post("/digest/generate", json={})
    assert r.status_code == 502
