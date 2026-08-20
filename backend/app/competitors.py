"""경쟁사 IR 분석 생성 — 경쟁사 실적/콜 문서를 게이트웨이(LLM)로 분기 분석화.

AI agent 개입 지점 #3: 경쟁사 IR·실적·컨퍼런스콜 문서 → LLM → 재무 요약,
콜 요약, 전분기 대비 변화, 컨센서스 추적. 재무 수치 환각을 막기 위해 시스템
프롬프트에서 '문서에 있는 수치만' 사용하도록 강하게 제약한다. 순수 로직과
네트워크 호출(주입된 게이트웨이 클라이언트)을 분리해 네트워크 없이 단위 테스트한다.
"""

from __future__ import annotations

from typing import Any, Protocol

from . import grounding, progress, report_agents
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
- callSummary/qoqChanges 의 각 항목은 완결된 문장이 아니라 개조식으로 작성한다.
- 출력은 오직 JSON 객체 하나. 코드펜스/주석/설명 문장을 붙이지 않는다."""

COMPETITOR_SYSTEM_PROMPT += report_agents.OUTLINE_STYLE_DIRECTIVE + """

출력 형식(값은 반드시 제공 문서에서 가져오고, 아래 꺾쇠 자리표시자를 그대로 베끼지 말 것):
{"fiscalQuarter":"<문서의 분기 표기>","reportedAt":"<YYYY-MM-DD 또는 미상>",
 "financials":[{"metric":"<지표명>","value":"<문서의 값 그대로>","qoq":<숫자 또는 null>,"yoy":<숫자 또는 null>}],
 "callSummary":["<문서 근거 요약>"],"qoqChanges":["<문서 근거 변화>"],
 "consensus":[{"metric":"<지표>","current":"<문서 값>","previous":"<문서 값 또는 빈칸>","revisedAt":"<날짜>","broker":"<증권사>","direction":"up|down|flat"}]}"""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_messages(
    name: str, ticker: str, docs: list[dict[str, Any]], feedback_notes: list[str] | None = None,
) -> list[dict[str, str]]:
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
        {"role": "system", "content": COMPETITOR_SYSTEM_PROMPT + report_agents.feedback_block(feedback_notes)},
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
    on_progress: progress.ProgressFn | None = None,
    feedback_notes: list[str] | None = None,
) -> dict[str, Any]:
    """경쟁사 문서로 분기 분석을 생성한다(id/name/ticker 는 서버가 부여)."""
    if not docs:
        raise ValueError("분석할 본문 있는 문서가 없습니다.")
    completion = await progress.track(
        client.chat(build_messages(name, ticker, docs, feedback_notes), temperature=temperature),
        on_progress, tool="competitor_generate", emoji="🏢", label=f"{name} 분기 분석 생성",
    )
    out = parse_analysis(extract_content(completion))

    # 환각 방어(재무 서비스): 수치가 근거 문서에 실재하지 않으면 그 항목을 버린다.
    # 재무·컨센서스의 '값'은 문서에 없는 숫자면 표시하지 않는다(환각 수치 노출 차단).
    src = [d.get("content", "") for d in docs]
    dropped: list[str] = []

    def _grounded_value(val: str) -> bool:
        bad = grounding.ungrounded_numbers(val or "", src)
        if bad:
            dropped.extend(bad)
            return False
        return True

    financials = [f for f in out.financials if _grounded_value(f.value)]
    consensus = [c for c in out.consensus if _grounded_value(c.current)]
    # 콜요약/변화의 미근거 수치도 함께 집계(표시는 유지하되 경고).
    g = grounding.check(" ".join([*out.callSummary, *out.qoqChanges]), src)
    ungrounded = list(dict.fromkeys([*dropped, *g["ungroundedNumbers"]]))

    # 독립 검증 agent(V3-style): 콜요약·변화 서술의 수치 아닌 주장(추세·인과) 중
    # 근거 없는 것을 별도로 잡는다. 위 grounding 검증은 수치만 본다.
    unsupported = await progress.track(
        report_agents.audit_overview(client, " ".join([*out.callSummary, *out.qoqChanges]), src),
        on_progress, tool="competitor_audit", emoji="🔍", label=f"{name} 서술 근거 검증",
    )

    return {
        "id": slugify(name),
        "name": name,
        "ticker": ticker,
        "fiscalQuarter": out.fiscalQuarter,
        "reportedAt": out.reportedAt,
        "financials": [f.model_dump() for f in financials],
        "callSummary": out.callSummary,
        "qoqChanges": out.qoqChanges,
        "consensus": [c.model_dump() for c in consensus],
        "sourceDocCount": len(docs),
        "generated": True,
        "numbersGrounded": not ungrounded,
        "ungroundedNumbers": ungrounded,
        "droppedCount": len(dropped),
        "unsupportedClaims": unsupported,
    }
