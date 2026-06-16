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

from app import collection, rag  # noqa: E402
from app.gateway import get_client  # noqa: E402
from tests.eval_data import EVAL_CORPUS, QA_NEGATIVES, QA_QUERIES  # noqa: E402

_REFUSAL = ("확인되지 않", "확인할 수 없", "찾을 수 없", "정보가 없", "나와 있지 않")

CONFIGS = {
    # name: (limit=top_n, cand_mult, rerank)
    "base(top5·cand3x·rerank)": (5, 3, True),
    "top5·cand4x·rerank": (5, 4, True),
    "top6·cand4x·rerank": (6, 4, True),
    "top5·cand3x·NO-rerank": (5, 3, False),
}


def _load_corpus() -> dict[str, str]:
    collection.init_db()
    title_to_id = {}
    for eid, title, body, topic in EVAL_CORPUS:
        d = collection.ingest_text(title, body, topic=topic, source_name="eval")
        title_to_id[d["title"]] = eid
    n = collection.rebuild_embeddings()
    print(f"[corpus] {len(EVAL_CORPUS)} docs, embeddings={n}, backend={os.getenv('MI_EMBED_BACKEND')}")
    return title_to_id


async def _run_query(client, question, *, limit, cand_mult):
    cand_k = min(max(limit * cand_mult, 12), 24)
    docs = collection.documents_for_rag(question, limit=cand_k)
    if not docs:
        return {"answer": "", "sources": [], "citedCount": 0}
    ranked = await rag.rerank(client, question, docs, top_n=limit)
    return await rag.answer_question(client, question, ranked)


async def _eval_config(client, title_to_id, name, limit, mult, rerank):
    prev = os.environ.get("MI_RERANK_MODEL", "")
    if not rerank:
        os.environ["MI_RERANK_MODEL"] = ""  # 리랭크 비활성(LLM 폴백)
    try:
        cite_hits = kw_hits = 0
        for q, exp_ids, kws in QA_QUERIES:
            res = await _run_query(client, q, limit=limit, cand_mult=mult)
            ans = res.get("answer", "")
            cited_ids = (
                {title_to_id.get(s["title"]) for s in res.get("sources", [])}
                if res.get("citedCount", 0) > 0 else set()
            )
            if set(exp_ids) & cited_ids:
                cite_hits += 1
            if kws and all(k in ans for k in kws):
                kw_hits += 1
        ref_hits = 0
        for q in QA_NEGATIVES:
            res = await _run_query(client, q, limit=limit, cand_mult=mult)
            if any(p in res.get("answer", "") for p in _REFUSAL):
                ref_hits += 1
    finally:
        os.environ["MI_RERANK_MODEL"] = prev

    nq, nn = len(QA_QUERIES), len(QA_NEGATIVES)
    cite, kw, ref = cite_hits / nq, kw_hits / nq, ref_hits / nn
    overall = (cite + kw + ref) / 3
    print(f"{name:<26} citation={cite:.2f}  keyword={kw:.2f}  refusal={ref:.2f}  overall={overall:.2f}")
    return name, overall


async def main():
    title_to_id = _load_corpus()
    client = get_client()
    print(f"\n{'config':<26}{'citation':>10}{'keyword':>9}{'refusal':>9}{'overall':>9}")
    print("-" * 63)
    results = []
    for name, (limit, mult, rerank) in CONFIGS.items():
        results.append(await _eval_config(client, title_to_id, name, limit, mult, rerank))
    best = max(results, key=lambda x: x[1])
    print(f"\n최고 구성: {best[0]} (overall={best[1]:.2f})")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
