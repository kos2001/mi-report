"""문서 자동 분류 테스트.

순수 로직은 네트워크 없이, 엔드포인트는 페이크 게이트웨이 클라이언트를 주입해 검증.
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app import classify, main
from app.schemas import DocClassificationOut


class FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple] = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


_VALID_RESPONSE = json.dumps(
    {"topic": "HBM 수요", "category": "수요/시황", "tags": ["HBM", "AI가속기"]},
    ensure_ascii=False,
)


# ── 순수 로직 ─────────────────────────────────────────────────────────────
def test_build_messages_includes_title_and_content():
    msgs = classify.build_messages("문서제목", "본문내용")
    assert msgs[0]["role"] == "system"
    assert "문서제목" in msgs[1]["content"]
    assert "본문내용" in msgs[1]["content"]


def test_parse_classification_valid():
    out = classify.parse_classification(_VALID_RESPONSE)
    assert isinstance(out, DocClassificationOut)
    assert out.topic == "HBM 수요"
    assert out.category == "수요/시황"


def test_parse_classification_invalid_raises():
    with pytest.raises(ValueError):
        classify.parse_classification("JSON 아님")


def test_classify_document_returns_dict():
    client = FakeClient(_VALID_RESPONSE)
    result = asyncio.run(classify.classify_document(client, "제목", "본문"))
    assert result["topic"] == "HBM 수요"
    assert result["tags"] == ["HBM", "AI가속기"]
    assert len(client.calls) == 1


def test_build_messages_includes_existing_topics_when_given():
    msgs = classify.build_messages("제목", "본문", existing_topics=["HBM 수요", "2nm 파운드리"])
    assert "HBM 수요" in msgs[0]["content"]
    assert "2nm 파운드리" in msgs[0]["content"]


def test_build_messages_omits_existing_topics_block_when_empty():
    msgs = classify.build_messages("제목", "본문", existing_topics=[])
    assert "기존 주제" not in msgs[0]["content"]


def test_classify_document_passes_existing_topics_through():
    client = FakeClient(_VALID_RESPONSE)
    asyncio.run(classify.classify_document(client, "제목", "본문", existing_topics=["HBM 수요"]))
    sent_system = client.calls[0][0][0]["content"]
    assert "HBM 수요" in sent_system


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def _upload(client, name, body, topic=None):
    return client.post(
        "/collection/upload",
        files={"file": (name, io.BytesIO(body.encode("utf-8")), "text/plain")},
        data={"topic": topic} if topic else {},
    )


def test_classify_single_document_sets_topic(client, monkeypatch):
    up = _upload(client, "doc.txt", "HBM4 채택 공식화. AI 가속기 수요 강세.")
    doc_id = up.json()["id"]
    assert up.json()["topic"] is None  # 업로드 시 주제 미부여
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post(f"/collection/documents/{doc_id}/classify")
    assert r.status_code == 200
    body = r.json()
    assert body["classification"]["topic"] == "HBM 수요"
    assert body["document"]["topic"] == "HBM 수요"  # 문서에 반영됨

    # 목록에서도 주제가 보인다
    docs = client.get("/collection/documents").json()["documents"]
    assert docs[0]["topic"] == "HBM 수요"


def test_classify_missing_document_404(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/collection/documents/nope/classify")
    assert r.status_code == 404


def test_classify_untagged_batch(client, monkeypatch):
    _upload(client, "a.txt", "본문 A")
    _upload(client, "b.txt", "본문 B")
    _upload(client, "c.txt", "이미 태깅됨", topic="기존주제")  # 미분류 아님
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient(_VALID_RESPONSE))
    r = client.post("/collection/classify-untagged")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2  # 미분류 2건만 분류
    for item in body["classified"]:
        assert item["topic"] == "HBM 수요"


def test_classify_bad_llm_output_502(client, monkeypatch):
    up = _upload(client, "doc.txt", "본문")
    doc_id = up.json()["id"]
    monkeypatch.setattr(main, "get_client", lambda profile=None: FakeClient("JSON 아님"))
    r = client.post(f"/collection/documents/{doc_id}/classify")
    assert r.status_code == 502
