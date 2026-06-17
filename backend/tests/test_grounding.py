"""환각 방어(수치 근거 검증) 테스트."""

from __future__ import annotations

import asyncio

from app import grounding, rag


def test_extract_numbers_ignores_single_digit():
    nums = grounding.extract_numbers("매출 117억, 영업이익률 29.1%, [문서 3] 12단 2027년")
    assert "117" in nums and "29.1" in nums and "12" in nums and "2027" in nums
    assert "3" not in nums  # [문서 3] 인덱스는 제외


def test_ungrounded_numbers_flags_fabricated():
    src = ["매출 10,599,000,000 영업이익률 29.1%"]
    # 근거 있는 수치(콤마 정규화 후 일치) → 통과
    assert grounding.ungrounded_numbers("매출 10,599,000,000, 이익률 29.1%", src) == []
    # 근거 없는 수치 → 플래그
    bad = grounding.ungrounded_numbers("순이익 7,777,777,777 (35.2%)", src)
    assert "7777777777" in bad and "35.2" in bad


def test_rescaled_numbers_are_grounded():
    # 원문은 백만 단위(콤마), 답변은 십억 단위(소수) — 같은 수치로 인정해야 함.
    src = ["분기 매출 61,157 백만달러, 직전 53,536 백만달러"]
    assert grounding.ungrounded_numbers("매출 61.157B (전분기 53.536B)", src) == []
    # 반올림 표기도 접두 매칭으로 인정.
    assert grounding.ungrounded_numbers("매출 약 61.1B", src) == []
    # 진짜 환각(접두 무관)은 계속 플래그.
    assert "72.4" in grounding.ungrounded_numbers("매출 72.4B", src)


def test_check_and_caveat():
    g = grounding.check("값 12345", ["다른 문서"])
    assert g["numbersGrounded"] is False and "12345" in g["ungroundedNumbers"]
    assert "검토가 필요" in grounding.caveat_line(g["ungroundedNumbers"])
    assert grounding.caveat_line([]) == ""


class _Fake:
    def __init__(self, content):
        self._c = content

    async def chat(self, messages, **kw):
        return {"choices": [{"message": {"content": self._c}}]}


def test_answer_flags_ungrounded_number():
    docs = [{"title": "T", "source": "SEC", "publishedAt": "", "content": "매출 10,599,000,000"}]
    # 답변이 문서에 없는 수치(999,999)를 지어냄 → 미근거 플래그 + 경고 부기
    res = asyncio.run(rag.answer_question(_Fake("매출은 999,999 입니다 [문서 1]."), "q", docs))
    assert res["numbersGrounded"] is False
    assert "999999" in res["ungroundedNumbers"]
    assert "검토가 필요" in res["answer"]


def test_answer_grounded_number_ok():
    docs = [{"title": "T", "source": "SEC", "publishedAt": "", "content": "매출 10,599,000,000"}]
    res = asyncio.run(rag.answer_question(_Fake("매출은 10,599,000,000 입니다 [문서 1]."), "q", docs))
    assert res["numbersGrounded"] is True and res["ungroundedNumbers"] == []
