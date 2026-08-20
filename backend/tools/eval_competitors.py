"""경쟁사 IR AI 분석 평가 하니스 — 다수 기업 실데이터로 품질 측정.

여러 반도체/IT 기업의 SEC EDGAR 실 IR 데이터를 한 코퍼스에 수집한 뒤, 각 기업을
analyze_competitor 로 분석해 품질을 측정한다:
  - retrieval: 그 회사 문서를 올바로 회수했는가(교차오염 방지)
  - grounded : 미근거(환각) 수치 0 인가(재무 서비스 핵심)
  - coverage : 재무 항목을 추출했는가(financials_count)

라이브(SEC + OpenRouter) 필요:
  cd backend && .venv/bin/python -m tools.eval_competitors
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/Users/kos2001/gitspace/mi-report/backend")
os.environ.setdefault("MI_EMBEDDINGS", "1")

import httpx  # noqa: E402

from app.profiles import load_profile  # noqa: E402

load_profile()

tmp = Path(tempfile.mkdtemp(prefix="eval_comp_"))
from app import config  # noqa: E402

config.DATA_DIR = tmp
config.COLLECTION_DB = tmp / "collection.db"
config.UPLOADS_DIR = tmp / "uploads"

from app import collection, competitors, sec_edgar  # noqa: E402
from app.gateway import get_client  # noqa: E402

# (name, ticker, CIK) — 미국 us-gaap + 외국 IFRS(TSMC/ASML) 혼합
COMPANIES = [
    ("Qualcomm", "QCOM", "0000804328"),
    ("NVIDIA", "NVDA", "0001045810"),
    ("Broadcom", "AVGO", "0001730168"),
    ("AMD", "AMD", "0000002488"),
    ("Intel", "INTC", "0000050863"),
    ("Texas Instruments", "TXN", "0000097476"),
    ("Micron", "MU", "0000723125"),
    ("TSMC", "TSM", "0001046179"),     # IFRS
    ("ASML", "ASML", "0000937966"),    # IFRS
]


async def _ingest_all(http):
    ok, doc_ids = [], {}
    for name, ticker, cik in COMPANIES:
        try:
            doc = await sec_edgar.fetch_company_ir(http, cik.zfill(10), name)
            row = collection.ingest_text(doc["title"], doc["text"], topic="경쟁사IR")
            doc_ids[name] = row["id"] if isinstance(row, dict) else row
            ok.append((name, ticker))
        except Exception as e:
            print(f"  [수집실패] {name}: {type(e).__name__} {str(e)[:60]}")
        await asyncio.sleep(0.3)  # SEC 속도 예의
    return ok, doc_ids


async def main():
    collection.init_db()
    async with httpx.AsyncClient(timeout=30,
                                 headers={"User-Agent": "mi-report eval mi-report@example.com"}) as http:
        ok, doc_ids = await _ingest_all(http)
    n_emb = collection.rebuild_embeddings()
    print(f"[corpus] 기업 {len(ok)} 수집, 임베딩 {n_emb}\n")

    client = get_client()
    print(f"{'company':<20}{'retrieved':>10}{'grounded':>10}{'fin#':>6}{'dropped':>8}")
    print("-" * 56)
    ret_hit = grnd_hit = cov_hit = 0
    fails = []
    for name, ticker in ok:
        docs = collection.documents_for_competitor(name, ticker, limit=5)
        # 회수 정확도: 최상위 문서가 실제 그 회사의 문서(doc-id 동일성)인가
        retrieved = bool(docs) and docs[0].get("id") == doc_ids.get(name)
        res = await competitors.analyze_competitor(client, name, ticker, docs)
        grounded = res.get("numbersGrounded", False)
        fin = len(res.get("financials", []))
        dropped = res.get("droppedCount", 0)
        ret_hit += int(retrieved)
        grnd_hit += int(grounded)
        cov_hit += int(fin >= 1)
        if not (retrieved and grounded and fin >= 1):
            fails.append((name, retrieved, grounded, fin, dropped, res.get("ungroundedNumbers", [])))
        print(f"{name:<20}{('O' if retrieved else 'X'):>10}{('O' if grounded else 'X'):>10}{fin:>6}{dropped:>8}")

    n = len(ok)
    print("\n── 집계 ─────────────────────────────")
    print(f"검색 정확도(retrieved): {ret_hit}/{n} = {ret_hit/n:.2f}")
    print(f"환각 없음(grounded)   : {grnd_hit}/{n} = {grnd_hit/n:.2f}")
    print(f"재무 추출(coverage)   : {cov_hit}/{n} = {cov_hit/n:.2f}")
    if fails:
        print("\n── 약점(실패) ─────────────────────")
        for name, r, g, f, dr, un in fails:
            print(f"  {name}: retrieved={r} grounded={g} fin#={f} dropped={dr} ungrounded={un[:5]}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
