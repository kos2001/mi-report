"""주제 카테고리(TopicCategory) 정규화 테스트.

LLM 이 허용된 4개 값(SET/반도체 설계/반도체 제조/수요/시황) 중 하나를 의도했지만
오타·환각으로 살짝 다른 문자열을 낼 때(예: '수요/시징'), Literal 검증에서 바로
실패해 리포트 생성 전체가 502 로 죽는 문제를 막는다 — 가장 가까운 허용값으로
보정하고, 전혀 다른 값이면 기본값으로 폴백한다.
"""

from __future__ import annotations

from app.schemas import DocClassificationOut, TopicSummaryOut


def test_topic_summary_category_typo_normalizes_to_closest():
    out = TopicSummaryOut.model_validate({"category": "수요/시징", "summary": "s", "insight": "i"})
    assert out.category == "수요/시황"


def test_topic_summary_category_exact_match_unchanged():
    out = TopicSummaryOut.model_validate({"category": "반도체 제조", "summary": "s", "insight": "i"})
    assert out.category == "반도체 제조"


def test_topic_summary_category_unrecognized_falls_back_to_default():
    out = TopicSummaryOut.model_validate({"category": "완전히 다른 값", "summary": "s", "insight": "i"})
    assert out.category == "수요/시황"


def test_doc_classification_category_typo_normalizes_to_closest():
    out = DocClassificationOut.model_validate({"category": "반도체 설게", "topic": "t"})
    assert out.category == "반도체 설계"
