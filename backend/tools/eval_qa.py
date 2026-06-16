"""문서 Q&A(RAG) 엔드투엔드 평가 하니스.

고정 코퍼스(tests/eval_data.EVAL_CORPUS)에 실제 RAG 파이프라인(임베딩→리랭크→LLM 답변)을
돌려 품질을 측정한다:
  - 인용 정확도(citation): 답변이 올바른 근거 문서를 [문서 N]로 인용했는가
  - 정답 키워드(keyword): 답변에 핵심 사실 키워드가 포함됐는가
  - 환각 거부(refusal): 코퍼스에 없는 질문에 "확인되지 않음"으로 답했는가

여러 설정(후보 풀 배수·top_n·rerank on/off)을 A/B 해 최적 구성을 찾는다.
실행(라이브 LLM·OpenRouter 필요):
  cd backend && .venv/bin/python -m tools.eval_qa
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/Users/kos2001/gitspace/mi-report/backend")

os.environ.setdefault("MI_EMBEDDINGS", "1")

from app.profiles import load_profile  # noqa: E402

load_profile()  # OPENROUTER_API_KEY / MI_EMBED_* / MI_RERANK_* 로드

tmp = Path(tempfile.mkdtemp(prefix="eval_qa_"))
from app import config  # noqa: E402

config.DATA_DIR = tmp
config.COLLECTION_DB = tmp / "collection.db"
config.UPLOADS_DIR = tmp / "uploads"
config.DIGESTS_DIR = tmp / "digests"

from app import collection, qa_golden, rag  # noqa: E402
from app.gateway import get_client  # noqa: E402
from tests.eval_data import EVAL_CORPUS  # noqa: E402

_REFUSAL = ("확인되지 않", "확인할 수 없", "찾을 수 없", "정보가 없", "나와 있지 않")

CONFIGS = {
    # name: (limit=top_n, cand_mult, rerank)
    "base(top5·cand3x·rerank)": (5, 3, True),
    "top5·cand4x·rerank": (5, 4, True),
    "top6·cand4x·rerank": (6, 4, True),
    "top5·cand3x·NO-rerank": (5, 3, False),
}


def _load_corpus() -> dict[str, str]:
    collection.init_db()  # qa_golden 골든셋도 시드됨
    title_to_id = {}
    for eid, title, body, topic in EVAL_CORPUS:
        d = collection.ingest_text(title, body, topic=topic, source_name="eval")
        title_to_id[d["title"]] = eid
    n = collection.rebuild_embeddings()
    print(f"[corpus] {len(EVAL_CORPUS)} docs, embeddings={n}, backend={os.getenv('MI_EMBED_BACKEND')}")
    return title_to_id


def _load_golden():
    """DB(qa_golden)에서 골든 Q&A 를 로드한다(평가셋 자산화).

    answerable: (질문, 근거 라벨, 반드시 포함, 금지값)
    """
    answerable = [
        (i["question"], i["expectedIds"], i["keywords"], i.get("forbidden", []))
        for i in qa_golden.list_qa(kind="answerable")
    ]
    negatives = [i["question"] for i in qa_golden.list_qa(kind="negative")]
    return answerable, negatives


async def _run_query(client, question, *, limit, cand_mult):
    cand_k = min(max(limit * cand_mult, 12), 24)
    docs = collection.documents_for_rag(question, limit=cand_k)
    if not docs:
        return {"answer": "", "sources": [], "citedCount": 0}
    ranked = await rag.rerank(client, question, docs, top_n=limit)
    return await rag.answer_question(client, question, ranked)


async def _eval_config(client, title_to_id, qa_queries, qa_negatives, name, limit, mult, rerank):
    prev = os.environ.get("MI_RERANK_MODEL", "")
    if not rerank:
        os.environ["MI_RERANK_MODEL"] = ""  # 리랭크 비활성(LLM 폴백)
    try:
        cite_hits = kw_hits = 0
        num_total = num_hits = 0  # 수치 정밀도(forbidden 보유 질문)
        for q, exp_ids, kws, forb in qa_queries:
            res = await _run_query(client, q, limit=limit, cand_mult=mult)
            ans = res.get("answer", "")
            cited_ids = (
                {title_to_id.get(s["title"]) for s in res.get("sources", [])}
                if res.get("citedCount", 0) > 0 else set()
            )
            if set(exp_ids) & cited_ids:
                cite_hits += 1
            # 정답: 필수 키워드 모두 포함 + 금지값(반올림/왜곡)은 하나도 없어야
            ok = bool(kws) and all(k in ans for k in kws) and not any(f in ans for f in forb)
            if ok:
                kw_hits += 1
            if forb:  # 수치 정밀도 전용 집계
                num_total += 1
                num_hits += int(ok)
        ref_hits = 0
        for q in qa_negatives:
            res = await _run_query(client, q, limit=limit, cand_mult=mult)
            if any(p in res.get("answer", "") for p in _REFUSAL):
                ref_hits += 1
    finally:
        os.environ["MI_RERANK_MODEL"] = prev

    nq, nn = len(qa_queries), len(qa_negatives)
    cite, kw, ref = cite_hits / nq, kw_hits / nq, ref_hits / nn
    num = (num_hits / num_total) if num_total else 1.0
    overall = (cite + kw + ref) / 3
    print(f"{name:<26} citation={cite:.2f}  keyword={kw:.2f}  numeric={num:.2f}  refusal={ref:.2f}  overall={overall:.2f}")
    return name, overall


async def main():
    title_to_id = _load_corpus()
    qa_queries, qa_negatives = _load_golden()
    print(f"[golden] answerable={len(qa_queries)} negative={len(qa_negatives)} (DB: qa_golden)")
    client = get_client()
    print(f"\n{'config':<26}  citation keyword numeric refusal overall")
    print("-" * 70)
    results = []
    for name, (limit, mult, rerank) in CONFIGS.items():
        results.append(
            await _eval_config(client, title_to_id, qa_queries, qa_negatives, name, limit, mult, rerank)
        )
    best = max(results, key=lambda x: x[1])
    print(f"\n최고 구성: {best[0]} (overall={best[1]:.2f})")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
