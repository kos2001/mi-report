"""뉴스 다이제스트 생성 — 수집 문서를 게이트웨이(LLM)로 요약·평가.

이 모듈이 AI agent 의 개입 지점이다: 수집된 문서(실데이터) → LLM → 구조화된
다이제스트(S.LSI 연관성·수요 영향·리스크·영향도). 순수 로직(프롬프트 구성·응답
파싱·검증)과 네트워크 호출(주입된 게이트웨이 클라이언트)을 분리해, 네트워크 없이
단위 테스트할 수 있게 한다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Protocol

from . import grounding, mi_wiki, progress, report_agents
from .llm_json import extract_json
from .schemas import DigestItemOut

# S.LSI 관점 MI 애널리스트 시스템 프롬프트. 도메인 제약(출처 근거·교차검증)을 명시한다.
DIGEST_SYSTEM_PROMPT = """당신은 반도체/IT 시장 인텔리전스(MI) 애널리스트다.
주어진 수집 문서들을 바탕으로 'S.LSI(시스템 LSI) 관점'의 뉴스 다이제스트를 작성한다.

규칙:
- 제공된 문서 내용에만 근거한다. 문서에 없는 수치·사실을 지어내지 않는다.
- 수치(매출·점유율·% 등)는 문서에 등장한 값을 그대로 옮긴다. 단위를 임의 환산하거나
  반올림해 새 숫자를 만들지 않는다. 근거가 없으면 수치를 쓰지 말고 정성 서술만 한다.
- source 는 그 항목의 근거가 된 문서의 '출처' 표기를 그대로 사용한다(지어내지 않는다).
- 각 항목에 S.LSI 제품군 연관성(slsiRelevance), 수요 변동 영향(demandImpact), 리스크(risk)를 명시한다.
  summary/slsiRelevance/demandImpact/risk 는 완결된 문장이 아니라 개조식으로 작성한다.
- 영향도(impact)는 high/medium/low 중 하나로 평가한다.
- 단일 출처에만 근거한 항목은 risk 에 '단일 출처 — 교차검증 필요'를 함께 적는다.
- 출력은 오직 JSON 객체 하나. 코드펜스/주석/설명 문장을 붙이지 않는다."""

DIGEST_SYSTEM_PROMPT += report_agents.OUTLINE_STYLE_DIRECTIVE + """

출력 형식:
{"items":[{"title":"...","source":"...","publishedAt":"YYYY-MM-DD",
  "summary":"...","slsiRelevance":"...","demandImpact":"...","risk":"...",
  "impact":"high|medium|low","tags":["..."]}]}
- 문자열 안의 큰따옴표(")와 역슬래시는 반드시 JSON 규칙에 맞게 이스케이프한다.
- 마지막 항목을 포함해 객체와 배열 사이의 쉼표를 빠뜨리지 말고, 출력 전 JSON 문법을 검증한다."""


class ChatClient(Protocol):
    """generate_digest 가 필요로 하는 게이트웨이 인터페이스(테스트용 페이크 주입 가능)."""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def current_week_label(dt: datetime.date | None = None) -> str:
    """다이제스트 식별자 — ISO 주차 기준 "YYYY년 W주차". 증가형 호수 대신 사용한다."""
    d = dt or datetime.date.today()
    year, week, _ = d.isocalendar()
    return f"{year}년 {week}주차"


def build_messages(
    docs: list[dict[str, Any]], feedback_notes: list[str] | None = None,
    wiki_context: str = "",
) -> list[dict[str, str]]:
    """수집 문서 목록을 chat 메시지로 구성한다."""
    blocks: list[str] = []
    for i, d in enumerate(docs, 1):
        blocks.append(
            f"[문서 {i}] 제목: {d.get('title', '')} | 출처: {d.get('source', '')} "
            f"| 발행: {d.get('publishedAt', '') or '미상'}\n{d.get('content', '')}"
        )
    user = "다음 수집 문서들을 근거로 다이제스트를 작성하라.\n\n" + "\n\n".join(blocks)
    if wiki_context:
        user += (
            "\n\n[이전 주차 LLM Wiki 맥락]\n"
            "아래 내용은 변화 비교를 위한 보조 맥락이다. 이번 초안의 사실·수치·출처는 "
            "반드시 위 원문 문서에 근거해야 하며, Wiki만을 근거로 새 항목을 만들지 마라.\n"
            + wiki_context
        )
    return [
        {"role": "system", "content": DIGEST_SYSTEM_PROMPT + report_agents.feedback_block(feedback_notes)},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    """OpenAI 호환 chat completion 에서 assistant content 를 꺼낸다."""
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


def parse_items(content: str) -> list[DigestItemOut]:
    """LLM 응답 문자열에서 다이제스트 항목을 파싱·검증한다."""
    data = extract_json(content)
    raw = data.get("items") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError("응답에 'items' 배열이 없음")
    return [DigestItemOut.model_validate(it) for it in raw]


def _retry_messages(
    docs: list[dict[str, Any]], feedback_notes: list[str] | None, error: ValueError,
    wiki_context: str,
) -> list[dict[str, str]]:
    """첫 응답의 JSON 문법이 깨졌을 때 사용할 1회 재생성 프롬프트."""
    messages = build_messages(docs, feedback_notes, wiki_context)
    messages[1]["content"] += (
        "\n\n이전 생성 응답이 JSON 문법 검증에 실패했다. 전체 결과를 처음부터 다시 생성하라. "
        "설명·코드펜스 없이 유효한 JSON 객체 하나만 출력하고, 문자열의 큰따옴표와 "
        f"역슬래시를 이스케이프하라. 이전 오류: {error}"
    )
    return messages


def _tokens(text: str) -> set[str]:
    """제목 대조용 토큰(2자 이상). 흔한 조사/일반어는 짧게 걸러진다."""
    return {t for t in re.findall(r"[\w가-힣]{2,}", (text or "").lower())}


def _verify_item(it: DigestItemOut, src_texts: list[str],
                 known_sources: list[str], doc_titles: list[str]) -> tuple[list[str], bool]:
    """항목의 (미근거 수치, 출처 검증여부)를 계산한다.

    환각 방어(MI 서비스): 정성 서술의 수치가 근거 문서에 실재하는지, 그리고 출처가
    실제 입력 문서에서 추적되는지(거짓 출처 귀속 방지) 검증한다.
    """
    prose = " ".join([it.summary, it.slsiRelevance, it.demandImpact, it.risk])
    ungrounded = grounding.ungrounded_numbers(prose, src_texts)

    src = (it.source or "").strip().lower()
    # 커넥터 문서는 source_name에는 수집기 이름(예: "컨센서스 갱신 감지"),
    # title에는 실제 발행처(예: "한경 컨센서스")를 둘 수 있다. 둘 다 provenance
    # 후보로 봐야 정상적인 발행처 표기가 거짓 출처로 오탐되지 않는다.
    provenance_labels = [*known_sources, *(title.strip().lower() for title in doc_titles)]
    source_verified = bool(src) and any(
        src in label or label in src for label in provenance_labels if label
    )
    if not source_verified:  # 발행처명이 달라도 입력 제목/본문에서 항목을 추적할 수 있으면 인정
        toks = _tokens(it.title)
        evidence_texts = [*doc_titles, *src_texts]
        source_verified = any(len(toks & _tokens(text)) >= 2 for text in evidence_texts)
    return ungrounded, source_verified


async def generate_digest(
    client: ChatClient,
    docs: list[dict[str, Any]],
    *,
    period: str,
    temperature: float = 0.2,
    on_progress: progress.ProgressFn | None = None,
    feedback_notes: list[str] | None = None,
) -> dict[str, Any]:
    """수집 문서로 다이제스트 초안을 생성한다(id·메타데이터는 서버가 부여)."""
    if not docs:
        raise ValueError("다이제스트로 만들 본문 있는 문서가 없습니다.")
    week = current_week_label()
    wiki_context = mi_wiki.digest_context(current_week=week)
    completion = await progress.track(
        client.chat(build_messages(docs, feedback_notes, wiki_context), temperature=temperature),
        on_progress, tool="digest_generate", emoji="📰", label="뉴스 다이제스트 초안 생성",
    )
    try:
        items = parse_items(extract_content(completion))
    except ValueError as first_error:
        # 생성형 모델은 간혹 긴 JSON 중간의 따옴표/쉼표를 깨뜨린다. 부분 문자열을
        # 임의 보정하면 내용이 변질될 수 있으므로, 낮은 temperature로 딱 한 번만
        # 전체 구조화 출력을 재생성한다.
        retry = await progress.track(
            client.chat(
                _retry_messages(docs, feedback_notes, first_error, wiki_context), temperature=0.0
            ),
            on_progress, tool="digest_json_retry", emoji="🔄", label="JSON 오류 자동 재생성",
        )
        try:
            items = parse_items(extract_content(retry))
        except ValueError as retry_error:
            raise ValueError(
                f"JSON 자동 재생성 후에도 파싱 실패: {retry_error}"
            ) from retry_error

    # 환각 방어: 항목별 수치 근거 + 출처 귀속 검증(비파괴적 — 플래그 후 사람이 검토).
    src_texts = [d.get("content", "") for d in docs]
    known_sources = [str(d.get("source", "")).strip().lower() for d in docs]
    doc_titles = [str(d.get("title", "")) for d in docs]
    all_ungrounded: list[str] = []
    unverified = 0
    out_items: list[dict[str, Any]] = []
    for i, it in enumerate(items, 1):
        ungrounded, source_verified = _verify_item(it, src_texts, known_sources, doc_titles)
        all_ungrounded.extend(ungrounded)
        unverified += int(not source_verified)
        out_items.append({
            "id": f"d{i}",
            **it.model_dump(),
            "numbersGrounded": not ungrounded,
            "ungroundedNumbers": ungrounded,
            "sourceVerified": source_verified,
        })

    union_ungrounded = list(dict.fromkeys(all_ungrounded))

    # 독립 검증 agent(V3-style): 항목 서술의 수치 아닌 주장(추세·인과) 중 근거 없는
    # 것을 별도로 잡는다. 위 grounding 검증은 수치만 본다.
    prose = " ".join(
        f"{it['summary']} {it['slsiRelevance']} {it['demandImpact']} {it['risk']}" for it in out_items
    )
    unsupported = await progress.track(
        report_agents.audit_overview(client, prose, src_texts),
        on_progress, tool="digest_audit", emoji="🔍", label="서술 근거 검증",
    )

    return {
        "week": week,
        "period": period,
        "mailedAt": None,  # 생성 직후는 발송 전 초안
        "generated": True,
        "sourceDocCount": len(docs),
        "items": out_items,
        "numbersGrounded": not union_ungrounded,
        "ungroundedNumbers": union_ungrounded,
        "unverifiedSourceCount": unverified,
        "unsupportedClaims": unsupported,
    }
