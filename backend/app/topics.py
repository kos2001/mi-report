"""주제별 History 생성 — 한 주제의 누적 수집 문서를 게이트웨이(LLM)로 정리.

AI agent 개입 지점 #2: 같은 주제로 시간순 누적된 문서 → LLM → 누적 요약 +
S.LSI 시황 연계 인사이트 + 사건 타임라인. 순수 로직(프롬프트·파싱·검증)과
네트워크 호출(주입된 게이트웨이 클라이언트)을 분리해 네트워크 없이 단위 테스트한다.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from .llm_json import extract_json
from .schemas import TopicSummaryOut

TOPIC_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
하나의 '주제'에 대해 시간순으로 누적된 수집 문서들을 받아, 주제 이력을 정리한다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 사실·수치를 지어내지 않는다.
- category 는 다음 중 하나로 분류한다: "SET", "반도체 설계", "반도체 제조", "수요/시황".
- summary: 주제의 현재 상황을 누적 관점에서 3~5문장으로 요약한다.
- insight: S.LSI(시스템 LSI)/SET 시황과의 연계 시사점을 1~3문장으로 제시한다.
- history: 주요 사건을 시간 역순으로 정리한다(date=YYYY-MM-DD, event, source).
  문서의 발행일·출처를 활용하고, 근거가 약한 항목은 넣지 않는다.
- 출력은 오직 JSON 객체 하나. 코드펜스/주석/설명 문장을 붙이지 않는다.

출력 형식:
{"category":"...","summary":"...","insight":"...",
 "history":[{"date":"YYYY-MM-DD","event":"...","source":"..."}]}"""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def slugify(title: str) -> str:
    """주제명을 안정적인 id 슬러그로 변환(영숫자/한글 유지, 공백→하이픈)."""
    s = title.strip().lower()
    s = re.sub(r"[^\w가-힣]+", "-", s, flags=re.UNICODE)
    return s.strip("-") or "topic"


def build_messages(topic_title: str, docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    blocks: list[str] = []
    for i, d in enumerate(docs, 1):
        blocks.append(
            f"[문서 {i}] 제목: {d.get('title', '')} | 출처: {d.get('source', '')} "
            f"| 발행: {d.get('publishedAt', '') or '미상'}\n{d.get('content', '')}"
        )
    user = (
        f"주제: {topic_title}\n\n"
        "다음은 이 주제로 누적된 수집 문서들이다. 이를 근거로 주제 이력을 정리하라.\n\n"
        + "\n\n".join(blocks)
    )
    return [
        {"role": "system", "content": TOPIC_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


def parse_summary(content: str) -> TopicSummaryOut:
    data = extract_json(content)
    if not isinstance(data, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    return TopicSummaryOut.model_validate(data)


async def generate_topic_summary(
    client: ChatClient,
    topic_title: str,
    docs: list[dict[str, Any]],
    *,
    updated_at: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """주제 누적 문서로 이력·인사이트를 생성한다(id/메타데이터는 서버가 부여)."""
    if not docs:
        raise ValueError("요약할 본문 있는 문서가 없습니다.")
    completion = await client.chat(build_messages(topic_title, docs), temperature=temperature)
    out = parse_summary(extract_content(completion))
    return {
        "id": slugify(topic_title),
        "title": topic_title,
        "category": out.category,
        "summary": out.summary,
        "insight": out.insight,
        "sourceCount": len(docs),
        "updatedAt": updated_at,
        "generated": True,
        "history": [h.model_dump() for h in out.history],
    }
