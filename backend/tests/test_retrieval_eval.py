"""RAG 검색 품질 평가 하니스(검증셋 기반).

eval_data 의 라벨 코퍼스를 격리 DB 에 적재하고, 각 질문에 대해
search_documents(순수 BM25) 의 recall@k / MRR 을 측정한다.

지표를 보려면:  pytest tests/test_retrieval_eval.py -s
회귀 가드:        recall@5, MRR 이 기준선 아래로 떨어지면 실패.
"""

from __future__ import annotations

import pytest

from app import collection
from tests.eval_data import EVAL_CORPUS, EVAL_QUERIES, HARD_QUERIES

K_VALUES = (1, 3, 5)
# 현재 구현(제목+주제 색인 + OR 매칭)에서 달성되는 수준을 회귀 가드로 고정.
RECALL5_FLOOR = 0.90
MRR_FLOOR = 0.80


def _load_corpus() -> dict[str, str]:
    """코퍼스를 적재하고 {eval_id: db_doc_id} 매핑을 반환."""
    id_map: dict[str, str] = {}
    for eval_id, title, body, topic in EVAL_CORPUS:
        doc = collection.ingest_text(title, body, topic=topic, source_name="eval")
        id_map[eval_id] = doc["id"]
    return id_map


def _evaluate(id_map: dict[str, str]) -> dict[str, float]:
    """전체 검증셋에 대해 recall@k 와 MRR 을 계산하고 표를 출력."""
    max_k = max(K_VALUES)
    hits_at = {k: 0 for k in K_VALUES}
    rr_sum = 0.0
    rows: list[str] = []
    for question, expected_ids, _note in EVAL_QUERIES:
        want = {id_map[e] for e in expected_ids}
        results = collection.search_documents(question, limit=max_k)
        ranked = [d["id"] for d in results]
        rank = next((i + 1 for i, did in enumerate(ranked) if did in want), None)
        rr_sum += (1.0 / rank) if rank else 0.0
        for k in K_VALUES:
            if rank and rank <= k:
                hits_at[k] += 1
        mark = f"#{rank}" if rank else "miss"
        rows.append(f"  {mark:>5}  {question}")

    n = len(EVAL_QUERIES)
    metrics = {f"recall@{k}": hits_at[k] / n for k in K_VALUES}
    metrics["mrr"] = rr_sum / n
    print("\n── RAG 검색 평가 (검증셋 %d건) ─────────────────────────" % n)
    for line in rows:
        print(line)
    print("  " + "  ".join(f"recall@{k}={metrics[f'recall@{k}']:.2f}" for k in K_VALUES)
          + f"  MRR={metrics['mrr']:.2f}")
    return metrics


def test_retrieval_quality(isolated):
    id_map = _load_corpus()
    metrics = _evaluate(id_map)
    assert metrics["recall@5"] >= RECALL5_FLOOR, metrics
    assert metrics["mrr"] >= MRR_FLOOR, metrics


def test_semantic_gap_diagnostic(isolated, capsys):
    """동의어/의미 기반 난이도 셋 회수율(진단용, 비-게이팅).

    BM25 어휘 매칭의 한계를 수치로 남긴다 → 다음 레버(의미 임베딩)의 목표치.
    """
    id_map = _load_corpus()
    hit = 0
    rows = []
    for question, expected_ids, note in HARD_QUERIES:
        want = {id_map[e] for e in expected_ids}
        ranked = [d["id"] for d in collection.search_documents(question, limit=5)]
        ok = bool(want & set(ranked))
        hit += int(ok)
        rows.append(f"  {'hit ' if ok else 'miss'}  {question}  ({note})")
    n = len(HARD_QUERIES)
    with capsys.disabled():
        print("\n── 의미 기반 난이도 셋 (진단, 비-게이팅) ─────────────")
        for line in rows:
            print(line)
        print(f"  recall@5={hit / n:.2f}  ← 의미 임베딩 도입 시 개선 목표")
    # 게이팅하지 않음: 어휘 매칭의 알려진 한계 기록만.
    assert 0 <= hit <= n


@pytest.mark.parametrize("question,expected_ids,note", EVAL_QUERIES)
def test_each_query_retrieves_expected(isolated, question, expected_ids, note):
    """각 질문이 정답 문서를 상위 5 안에 회수하는지(개별 회귀 가드)."""
    id_map = _load_corpus()
    want = {id_map[e] for e in expected_ids}
    ranked = [d["id"] for d in collection.search_documents(question, limit=5)]
    assert want & set(ranked), f"{question!r} → miss (정답 미회수). {note}"
