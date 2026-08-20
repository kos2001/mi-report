"""주간 MI 리포트 통합 생성 — 다이제스트(#1)·주제 요약(#2)을 묶어 한 편으로.

AI agent 개입 지점 #7: 개별 기능을 오케스트레이션해 '이번 주 리포트 초안'을
만든다. 다이제스트와 주제 요약을 생성한 뒤, 이를 종합한 총평(executive overview)을
게이트웨이로 한 번 더 생성한다. DB 접근은 호출자(엔드포인트)가 담당하고, 이 모듈은
이미 조회된 문서를 받아 오케스트레이션만 한다(네트워크 외 의존 없이 테스트 가능).
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from . import digest, grounding, progress, report_agents, topics

REPORT_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
이번 주 다이제스트 항목·주제 요약·Top Priority/Risk·치명적 관리포인트를 종합해
주간 리포트의 '총평'을 작성한다.

규칙:
- 제공된 자료에만 근거한다. 새로운 사실·수치를 지어내지 않는다.
- 이번 주의 핵심 흐름과 S.LSI(시스템 LSI) 관점 시사점을 3~5개 포인트로 정리한다.
- Priority/Risk·관리포인트가 있으면 그중 가장 중요한 것을 반영한다.
- 완결된 문장이 아니라 개조식으로 작성한다. 각 포인트는 줄바꿈 또는 '·'로 구분한다.
- 출력은 평문(개조식 텍스트)만. JSON/코드펜스/머리말을 붙이지 않는다."""


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_overview_messages(
    digest_obj: dict[str, Any] | None,
    topic_summaries: list[dict[str, Any]],
    priority_risk: dict[str, Any] | None = None,
    critical_points: dict[str, Any] | None = None,
    feedback_notes: list[str] | None = None,
) -> list[dict[str, str]]:
    parts: list[str] = []
    if digest_obj:
        # 제목뿐 아니라 (이미 근거검증된) 요약도 제공 — 총평이 실제 내용에 근거하도록.
        for it in digest_obj.get("items", []):
            parts.append(f"[다이제스트] {it.get('title', '')}: {it.get('summary', '')}")
    for t in topic_summaries:
        parts.append(f"[주제: {t.get('title', '')}] {t.get('summary', '')}")
    if priority_risk:
        for p in priority_risk.get("priorities", []):
            parts.append(f"[Priority {p.get('rank', '')}] {p.get('title', '')}: {p.get('rationale', '')}")
        for r in priority_risk.get("risks", []):
            parts.append(f"[Risk {r.get('rank', '')}] {r.get('title', '')}: {r.get('rationale', '')}")
    if critical_points:
        for c in critical_points.get("criticalPoints", []):
            parts.append(f"[관리포인트] {c.get('title', '')}: {c.get('rootCause', '')}")
    user = "다음 자료를 종합해 이번 주 MI 리포트 총평을 작성하라.\n\n" + "\n\n".join(parts)
    return [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT + report_agents.feedback_block(feedback_notes)},
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
    priority_risk: dict[str, Any] | None = None,
    critical_points: dict[str, Any] | None = None,
    *,
    temperature: float = 0.3,
    on_progress: progress.ProgressFn | None = None,
    feedback_notes: list[str] | None = None,
) -> str:
    completion = await progress.track(
        client.chat(
            build_overview_messages(
                digest_obj, topic_summaries, priority_risk, critical_points, feedback_notes,
            ),
            temperature=temperature,
        ),
        on_progress, tool="report_overview", emoji="✍️", label="총평 작성",
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
    on_progress: progress.ProgressFn | None = None,
    feedback_notes: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """다이제스트 + 주제 요약 + 총평을 묶어 주간 리포트를 생성한다.

    feedback_notes 는 종류별({"report": [...], "digest": [...], "topic": [...]})
    최근 부정 피드백 — 자기개선 loop: 각 하위 생성이 자기 종류의 피드백을,
    총평은 report 종류의 피드백을 프롬프트에 반영한다."""
    if not digest_docs and not topic_docs:
        raise ValueError("리포트로 만들 본문 있는 문서가 없습니다.")
    feedback_notes = feedback_notes or {}

    # 심층분석 agent(Priority/Risk·Critical Point)를 포함해 서로 독립인 LLM 호출은
    # 모두 동시 수행한다(weekly-report-harness 의 A1~A5 병렬 패턴). 총평·총평 검증만
    # 그 결과에 의존하므로 이후 순차 수행. 각 태스크가 스스로 시작·완료 이벤트를
    # 내므로(progress.track) 동시 실행 순서와 무관하게 실제 완료 순서가 그대로 보인다.
    named_topics = [(name, docs) for name, docs in topic_docs.items() if docs]
    all_docs = list(digest_docs)
    for docs in topic_docs.values():
        all_docs.extend(docs)
    digest_task = (
        digest.generate_digest(
            client, digest_docs, period=period, on_progress=on_progress,
            feedback_notes=feedback_notes.get("digest"),
        )
        if digest_docs
        else None
    )
    priority_risk_task = (
        progress.track(
            report_agents.generate_priority_risk(client, all_docs),
            on_progress, tool="priority_risk", emoji="🎯", label="Top Priority/Risk 분석",
        )
        if all_docs else None
    )
    critical_point_task = (
        progress.track(
            report_agents.generate_critical_points(client, all_docs),
            on_progress, tool="critical_point", emoji="⚠️", label="치명적 관리포인트 분석",
        )
        if all_docs else None
    )
    parallel_tasks = [
        t for t in (digest_task, priority_risk_task, critical_point_task) if t is not None
    ]
    topic_tasks = [
        topics.generate_topic_summary(
            client, name, docs, updated_at=generated_at, on_progress=on_progress,
            feedback_notes=feedback_notes.get("topic"),
        )
        for name, docs in named_topics
    ]
    results = await asyncio.gather(*parallel_tasks, *topic_tasks)
    n_parallel = len(parallel_tasks)
    parallel_results = results[:n_parallel]
    topic_summaries = list(results[n_parallel:])
    digest_obj = parallel_results.pop(0) if digest_task else None
    priority_risk = parallel_results.pop(0) if priority_risk_task else None
    critical_points = parallel_results.pop(0) if critical_point_task else None

    overview = await generate_overview(
        client, digest_obj, topic_summaries, priority_risk, critical_points,
        on_progress=on_progress, feedback_notes=feedback_notes.get("report"),
    )

    # 환각 방어(MI 서비스): 총평의 수치를 실제 근거 문서(다이제스트·주제 원문)와 대조하고,
    # 하위 산출물(다이제스트·주제 요약)의 미근거 수치를 리포트 수준으로 롤업한다.
    src_texts = [d.get("content", "") for d in digest_docs]
    for docs in topic_docs.values():
        src_texts.extend(d.get("content", "") for d in docs)
    overview_ungrounded = grounding.ungrounded_numbers(overview, src_texts)
    # 독립 검증 agent(V3-style): 수치가 아닌 서술 주장 중 근거 없는 것을 별도로 잡는다.
    overview_unsupported = await progress.track(
        report_agents.audit_overview(client, overview, src_texts),
        on_progress, tool="report_overview_audit", emoji="🔍", label="총평 근거 검증",
    )

    rolled = list(overview_ungrounded)
    if digest_obj:
        rolled.extend(digest_obj.get("ungroundedNumbers", []))
    for t in topic_summaries:
        rolled.extend(t.get("ungroundedNumbers", []))
    rolled = list(dict.fromkeys(rolled))

    return {
        "generatedAt": generated_at,
        "period": period,
        "issueNo": issue_no,
        "overview": overview,
        "overviewGrounded": not overview_ungrounded,
        "overviewUngroundedNumbers": overview_ungrounded,
        "overviewUnsupportedClaims": overview_unsupported,
        "digest": digest_obj,
        "topics": topic_summaries,
        "priorities": priority_risk.get("priorities", []) if priority_risk else [],
        "risks": priority_risk.get("risks", []) if priority_risk else [],
        "criticalPoints": critical_points.get("criticalPoints", []) if critical_points else [],
        "numbersGrounded": not rolled,
        "ungroundedNumbers": rolled,
    }


# ── 문서(Markdown) 렌더 + 템플릿 ──────────────────────────────────────────
# 템플릿은 {{placeholder}} 토큰을 채워 완성한다. 지원 토큰:
#   {{issue_no}} {{period}} {{generated_at}} {{overview}} {{digest}} {{topics}}
DEFAULT_REPORT_TEMPLATE = """# 주간 MI 리포트 제{{issue_no}}호

**기간**: {{period}}  |  **생성일**: {{generated_at}}

## 총평
{{overview}}

## Top Priority / Risk
{{priority_risk}}

## 치명적 관리포인트
{{critical_points}}

## 뉴스 다이제스트
{{digest}}

## 주제별 동향
{{topics}}

---
_본 리포트는 수집 문서를 근거로 AI가 생성한 초안이며, 발송 전 사람의 검토가 필요합니다._
"""

REPORT_PLACEHOLDERS = (
    "issue_no", "period", "generated_at", "overview",
    "priority_risk", "critical_points", "digest", "topics",
)


def _render_digest_md(digest_obj: dict[str, Any] | None) -> str:
    if not digest_obj or not digest_obj.get("items"):
        return "_생성된 다이제스트 항목이 없습니다._"
    lines: list[str] = []
    for it in digest_obj["items"]:
        lines.append(f"### [{it.get('impact', 'medium')}] {it.get('title', '')}")
        if it.get("summary"):
            lines.append(it["summary"])
        meta = [
            ("S.LSI 연관성", it.get("slsiRelevance")),
            ("수요 변동", it.get("demandImpact")),
            ("리스크", it.get("risk")),
        ]
        for label, val in meta:
            if val:
                lines.append(f"- **{label}**: {val}")
        lines.append("")
    return "\n".join(lines).strip()


def _render_priority_risk_md(priorities: list[dict[str, Any]], risks: list[dict[str, Any]]) -> str:
    if not priorities and not risks:
        return "_선정된 Priority/Risk 가 없습니다._"
    lines: list[str] = []
    if priorities:
        lines.append("**Priority**")
        for p in priorities:
            flag = "" if p.get("evidenceGrounded", True) else " ⚠ 근거 미확인"
            lines.append(f"{p.get('rank', '')}. {p.get('title', '')} — {p.get('rationale', '')}{flag}")
        lines.append("")
    if risks:
        lines.append("**Risk**")
        for r in risks:
            flag = "" if r.get("evidenceGrounded", True) else " ⚠ 근거 미확인"
            lines.append(f"{r.get('rank', '')}. {r.get('title', '')} — {r.get('rationale', '')}{flag}")
    return "\n".join(lines).strip()


def _render_critical_points_md(critical_points: list[dict[str, Any]]) -> str:
    if not critical_points:
        return "_선별된 관리포인트가 없습니다._"
    lines: list[str] = []
    for c in critical_points:
        flag = "" if c.get("evidenceGrounded", True) else " ⚠ 근거 미확인"
        lines.append(f"### {c.get('title', '')}{flag}")
        if c.get("rootCause"):
            lines.append(f"- **근본원인**: {c['rootCause']}")
        if c.get("chainEffect"):
            lines.append(f"- **연쇄효과**: {c['chainEffect']}")
        if c.get("decisionNeeded"):
            lines.append(f"- **필요한 결정**: {c['decisionNeeded']}")
        lines.append("")
    return "\n".join(lines).strip()


def _render_topics_md(topic_summaries: list[dict[str, Any]]) -> str:
    if not topic_summaries:
        return "_요약된 주제가 없습니다._"
    lines: list[str] = []
    for t in topic_summaries:
        cat = t.get("category", "")
        lines.append(f"### {t.get('title', '')}" + (f" ({cat})" if cat else ""))
        if t.get("summary"):
            lines.append(t["summary"])
        if t.get("insight"):
            lines.append(f"- **인사이트**: {t['insight']}")
        lines.append("")
    return "\n".join(lines).strip()


def render_report_markdown(report: dict[str, Any], template: str | None = None) -> str:
    """리포트(dict)를 템플릿에 채워 Markdown 문서로 렌더한다.

    template 미지정 시 DEFAULT_REPORT_TEMPLATE 사용. {{토큰}}만 치환하며,
    템플릿에 없는 섹션은 자연히 빠진다(사용자 정의 템플릿 자유도 보장).
    """
    tmpl = template if (template and template.strip()) else DEFAULT_REPORT_TEMPLATE
    values = {
        "issue_no": str(report.get("issueNo", "")),
        "period": report.get("period") or "—",
        "generated_at": report.get("generatedAt") or "—",
        "overview": report.get("overview") or "_총평이 없습니다._",
        "priority_risk": _render_priority_risk_md(report.get("priorities", []), report.get("risks", [])),
        "critical_points": _render_critical_points_md(report.get("criticalPoints", [])),
        "digest": _render_digest_md(report.get("digest")),
        "topics": _render_topics_md(report.get("topics", [])),
    }
    out = tmpl
    for key in REPORT_PLACEHOLDERS:
        out = out.replace("{{" + key + "}}", values[key])
    # 환각 방어: 미근거 수치·근거 없는 서술 주장이 있으면 문서 상단(제목 다음)에 검토 경고를 덧붙인다.
    ungrounded = report.get("ungroundedNumbers") or []
    unsupported = report.get("overviewUnsupportedClaims") or []
    if ungrounded or unsupported:
        bits = []
        if ungrounded:
            bits.append("다음 수치는 제공 문서에서 그대로 확인되지 않았습니다: " + ", ".join(ungrounded[:10]))
        if unsupported:
            claims = [
                f"{u.get('claim', '')}({u['why']})" if isinstance(u, dict) and u.get("why") else
                (u.get("claim", "") if isinstance(u, dict) else str(u))
                for u in unsupported[:5]
            ]
            bits.append("다음 총평 서술은 근거가 확인되지 않았습니다: " + " / ".join(claims))
        notice = "> ⚠ **검토 필요** — " + " ".join(bits) + "\n\n"
        if out.startswith("# "):
            nl = out.find("\n")
            out = out[: nl + 1] + "\n" + notice + out[nl + 1:]
        else:
            out = notice + out
    return out
