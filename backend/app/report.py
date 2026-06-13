"""주간 MI 리포트 통합 생성 — 다이제스트(#1)·주제 요약(#2)을 묶어 한 편으로.

AI agent 개입 지점 #7: 개별 기능을 오케스트레이션해 '이번 주 리포트 초안'을
만든다. 다이제스트와 주제 요약을 생성한 뒤, 이를 종합한 총평(executive overview)을
게이트웨이로 한 번 더 생성한다. DB 접근은 호출자(엔드포인트)가 담당하고, 이 모듈은
이미 조회된 문서를 받아 오케스트레이션만 한다(네트워크 외 의존 없이 테스트 가능).
"""

from __future__ import annotations

from typing import Any, Protocol

from . import digest, topics

REPORT_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
이번 주 다이제스트 항목과 주제 요약을 종합해 주간 리포트의 '총평'을 작성한다.

규칙:
- 제공된 자료에만 근거한다. 새로운 사실·수치를 지어내지 않는다.
- 이번 주의 핵심 흐름과 S.LSI(시스템 LSI) 관점 시사점을 3~5문장으로 정리한다.
- 출력은 평문(문장)만. JSON/코드펜스/머리말을 붙이지 않는다."""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_overview_messages(
    digest_obj: dict[str, Any] | None, topic_summaries: list[dict[str, Any]]
) -> list[dict[str, str]]:
    parts: list[str] = []
    if digest_obj:
        titles = "; ".join(it.get("title", "") for it in digest_obj.get("items", []))
        parts.append(f"[다이제스트 제{digest_obj.get('issueNo')}호] {titles}")
    for t in topic_summaries:
        parts.append(f"[주제: {t.get('title', '')}] {t.get('summary', '')}")
    user = "다음 자료를 종합해 이번 주 MI 리포트 총평을 작성하라.\n\n" + "\n\n".join(parts)
    return [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


async def generate_overview(
    client: ChatClient,
    digest_obj: dict[str, Any] | None,
    topic_summaries: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
) -> str:
    completion = await client.chat(
        build_overview_messages(digest_obj, topic_summaries), temperature=temperature
    )
    return extract_content(completion).strip()


async def generate_report(
    client: ChatClient,
    *,
    digest_docs: list[dict[str, Any]],
    topic_docs: dict[str, list[dict[str, Any]]],
    issue_no: int,
    period: str,
    generated_at: str,
) -> dict[str, Any]:
    """다이제스트 + 주제 요약 + 총평을 묶어 주간 리포트를 생성한다."""
    if not digest_docs and not topic_docs:
        raise ValueError("리포트로 만들 본문 있는 문서가 없습니다.")

    digest_obj = (
        await digest.generate_digest(client, digest_docs, issue_no=issue_no, period=period)
        if digest_docs
        else None
    )
    topic_summaries: list[dict[str, Any]] = []
    for name, docs in topic_docs.items():
        if not docs:
            continue
        topic_summaries.append(
            await topics.generate_topic_summary(client, name, docs, updated_at=generated_at)
        )

    overview = await generate_overview(client, digest_obj, topic_summaries)
    return {
        "generatedAt": generated_at,
        "period": period,
        "issueNo": issue_no,
        "overview": overview,
        "digest": digest_obj,
        "topics": topic_summaries,
    }
