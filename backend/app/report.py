"""주간 MI 리포트 통합 생성 — 다이제스트(#1)·주제 요약(#2)을 묶어 한 편으로.

AI agent 개입 지점 #7: 개별 기능을 오케스트레이션해 '이번 주 리포트 초안'을
만든다. 다이제스트와 주제 요약을 생성한 뒤, 이를 종합한 총평(executive overview)을
게이트웨이로 한 번 더 생성한다. DB 접근은 호출자(엔드포인트)가 담당하고, 이 모듈은
이미 조회된 문서를 받아 오케스트레이션만 한다(네트워크 외 의존 없이 테스트 가능).
"""

from __future__ import annotations

from typing import Any, Protocol

from . import digest, grounding, topics

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
        # 제목뿐 아니라 (이미 근거검증된) 요약도 제공 — 총평이 실제 내용에 근거하도록.
        for it in digest_obj.get("items", []):
            parts.append(f"[다이제스트] {it.get('title', '')}: {it.get('summary', '')}")
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

    # 환각 방어(MI 서비스): 총평의 수치를 실제 근거 문서(다이제스트·주제 원문)와 대조하고,
    # 하위 산출물(다이제스트·주제 요약)의 미근거 수치를 리포트 수준으로 롤업한다.
    src_texts = [d.get("content", "") for d in digest_docs]
    for docs in topic_docs.values():
        src_texts.extend(d.get("content", "") for d in docs)
    overview_ungrounded = grounding.ungrounded_numbers(overview, src_texts)

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
        "digest": digest_obj,
        "topics": topic_summaries,
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

## 뉴스 다이제스트
{{digest}}

## 주제별 동향
{{topics}}

---
_본 리포트는 수집 문서를 근거로 AI가 생성한 초안이며, 발송 전 사람의 검토가 필요합니다._
"""

REPORT_PLACEHOLDERS = ("issue_no", "period", "generated_at", "overview", "digest", "topics")


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
        "digest": _render_digest_md(report.get("digest")),
        "topics": _render_topics_md(report.get("topics", [])),
    }
    out = tmpl
    for key in REPORT_PLACEHOLDERS:
        out = out.replace("{{" + key + "}}", values[key])
    # 환각 방어: 미근거 수치가 있으면 문서 상단(제목 다음)에 검토 경고를 덧붙인다.
    ungrounded = report.get("ungroundedNumbers") or []
    if ungrounded:
        notice = (
            "> ⚠ **검토 필요** — 다음 수치는 제공 문서에서 그대로 확인되지 않았습니다: "
            + ", ".join(ungrounded[:10]) + "\n\n"
        )
        if out.startswith("# "):
            nl = out.find("\n")
            out = out[: nl + 1] + "\n" + notice + out[nl + 1:]
        else:
            out = notice + out
    return out
