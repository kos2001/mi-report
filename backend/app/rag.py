"""문서 코퍼스 Q&A — 수집 문서를 근거로 자연어 질문에 답한다(RAG).

AI agent 개입 지점 #6: 사용자의 자연어 질문 + 수집 문서(검색/최근) → LLM →
문서 근거 답변. 답변은 자유 텍스트이며 [문서 N] 형태로 근거를 인용한다.
검색은 제목·주제 기반 FTS(또는 최근 문서)로 후보를 추리는 경량 방식이다.
순수 로직과 네트워크 호출(주입된 게이트웨이 클라이언트)을 분리한다.
"""

from __future__ import annotations

from typing import Any, Protocol

RAG_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
아래에 번호가 매겨진 수집 문서들만 근거로 사용자 질문에 답한다.

규칙:
- 제공된 문서에 없는 내용은 추측하지 말고 "제공된 문서에서 확인되지 않음"이라고 답한다.
- 답변 중 근거가 된 부분에는 [문서 N] 형태로 출처를 인용한다.
- 한국어로 간결하고 분석적으로 답한다."""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_messages(question: str, docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    blocks: list[str] = []
    for i, d in enumerate(docs, 1):
        blocks.append(
            f"[문서 {i}] 제목: {d.get('title', '')} | 출처: {d.get('source', '')} "
            f"| 발행: {d.get('publishedAt', '') or '미상'}\n{d.get('content', '')}"
        )
    user = (
        "다음 수집 문서들을 근거로 질문에 답하라.\n\n"
        + "\n\n".join(blocks)
        + f"\n\n질문: {question}"
    )
    return [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


async def answer_question(
    client: ChatClient,
    question: str,
    docs: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """질문 + 문서로 근거 기반 답변을 생성한다. 사용한 문서를 sources 로 함께 반환."""
    if not docs:
        raise ValueError("답변 근거로 쓸 본문 있는 문서가 없습니다.")
    completion = await client.chat(build_messages(question, docs), temperature=temperature)
    answer = extract_content(completion)
    sources = [
        {"index": i, "title": d.get("title", ""), "source": d.get("source", "")}
        for i, d in enumerate(docs, 1)
    ]
    return {"answer": answer, "sources": sources, "usedDocCount": len(docs)}
