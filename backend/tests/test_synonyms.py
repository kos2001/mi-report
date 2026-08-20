"""도메인 동의어 질의 확장 검증."""

from __future__ import annotations

from app import synonyms


def test_expands_known_synonym():
    out = synonyms.expand_query("시험양산 일정")
    assert "위험생산" in out  # 동의어가 추가됨
    assert "시험양산" in out  # 원문 보존


def test_no_match_returns_original():
    assert synonyms.expand_query("환율 변동") == "환율 변동"


def test_does_not_duplicate_existing():
    out = synonyms.expand_query("HBM 고대역폭메모리")
    # 이미 있는 표현은 다시 붙지 않음(공백 분리 토큰 수로 확인)
    assert out.lower().count("hbm") == 1


def test_expands_business_metric_abbreviations():
    out = synonyms.expand_query("스마트폰 두뇌칩 평균 판매가격")
    assert "AP" in out
    assert "ASP" in out
