"""LLM 응답에서 JSON 을 견고하게 추출한다.

다이제스트·주제 요약 등 '구조화 출력'을 요구하는 agent 호출이 공유한다.
코드펜스·잡음이 섞이거나, 일부 모델이 같은 객체를 중복 출력(예: '{...}{...}')해도
첫 '{' 에서 시작하는 첫 완전한 JSON 객체 하나만 파싱한다(뒤따르는 잡음은 무시).
"""

from __future__ import annotations

import json
from typing import Any


def extract_json(content: str) -> Any:
    """문자열에서 첫 '{' 에서 시작하는 첫 완전한 JSON 객체를 파싱한다.

    raw_decode 로 첫 객체만 취해, 모델이 객체 뒤에 덧붙인 중복/설명/잡음(Extra data)을
    허용한다. JSON 객체를 찾지 못하거나 파싱에 실패하면 ValueError 를 던진다.
    """
    start = content.find("{")
    if start == -1:
        raise ValueError(f"응답에서 JSON 객체를 찾지 못함: {content[:200]!r}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(content[start:])
        return obj
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e
