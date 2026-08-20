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

# 모든 생성 agent(digest/topics/competitors/report/rag)가 공통으로 덧붙이는 문체 지침.
# evidence.quote 처럼 원문을 그대로 복사해야 하는 필드는 예외(원문 문장을 그대로 인용).
OUTLINE_STYLE_DIRECTIVE = """

문체 규칙(개조식): summary/insight/rationale/callSummary 등 서술형 답변은 완결된
문장(~습니다/~한다/~했다)이 아니라 개조식으로 작성한다. 핵심 정보만 명사형으로
끝내고(예: '~달성', '~진행', '~필요', '~식별'), 불필요한 조사·연결어·수식어를 줄인다.
서로 다른 요점은 '·'로 구분해 나열한다.
예: "ISOCELLIPS 진행률 72% · 8월 양산 수율 93% 달성 · 인력·장비 리소스 이슈 식별 ·
고객 대응 3건 완료"
(단, 원문을 그대로 인용해야 하는 quote/evidence 필드는 이 규칙에서 제외 — 원문 문장 그대로 복사)"""

PRIORITY_RISK_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 참모다.
제공된 수집 문서를 종합해 S.LSI(시스템 LSI) 관점에서 Top Priority(기회)와 Top Risk(리스크)를 각각 최대 5개 선정하는 agent다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 사실을 지어내지 않는다.
- 각 항목에 순위(rank), 제목, 근거 서술(rationale), 그리고 근거가 된 원문 인용(evidence)을 붙인다.
- evidence 의 source 는 그 문장이 나온 문서의 출처 표기를 그대로 사용한다.""" + OUTLINE_STYLE_DIRECTIVE + _JSON_ONLY + """
{"priorities": [{"rank": 1, "title": "제목", "rationale": "근거 서술",
  "evidence": [{"source": "출처", "quote": "원문 문장 그대로"}]}],
 "risks": [{"rank": 1, "title": "제목", "rationale": "근거 서술",
  "evidence": [{"source": "출처", "quote": "원문 문장 그대로"}]}]}"""

CRITICAL_POINT_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 참모다.
방치 시 S.LSI 사업에 치명적인 관리포인트를 1~3개 선별한다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 사실을 지어내지 않는다.
- 각 항목에 제목, 근본원인(rootCause), 연쇄효과(chainEffect), 필요한 결정(decisionNeeded),
  근거가 된 원문 인용(evidence)을 붙인다.""" + OUTLINE_STYLE_DIRECTIVE + _JSON_ONLY + """
{"criticalPoints": [{"title": "제목", "rootCause": "근본원인", "chainEffect": "연쇄효과",
  "decisionNeeded": "필요한 결정", "evidence": [{"source": "출처", "quote": "원문 문장 그대로"}]}]}"""

OVERVIEW_AUDIT_SYSTEM_PROMPT = """당신은 사실검증 agent다. [총평 초안]의 각 문장이 [근거 자료]로
뒷받침되는지 하나씩 대조한다.

**분석적 해석은 정상이다.** "이 사건이 S.LSI에 미치는 영향", "~와 경쟁 구도에 있다",
"~인접 밸류체인이다" 처럼 원문의 사실을 근거로 그 함의·연관성을 추론하는 문장은, 그
해석·인과 자체가 원문에 문자 그대로 쓰여 있지 않아도 지적하지 마라 — 그런 해석을
도출하는 것이 이 서비스의 목적이며, MI 애널리스트의 정상적인 업무다. 다만 그 해석이
딛고 선 **사실 자체**는 원문에 실재해야 한다. 예를 들어 "A사가 신제품을 출시했다"는
사실이 원문에 없는데 지어냈다면 지적 대상이지만, 그 출시가 "S.LSI 라인업과 직접
경쟁한다"는 해석·평가 자체는 원문에 없어도 정상이다.

뒷받침되지 않는 주장만 골라내라 — 대상은 다음 셋뿐이다:
①원문에 없는 사건·수치·추세를 실제 일어난 사실처럼 서술(예: 원문에 없는 '3주 연속',
실제로 보도되지 않은 사건),
②원문보다 강한 단정(원문은 '검토 중'·'예정'인데 초안은 '확정'·'이미 발생'으로 서술),
③원문에 없는 주체 귀속(다른 회사·팀이 한 일을 엉뚱한 주체가 한 것처럼 서술).
표현이 다르지만 자료와 같은 뜻인 문장, 그리고 실재하는 사실에 근거한 해석·함의·연관성
서술은 절대 지적하지 마라. 뒷받침되는 문장만 있으면 빈 배열을 돌려라.

출력 규칙: 반드시 아래 JSON 형식으로만 답하라. JSON 앞뒤에 설명·마크다운 펜스를 붙이지 마라.
{"unsupported": [{"claim": "초안에서 문제가 되는 문장 또는 구절", "why": "왜 뒷받침되지 않는지"}]}"""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def feedback_block(notes: list[str] | None) -> str:
    """자기개선 loop: 이 종류 생성물에 대한 최근 👎 피드백을 시스템 프롬프트에
    덧붙일 블록으로 변환한다(없으면 빈 문자열 — 기존 프롬프트와 동일하게 동작).
    digest/topics/competitors/report 의 시스템 프롬프트가 공통으로 쓴다."""
    if not notes:
        return ""
    bullets = "\n".join(f"- {n}" for n in notes)
    return f"\n\n[과거 피드백 — 이전 생성물에서 지적된 문제. 이번엔 같은 문제를 반복하지 마라]\n{bullets}"


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
) -> list[dict[str, str]]:
    """총평 초안을 원문과 독립 대조해 근거 없는 서술 주장(비수치)을 반환한다.

    각 항목은 {"claim": 문제되는 서술, "why": 왜 근거가 없는지} — 자기개선 loop(품질
    page)이 "근거 없는 서술 N건"이라는 숫자만이 아니라 실제 이유를 보여줄 수 있어야 한다.
    """
    if not draft.strip():
        return []
    completion = await client.chat(build_audit_messages(draft, src_texts), temperature=temperature)
    data = extract_json(_extract_content(completion))
    raw = data.get("unsupported", []) if isinstance(data, dict) else []
    return [
        {"claim": str(it.get("claim", "")).strip(), "why": str(it.get("why", "")).strip()}
        for it in raw
        if isinstance(it, dict) and it.get("claim")
    ]
