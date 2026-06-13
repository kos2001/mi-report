"""LLM 응답에서 JSON 을 견고하게 추출한다.

다이제스트·주제 요약 등 '구조화 출력'을 요구하는 agent 호출이 공유한다.
코드펜스나 잡음이 섞여도 첫 '{' ~ 마지막 '}' 구간을 JSON 으로 취한다.
"""

from __future__ import annotations

import json
from typing import Any


def extract_json(content: str) -> Any:
    """문자열에서 첫 '{' ~ 마지막 '}' 구간을 JSON 으로 파싱한다.

    JSON 객체를 찾지 못하거나 파싱에 실패하면 ValueError 를 던진다.
    """
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"응답에서 JSON 객체를 찾지 못함: {content[:200]!r}")
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e
