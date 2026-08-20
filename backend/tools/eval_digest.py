"""뉴스 다이제스트 AI 초안 평가 하니스 — 실데이터로 환각·품질 측정.

여러 기업의 SEC EDGAR 실 IR 문서(실제 수치 다수)를 코퍼스로 다이제스트 초안을 생성하고
항목별 품질을 측정한다:
  - grounded     : 정성 서술의 수치가 근거 문서에 실재하는가(환각 없음)
  - sourceVerified: 출처가 실제 입력 문서에서 추적되는가(거짓 출처 귀속 방지)
  - coverage     : 입력 대비 항목이 생성됐는가

라이브(SEC + OpenRouter) 필요:
  cd backend && .venv/bin/python -m tools.eval_digest
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

tmp = Path(tempfile.mkdtemp(prefix="eval_digest_"))
from app import config  # noqa: E402

config.DATA_DIR = tmp
config.COLLECTION_DB = tmp / "collection.db"
config.UPLOADS_DIR = tmp / "uploads"
config.DIGESTS_DIR = tmp / "digests"

from app import collection, digest, sec_edgar  # noqa: E402
from app.gateway import get_client  # noqa: E402

COMPANIES = [
    ("Qualcomm", "0000804328"),
    ("NVIDIA", "0001045810"),
    ("Broadcom", "0001730168"),
    ("AMD", "0000002488"),
    ("Intel", "0000050863"),
    ("Micron", "0000723125"),
    ("TSMC", "0001046179"),
    ("ASML", "0000937966"),
]


async def main():
    collection.init_db()
    async with httpx.AsyncClient(timeout=30,
                                 headers={"User-Agent": "mi-report eval mi-report@example.com"}) as http:
        for name, cik in COMPANIES:
            try:
                doc = await sec_edgar.fetch_company_ir(http, cik.zfill(10), name)
                collection.ingest_text(doc["title"], doc["text"], topic="경쟁사IR")
            except Exception as e:
                print(f"  [수집실패] {name}: {type(e).__name__} {str(e)[:60]}")
            await asyncio.sleep(0.3)

    docs = collection.documents_for_digest(limit=len(COMPANIES))
    print(f"[corpus] 다이제스트 입력 문서 {len(docs)}\n")

    client = get_client()
    res = await digest.generate_digest(client, docs, period="eval")
    items = res["items"]

    print(f"{'item title':<46}{'grounded':>10}{'srcOK':>7}")
    print("-" * 63)
    grnd = srcok = 0
    for it in items:
        g = it["numbersGrounded"]
        s = it["sourceVerified"]
        grnd += int(g)
        srcok += int(s)
        print(f"{it['title'][:44]:<46}{('O' if g else 'X'):>10}{('O' if s else 'X'):>7}")

    n = len(items) or 1
    print("\n── 집계 ─────────────────────────────")
    print(f"항목 수(coverage)        : {len(items)} (입력 {len(docs)})")
    print(f"환각 없음(grounded)      : {grnd}/{len(items)} = {grnd/n:.2f}")
    print(f"출처 검증(sourceVerified): {srcok}/{len(items)} = {srcok/n:.2f}")
    print(f"미근거 수치(union)       : {res['ungroundedNumbers'][:10]}")
    print(f"출처 미검증 항목 수       : {res['unverifiedSourceCount']}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
