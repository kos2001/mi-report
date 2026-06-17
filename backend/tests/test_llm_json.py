"""LLM JSON 추출 견고성 테스트."""

from __future__ import annotations

import pytest

from app.llm_json import extract_json


def test_plain_object():
    assert extract_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_strips_code_fence_and_prose():
    assert extract_json('설명문\n```json\n{"a": 1}\n```') == {"a": 1}


def test_tolerates_duplicated_object():
    # 일부 모델(minimax 등)이 같은 객체를 중복 출력 → 첫 객체만 취한다.
    assert extract_json('{"a": 1}{"a": 1}') == {"a": 1}


def test_tolerates_trailing_noise():
    assert extract_json('{"a": 1} 추가 설명문은 무시') == {"a": 1}


def test_nested_object_intact():
    assert extract_json('{"x": {"y": [1, 2]}}garbage') == {"x": {"y": [1, 2]}}


def test_no_object_raises():
    with pytest.raises(ValueError):
        extract_json("JSON 이 전혀 없습니다.")


def test_malformed_raises():
    with pytest.raises(ValueError):
        extract_json('{"a": ')
