"""뉴스 다이제스트 생성 — 수집 문서를 게이트웨이(LLM)로 요약·평가.

이 모듈이 AI agent 의 개입 지점이다: 수집된 문서(실데이터) → LLM → 구조화된
다이제스트(S.LSI 연관성·수요 영향·리스크·영향도). 순수 로직(프롬프트 구성·응답
파싱·검증)과 네트워크 호출(주입된 게이트웨이 클라이언트)을 분리해, 네트워크 없이
단위 테스트할 수 있게 한다.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from .schemas import DigestItemOut

# S.LSI 관점 MI 애널리스트 시스템 프롬프트. 도메인 제약(출처 근거·교차검증)을 명시한다.
DIGEST_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
주어진 수집 문서들을 바탕으로 'S.LSI(시스템 LSI) 관점'의 뉴스 다이제스트를 작성한다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 수치·사실을 지어내지 않는다.
- 각 항목에 S.LSI 제품군 연관성(slsiRelevance), 수요 변동 영향(demandImpact), 리스크(risk)를 명시한다.
- 영향도(impact)는 high/medium/low 중 하나로 평가한다.
- 단일 출처에만 근거한 항목은 risk 에 '단일 출처 — 교차검증 필요'를 함께 적는다.
- 출력은 오직 JSON 객체 하나. 코드펜스/주석/설명 문장을 붙이지 않는다.

출력 형식:
{"items":[{"title":"...","source":"...","publishedAt":"YYYY-MM-DD",
  "summary":"...","slsiRelevance":"...","demandImpact":"...","risk":"...",
  "impact":"high|medium|low","tags":["..."]}]}"""


class ChatClient(Protocol):
    """generate_digest 가 필요로 하는 게이트웨이 인터페이스(테스트용 페이크 주입 가능)."""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_messages(docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """수집 문서 목록을 chat 메시지로 구성한다."""
    blocks: list[str] = []
    for i, d in enumerate(docs, 1):
        blocks.append(
            f"[문서 {i}] 제목: {d.get('title', '')} | 출처: {d.get('source', '')} "
            f"| 발행: {d.get('publishedAt', '') or '미상'}\n{d.get('content', '')}"
        )
    user = "다음 수집 문서들을 근거로 다이제스트를 작성하라.\n\n" + "\n\n".join(blocks)
    return [
        {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    """OpenAI 호환 chat completion 에서 assistant content 를 꺼낸다."""
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


def parse_items(content: str) -> list[DigestItemOut]:
    """LLM 응답 문자열에서 다이제스트 항목을 파싱·검증한다.

    코드펜스나 잡음이 섞여도 첫 '{' ~ 마지막 '}' 구간을 JSON 으로 취한다.
    """
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"응답에서 JSON 객체를 찾지 못함: {content[:200]!r}")
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"다이제스트 JSON 파싱 실패: {e}") from e
    raw = data.get("items") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError("응답에 'items' 배열이 없음")
    return [DigestItemOut.model_validate(it) for it in raw]


async def generate_digest(
    client: ChatClient,
    docs: list[dict[str, Any]],
    *,
    issue_no: int,
    period: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """수집 문서로 다이제스트 초안을 생성한다(id·메타데이터는 서버가 부여)."""
    if not docs:
        raise ValueError("다이제스트로 만들 본문 있는 문서가 없습니다.")
    completion = await client.chat(build_messages(docs), temperature=temperature)
    items = parse_items(extract_content(completion))
    return {
        "issueNo": issue_no,
        "period": period,
        "mailedAt": None,  # 생성 직후는 발송 전 초안
        "generated": True,
        "sourceDocCount": len(docs),
        "items": [{"id": f"d{i}", **it.model_dump()} for i, it in enumerate(items, 1)],
    }
