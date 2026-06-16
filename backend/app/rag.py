"""문서 코퍼스 Q&A — 수집 문서를 근거로 자연어 질문에 답한다(RAG).

AI agent 개입 지점 #6: 사용자의 자연어 질문 + 수집 문서(검색/최근) → LLM →
문서 근거 답변. 답변은 자유 텍스트이며 [문서 N] 형태로 근거를 인용한다.
검색은 제목·주제 기반 FTS(또는 최근 문서)로 후보를 추리는 경량 방식이다.
순수 로직과 네트워크 호출(주입된 게이트웨이 클라이언트)을 분리한다.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from . import reranker

RAG_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
아래에 번호가 매겨진 수집 문서들만 근거로 사용자 질문에 답한다.

규칙:
- 제공된 문서에 없는 내용은 추측하지 말고 "제공된 문서에서 확인되지 않음"이라고 답한다.
- 답변 중 근거가 된 부분에는 [문서 N] 형태로 출처를 인용한다.
- 한국어로 간결하고 분석적으로 답한다."""

RERANK_SYSTEM_PROMPT = """질문과 번호가 매겨진 후보 문서 목록이 주어진다.
질문에 답하는 데 실제로 관련 있는 문서만 관련도 높은 순으로 골라, 그 번호만 반환한다.
- 최대 {top_n}개. 관련 없는 문서는 빼라.
- 출력은 번호만(예: 3, 1, 5). 다른 설명 금지."""


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


def _parse_indices(content: str, n: int) -> list[int]:
    """응답에서 1..n 범위의 번호를 등장 순서대로(중복 제거) 추출한다."""
    out: list[int] = []
    for tok in re.findall(r"\d+", content):
        i = int(tok)
        if 1 <= i <= n and i not in out:
            out.append(i)
    return out


def _cited_indices(answer: str, n: int) -> list[int]:
    """답변의 [문서 N] 인용에서 실제 인용된 문서 번호를 추출한다."""
    found = {int(m) for m in re.findall(r"\[\s*문서\s*(\d+)\s*\]", answer)}
    return sorted(i for i in found if 1 <= i <= n)


async def rerank(
    client: ChatClient,
    question: str,
    docs: list[dict[str, Any]],
    *,
    top_n: int = 6,
    temperature: float = 0.0,
) -> list[dict[str, Any]]:
    """후보 문서를 관련도 재정렬해 상위 top_n 만 남긴다(2단계 검색).

    MI_RERANK_MODEL 가 설정되면 OpenRouter 전용 rerank 모델(다국어·한국어)을 쓰고,
    아니면 LLM(게이트웨이)으로 재정렬한다. 후보가 top_n 이하면 그대로 둔다.
    모든 경로 실패 시 입력 상위 top_n 으로 폴백.
    """
    if len(docs) <= top_n:
        return docs

    # 1순위: 전용 rerank 모델(설정 시)
    if reranker.enabled():
        try:
            ranked = await reranker.rerank_documents(question, docs, top_n=top_n)
            if ranked:
                return ranked
        except Exception:
            pass  # rerank 실패 → LLM 재정렬로 폴백

    lines = [
        f"[{i}] {d.get('title', '')}: {(d.get('content', '') or '')[:300]}"
        for i, d in enumerate(docs, 1)
    ]
    messages = [
        {"role": "system", "content": RERANK_SYSTEM_PROMPT.format(top_n=top_n)},
        {"role": "user", "content": f"질문: {question}\n\n후보 문서:\n" + "\n".join(lines)},
    ]
    try:
        completion = await client.chat(messages, temperature=temperature)
        order = _parse_indices(extract_content(completion), len(docs))
        chosen = [docs[i - 1] for i in order][:top_n]
        if chosen:
            return chosen
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    return docs[:top_n]  # 폴백: 입력 순서 상위


async def answer_question(
    client: ChatClient,
    question: str,
    docs: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """질문 + 문서로 근거 기반 답변을 생성한다. 답변이 실제 인용한 문서만 sources 로 반환."""
    if not docs:
        raise ValueError("답변 근거로 쓸 본문 있는 문서가 없습니다.")
    completion = await client.chat(build_messages(question, docs), temperature=temperature)
    answer = extract_content(completion)

    all_sources = [
        {"index": i, "title": d.get("title", ""), "source": d.get("source", "")}
        for i, d in enumerate(docs, 1)
    ]
    cited = _cited_indices(answer, len(docs))
    # 실제 인용된 문서만 근거로 표시(인용이 없으면 전체로 폴백)
    sources = [all_sources[i - 1] for i in cited] if cited else all_sources
    return {
        "answer": answer,
        "sources": sources,
        "usedDocCount": len(docs),
        "citedCount": len(cited),
    }
