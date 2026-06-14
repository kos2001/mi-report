"""MI 파이프라인 단독 실행기 (cron/launchd 용).

수집(소스 URL fetch → 본문 추출 → 문서 저장) → 다이제스트 생성·저장을 한 번에
돌린다. uvicorn 없이 동작하지만, 다이제스트 생성은 OPENROUTER_API_KEY 가 설정돼
있어야 한다(활성 프로파일 .env).

사용:
  cd backend && .venv/bin/python -m tools.run_pipeline [--issue N] [--period STR] [--limit N]

cron 예 (매일 07:00):
  0 7 * * *  cd /path/to/mi-report/backend && .venv/bin/python -m tools.run_pipeline >> data/pipeline.log 2>&1
"""

from __future__ import annotations

import argparse
import asyncio

from app import collection, gateway, pipeline


async def _main(issue_no: int, period: str, limit: int) -> int:
    collection.init_db()
    try:
        result = await pipeline.run_pipeline(issue_no=issue_no, period=period, limit=limit)
    finally:
        await gateway.close_all()

    col = result["collected"]
    print(f"[수집] 신규 문서 {col['ingested']}건")
    for s in col["sources"]:
        note = f" (실패 {len(s['errors'])})" if s["errors"] else ""
        print(f"  - {s['source']}: {s['ingested']}건{note}")

    dg = result.get("digest")
    if dg is None:
        print(f"[다이제스트] 생성 안 됨: {result.get('digestError', '사유 미상')}")
        return 1
    print(f"[다이제스트] 제{dg['issueNo']}호 · 항목 {len(dg['items'])}개 → 저장: {dg['savedPath']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="MI 파이프라인 실행 (수집 → 다이제스트 생성·저장)")
    p.add_argument("--issue", type=int, default=1, help="다이제스트 호수")
    p.add_argument("--period", default="자동 수집분", help="대상 기간 표기")
    p.add_argument("--limit", type=int, default=20, help="다이제스트 입력 문서 최대 건수")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_main(args.issue, args.period, args.limit)))


if __name__ == "__main__":
    main()
