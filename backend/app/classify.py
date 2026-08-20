"""문서 자동 분류 — 수집 문서 본문을 게이트웨이(LLM)로 주제·카테고리 태깅.

AI agent 개입 지점 #5: 인제스트된 문서(특히 주제 미부여분)를 LLM 으로 분류해
topic 을 자동 부여한다. 이렇게 태깅된 문서는 주제별 History(#2)·경쟁사 IR(#3)의
입력으로 바로 쓰인다. 순수 로직과 네트워크 호출(주입된 클라이언트)을 분리한다.
"""

from __future__ import annotations

from typing import Any, Protocol

from .llm_json import extract_json
from .schemas import DocClassificationOut

CLASSIFY_SYSTEM_PROMPT = """반도체/IT 시장 인텔리전스(MI) 문서를 분류한다.
제목과 본문을 보고 다음을 판단한다:
- topic: 문서의 핵심 주제를 짧은 한국어 명사구로 정한다(예: "HBM 수요", "2nm 파운드리",
  "온디바이스 AI"). 같은 주제의 다른 문서와 묶일 수 있도록 지나치게 구체적이지 않게.
- category: "SET" | "반도체 설계" | "반도체 제조" | "수요/시황" 중 하나.
- tags: 핵심 키워드 2~5개.
- 제공된 내용에만 근거한다. 출력은 오직 JSON 객체 하나. 코드펜스/설명 금지.

출력 형식:
{"topic":"...","category":"...","tags":["..."]}"""

# 새 문서 분류 시 이미 있는 주제 목록을 함께 보여줘, 같은 사안이면 새 문자열을
# 만들지 않고 기존 주제를 그대로 재사용하도록 유도한다. topic 은 LLM 이 매번 자유
# 생성하는 문자열이라, 이 유도가 없으면 "HBM 수요"/"HBM4 수요 확대"처럼 같은 주제가
# 표현만 다르게 갈라져 주제별 History 가 조각난다.
_EXISTING_TOPICS_RULE = (
    "\n\n[기존 주제 목록 — 같은 사안이면 아래 중 하나를 정확히 그대로 재사용하라. "
    "새 사안일 때만 새 주제명을 만들어라]\n{topics}"
)


class ChatClient(Protocol):
    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


def build_messages(
    title: str, content: str, existing_topics: list[str] | None = None,
) -> list[dict[str, str]]:
    system = CLASSIFY_SYSTEM_PROMPT
    if existing_topics:
        system += _EXISTING_TOPICS_RULE.format(topics=", ".join(existing_topics))
    user = f"제목: {title}\n\n본문:\n{content}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_content(completion: Any) -> str:
    try:
        return completion["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"예상치 못한 completion 형식: {completion!r}") from e


def parse_classification(content: str) -> DocClassificationOut:
    data = extract_json(content)
    if not isinstance(data, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    return DocClassificationOut.model_validate(data)


async def classify_document(
    client: ChatClient, title: str, content: str, *,
    temperature: float = 0.1, existing_topics: list[str] | None = None,
) -> dict[str, Any]:
    """문서 제목·본문으로 topic/category/tags 를 분류한다."""
    completion = await client.chat(
        build_messages(title, content, existing_topics), temperature=temperature,
    )
    return parse_classification(extract_content(completion)).model_dump()
