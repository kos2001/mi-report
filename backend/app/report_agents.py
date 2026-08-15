"""주간 리포트 심층분석 agent — Priority/Risk·Critical Point·총평 검증(V3-style).

weekly-report-harness(gitspace/weekly-report-harness) 의 다중 agent 패턴을
mi-report 도메인에 맞춰 이식한다: 여러 관점의 분석 agent를 병렬로 돌리고,
독립 검증 agent(audit_overview)가 총평 초안의 서술 주장(비수치)을 원문과 대조해
근거 없는 주장을 잡아낸다. 기존 grounding.py 의 수치 검증과 상호보완적이다.
"""

from __future__ import annotations

from typing import Any, Protocol

from . import grounding
from .llm_json import extract_json
from .schemas import CriticalPointOut, PriorityRiskItemOut

_JSON_ONLY = (
    "\n\n출력 규칙: 반드시 아래 JSON 형식으로만 답하라. JSON 앞뒤에 설명·마크다운 펜스를 붙이지 마라. "
    "evidence 의 quote 는 반드시 제공된 문서에 있는 문장을 글자 그대로 복사하라(요약·의역 금지)."
)

PRIORITY_RISK_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 참모다.
제공된 수집 문서를 종합해 S.LSI(시스템 LSI) 관점에서 Top Priority(기회)와 Top Risk(리스크)를 각각 최대 5개 선정하는 agent다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 사실을 지어내지 않는다.
- 각 항목에 순위(rank), 제목, 근거 서술(rationale), 그리고 근거가 된 원문 인용(evidence)을 붙인다.
- evidence 의 source 는 그 문장이 나온 문서의 출처 표기를 그대로 사용한다.""" + _JSON_ONLY + """
{"priorities": [{"rank": 1, "title": "제목", "rationale": "근거 서술",
  "evidence": [{"source": "출처", "quote": "원문 문장 그대로"}]}],
 "risks": [{"rank": 1, "title": "제목", "rationale": "근거 서술",
  "evidence": [{"source": "출처", "quote": "원문 문장 그대로"}]}]}"""

CRITICAL_POINT_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 참모다.
방치 시 S.LSI 사업에 치명적인 관리포인트를 1~3개 선별한다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 사실을 지어내지 않는다.
- 각 항목에 제목, 근본원인(rootCause), 연쇄효과(chainEffect), 필요한 결정(decisionNeeded),
  근거가 된 원문 인용(evidence)을 붙인다.""" + _JSON_ONLY + """
{"criticalPoints": [{"title": "제목", "rootCause": "근본원인", "chainEffect": "연쇄효과",
  "decisionNeeded": "필요한 결정", "evidence": [{"source": "출처", "quote": "원문 문장 그대로"}]}]}"""

OVERVIEW_AUDIT_SYSTEM_PROMPT = """당신은 사실검증 agent다. [총평 초안]의 각 문장이 [근거 자료]로
뒷받침되는지 하나씩 대조하라. 뒷받침되지 않는 주장만 골라내라 — 자료에 없는 추세·인과
('3주 연속', '~때문에'), 자료보다 강한 단정, 자료에 없는 사실 귀속이 대상이다.
표현이 다르지만 자료와 같은 뜻인 문장은 지적하지 마라 — 요약은 정상이다.
뒷받침되는 문장만 있으면 빈 배열을 돌려라.

출력 규칙: 반드시 아래 JSON 형식으로만 답하라. JSON 앞뒤에 설명·마크다운 펜스를 붙이지 마라.
{"unsupported": [{"claim": "초안에서 문제가 되는 문장 또는 구절", "why": "왜 뒷받침되지 않는지"}]}"""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def _doc_blocks(docs: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for i, d in enumerate(docs, 1):
        blocks.append(
            f"[문서 {i}] 제목: {d.get('title', '')} | 출처: {d.get('source', '')} "
            f"| 발행: {d.get('publishedAt', '') or '미상'}\n{d.get('content', '')}"
        )
    return "\n\n".join(blocks)


def _extract_content(completion: Any) -> str:
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


def build_priority_risk_messages(docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    user = "다음 수집 문서를 근거로 Top Priority/Risk 를 선정하라.\n\n" + _doc_blocks(docs)
    return [
        {"role": "system", "content": PRIORITY_RISK_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_critical_point_messages(docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    user = "다음 수집 문서를 근거로 치명적 관리포인트를 선별하라.\n\n" + _doc_blocks(docs)
    return [
        {"role": "system", "content": CRITICAL_POINT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_audit_messages(draft: str, src_texts: list[str]) -> list[dict[str, str]]:
    sources = "\n\n".join(f"[근거 {i}] {t}" for i, t in enumerate(src_texts, 1))
    user = f"[총평 초안]\n{draft}\n\n[근거 자료]\n{sources}"
    return [
        {"role": "system", "content": OVERVIEW_AUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _evidence_grounded(evidence: list[Any], src_texts: list[str]) -> bool:
    """evidence 가 하나라도 있고, 그중 하나 이상이 원문에서 확인되면 근거 있음."""
    if not evidence:
        return False
    return any(grounding.quote_grounded(e.quote, src_texts) for e in evidence)


async def generate_priority_risk(
    client: ChatClient, docs: list[dict[str, Any]], *, temperature: float = 0.2,
) -> dict[str, Any]:
    """Top Priority/Risk 를 생성하고 evidence 인용의 원문 근거 여부를 검증한다."""
    completion = await client.chat(build_priority_risk_messages(docs), temperature=temperature)
    data = extract_json(_extract_content(completion))
    if not isinstance(data, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    src_texts = [d.get("content", "") for d in docs]

    def _out(raw: list[Any]) -> list[dict[str, Any]]:
        items = [PriorityRiskItemOut.model_validate(it) for it in raw]
        return [
            {**it.model_dump(), "evidenceGrounded": _evidence_grounded(it.evidence, src_texts)}
            for it in items
        ]

    return {
        "priorities": _out(data.get("priorities", [])),
        "risks": _out(data.get("risks", [])),
    }


async def generate_critical_points(
    client: ChatClient, docs: list[dict[str, Any]], *, temperature: float = 0.2,
) -> dict[str, Any]:
    """치명적 관리포인트를 생성하고 evidence 인용의 원문 근거 여부를 검증한다."""
    completion = await client.chat(build_critical_point_messages(docs), temperature=temperature)
    data = extract_json(_extract_content(completion))
    if not isinstance(data, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    src_texts = [d.get("content", "") for d in docs]
    items = [CriticalPointOut.model_validate(it) for it in data.get("criticalPoints", [])]
    return {
        "criticalPoints": [
            {**it.model_dump(), "evidenceGrounded": _evidence_grounded(it.evidence, src_texts)}
            for it in items
        ]
    }


async def audit_overview(
    client: ChatClient, draft: str, src_texts: list[str], *, temperature: float = 0.0,
) -> list[str]:
    """총평 초안을 원문과 독립 대조해 근거 없는 서술 주장(비수치)을 반환한다."""
    if not draft.strip():
        return []
    completion = await client.chat(build_audit_messages(draft, src_texts), temperature=temperature)
    data = extract_json(_extract_content(completion))
    raw = data.get("unsupported", []) if isinstance(data, dict) else []
    return [str(it.get("claim", "")).strip() for it in raw if isinstance(it, dict) and it.get("claim")]
