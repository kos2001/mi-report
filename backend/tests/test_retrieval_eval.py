"""RAG 검색 품질 평가 하니스(검증셋 기반).

eval_data 의 라벨 코퍼스를 격리 DB 에 적재하고, 각 질문에 대해
search_documents(순수 BM25) 의 recall@k / MRR 을 측정한다.

지표를 보려면:  pytest tests/test_retrieval_eval.py -s
회귀 가드:        recall@5, MRR 이 기준선 아래로 떨어지면 실패.
"""

from __future__ import annotations

import pytest

from app import collection, embeddings
from tests.eval_data import EVAL_CORPUS, EVAL_QUERIES, HARD_QUERIES, PARAPHRASE_QUERIES

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


def test_synonym_coverage(isolated, capsys):
    """동의어/약어 난이도 셋 회수율 — 도메인 동의어 사전이 커버하는지 가드.

    BM25 어휘 매칭으로는 0.75 였던 셋을 동의어 질의 확장으로 1.00 까지 끌어올린다.
    사전에 없는 신규 패러프레이즈는 의미 임베딩 검색이 다음 레버.
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
    recall = hit / n
    with capsys.disabled():
        print("\n── 동의어 난이도 셋 (동의어 사전 적용) ─────────────")
        for line in rows:
            print(line)
        print(f"  recall@5={recall:.2f}  (BM25 단독 0.75 → 동의어 확장)")
    assert recall == 1.0, f"동의어 사전 커버리지 회귀: {recall:.2f}"


def _recall_at_5(queries, id_map, search_fn) -> tuple[float, list[str]]:
    hit = 0
    rows = []
    for question, expected_ids, note in queries:
        want = {id_map[e] for e in expected_ids}
        ranked = [d["id"] for d in search_fn(question, limit=5)]
        ok = bool(want & set(ranked))
        hit += int(ok)
        rows.append(f"  {'hit ' if ok else 'miss'}  {question}  ({note})")
    return hit / len(queries), rows


def test_hybrid_beats_bm25_on_paraphrase(isolated, monkeypatch, capsys):
    """사전 밖 패러프레이즈 셋에서 의미 임베딩 하이브리드가 BM25(+동의어)를 능가/동률.

    fastembed/모델이 없으면 skip(코어 회귀 가드와 독립). 측정으로 가치를 입증한다.
    """
    pytest.importorskip("fastembed")
    pytest.importorskip("numpy")
    monkeypatch.setenv("MI_EMBEDDINGS", "1")
    embeddings.reset_for_test()
    if not embeddings.active():
        pytest.skip("임베딩 모델 로드 불가(오프라인) — 하이브리드 평가 생략")

    id_map = _load_corpus()  # 임베딩 활성 상태 → 적재 시 문서 임베딩도 저장됨
    assert collection.rebuild_embeddings() >= len(EVAL_CORPUS)

    bm25_recall, _ = _recall_at_5(PARAPHRASE_QUERIES, id_map, collection.search_documents)
    hybrid_recall, rows = _recall_at_5(PARAPHRASE_QUERIES, id_map, collection.hybrid_search)

    with capsys.disabled():
        print("\n── 사전 밖 패러프레이즈 셋 (하이브리드) ─────────────")
        for line in rows:
            print(line)
        print(f"  BM25+동의어 recall@5={bm25_recall:.2f}  →  하이브리드 recall@5={hybrid_recall:.2f}")

    assert hybrid_recall >= bm25_recall, (bm25_recall, hybrid_recall)
    assert hybrid_recall >= 0.66, hybrid_recall


@pytest.mark.parametrize("question,expected_ids,note", EVAL_QUERIES)
def test_each_query_retrieves_expected(isolated, question, expected_ids, note):
    """각 질문이 정답 문서를 상위 5 안에 회수하는지(개별 회귀 가드)."""
    id_map = _load_corpus()
    want = {id_map[e] for e in expected_ids}
    ranked = [d["id"] for d in collection.search_documents(question, limit=5)]
    assert want & set(ranked), f"{question!r} → miss (정답 미회수). {note}"
