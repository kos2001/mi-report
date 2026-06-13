"""경쟁사 IR 분석 생성 — 경쟁사 실적/콜 문서를 게이트웨이(LLM)로 분기 분석화.

AI agent 개입 지점 #3: 경쟁사 IR·실적·컨퍼런스콜 문서 → LLM → 재무 요약,
콜 요약, 전분기 대비 변화, 컨센서스 추적. 재무 수치 환각을 막기 위해 시스템
프롬프트에서 '문서에 있는 수치만' 사용하도록 강하게 제약한다. 순수 로직과
네트워크 호출(주입된 게이트웨이 클라이언트)을 분리해 네트워크 없이 단위 테스트한다.
"""

from __future__ import annotations

from typing import Any, Protocol

from .llm_json import extract_json
from .schemas import CompetitorAnalysisOut
from .topics import slugify

COMPETITOR_SYSTEM_PROMPT = """당신은 반도체/IT 기업 IR·실적을 분석하는 MI 애널리스트다.
주어진 경쟁사 IR·실적·컨퍼런스콜 문서에서 분기 분석을 구조화한다.

규칙:
- 제공된 문서에 실제로 등장하는 수치만 사용한다. 문서에 없는 재무 수치를 지어내지 않는다.
  값이 없으면 항목을 생략하거나 value 를 "미상"으로, qoq/yoy 는 null 로 둔다.
- financials: metric/value(문서 표기 그대로)/qoq/yoy(% 숫자, 없으면 null).
- callSummary: 컨퍼런스콜·경영진 코멘트의 핵심을 항목화한다.
- qoqChanges: 전분기 대비 달라진 점(톤/내러티브/수치 변화). 문서에 근거가 있을 때만 적는다.
- consensus: 증권사 컨센서스 갱신(metric/current/previous/revisedAt/broker/direction=up|down|flat).
- 출력은 오직 JSON 객체 하나. 코드펜스/주석/설명 문장을 붙이지 않는다.

출력 형식:
{"fiscalQuarter":"...","reportedAt":"YYYY-MM-DD",
 "financials":[{"metric":"매출","value":"$11.7B","qoq":3.2,"yoy":12.4}],
 "callSummary":["..."],"qoqChanges":["..."],
 "consensus":[{"metric":"...","current":"...","previous":"...","revisedAt":"...","broker":"...","direction":"flat"}]}"""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_messages(name: str, ticker: str, docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    blocks: list[str] = []
    for i, d in enumerate(docs, 1):
        blocks.append(
            f"[문서 {i}] 제목: {d.get('title', '')} | 출처: {d.get('source', '')} "
            f"| 발행: {d.get('publishedAt', '') or '미상'}\n{d.get('content', '')}"
        )
    label = f"{name}" + (f" ({ticker})" if ticker else "")
    user = (
        f"경쟁사: {label}\n\n"
        "다음은 이 경쟁사의 IR·실적·콜 관련 수집 문서들이다. 이를 근거로 분기 분석을 작성하라.\n\n"
        + "\n\n".join(blocks)
    )
    return [
        {"role": "system", "content": COMPETITOR_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


def parse_analysis(content: str) -> CompetitorAnalysisOut:
    data = extract_json(content)
    if not isinstance(data, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    return CompetitorAnalysisOut.model_validate(data)


async def analyze_competitor(
    client: ChatClient,
    name: str,
    ticker: str,
    docs: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """경쟁사 문서로 분기 분석을 생성한다(id/name/ticker 는 서버가 부여)."""
    if not docs:
        raise ValueError("분석할 본문 있는 문서가 없습니다.")
    completion = await client.chat(build_messages(name, ticker, docs), temperature=temperature)
    out = parse_analysis(extract_content(completion))
    return {
        "id": slugify(name),
        "name": name,
        "ticker": ticker,
        "fiscalQuarter": out.fiscalQuarter,
        "reportedAt": out.reportedAt,
        "financials": [f.model_dump() for f in out.financials],
        "callSummary": out.callSummary,
        "qoqChanges": out.qoqChanges,
        "consensus": [c.model_dump() for c in out.consensus],
        "sourceDocCount": len(docs),
        "generated": True,
    }
