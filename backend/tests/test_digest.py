"""다이제스트 생성 테스트.

순수 로직(프롬프트 구성·파싱·검증)은 네트워크 없이, 엔드포인트는 페이크
게이트웨이 클라이언트를 주입해 검증한다(실제 게이트웨이 의존 없음).
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app import digest, main
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


def test_generate_digest_assigns_ids_and_metadata():
    client = FakeClient(_VALID_RESPONSE)
    docs = [{"title": "T1", "source": "뉴스", "publishedAt": "2026-06-01", "content": "본문"}]
    result = asyncio.run(
        digest.generate_digest(client, docs, issue_no=47, period="2026.06.08 – 06.11")
    )
    assert result["issueNo"] == 47
    assert result["mailedAt"] is None  # 초안
    assert result["generated"] is True
    assert result["sourceDocCount"] == 1
    assert result["items"][0]["id"] == "d1"
    assert result["items"][0]["impact"] == "high"
    assert len(client.calls) == 1  # 게이트웨이 1회 호출


def test_generate_digest_empty_docs_raises():
    with pytest.raises(ValueError):
        asyncio.run(digest.generate_digest(FakeClient(""), [], issue_no=1, period=""))


def test_generate_digest_flags_ungrounded_numbers():
    # 문서엔 35.2% 만 있고 LLM 이 1,234억(미근거)을 지어냄 → 플래그.
    resp = json.dumps({"items": [{
        "title": "HBM4 12단 채택", "source": "기술뉴스", "publishedAt": "2026-06-10",
        "summary": "점유율 35.2% 기록, 매출 1,234억원 전망.", "slsiRelevance": "HBM 컨트롤러.",
        "demandImpact": "수요 강세.", "risk": "단일 출처.", "impact": "high", "tags": [],
    }]}, ensure_ascii=False)
    docs = [{"title": "HBM4 12단 채택", "source": "기술뉴스",
             "publishedAt": "2026-06-10", "content": "HBM4 12단 채택. 점유율 35.2% 기록."}]
    res = asyncio.run(digest.generate_digest(FakeClient(resp), docs, issue_no=1, period="P"))
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
    res = asyncio.run(digest.generate_digest(FakeClient(resp), docs, issue_no=1, period="P"))
    assert res["items"][0]["sourceVerified"] is False
    assert res["unverifiedSourceCount"] == 1


# ── 엔드포인트 (페이크 클라이언트 주입) ────────────────────────────────────
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

    r = client.post("/digest/generate", json={"issueNo": 47, "period": "2026.06.08 – 06.11"})
    assert r.status_code == 200
    body = r.json()
    assert body["issueNo"] == 47
    assert body["sourceDocCount"] == 1
    assert body["items"][0]["id"] == "d1"
    assert body["items"][0]["impact"] == "high"


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
