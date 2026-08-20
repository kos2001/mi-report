"""MI 파이프라인 — 수집 → 다이제스트 생성 → 저장 오케스트레이션.

스케줄(cron/launchd) 자동 실행과 HTTP 엔드포인트가 공유한다. 수집(소스 URL fetch
→ 본문 추출 → 문서 저장)과 다이제스트 생성을 한 번에 돌리고, 산출물을 JSON 으로
영속화해 나중에 조회할 수 있게 한다. 게이트웨이가 떠 있어야 다이제스트가 생성된다.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from . import collection, confluence, config, dart, digest, fetcher, hankyung, sec_edgar
from .gateway import get_client


async def collect_source(
    source: dict[str, Any], client: httpx.AsyncClient
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """한 소스를 수집한다. confluence/sec/dart 는 API 동기화, 그 외는 URL fetch."""
    if source["type"] == "confluence":
        return await collect_confluence_source(source, client)
    if source["type"] == "sec":
        return await collect_sec_source(source, client)
    if source["type"] == "dart":
        return await collect_dart_source(source, client)
    if source["type"] == "hankyung":
        return await collect_hankyung_source(source, client)

    errors: list[dict[str, str]] = []
    urls = collection.source_urls(source)
    # URL fetch 는 네트워크 대기가 지배적 → 동시 수행(문서 저장은 순서대로).
    fetched_all = await asyncio.gather(
        *(fetcher.fetch_url(client, url) for url in urls), return_exceptions=True
    )
    items: list[dict[str, Any]] = []
    for url, fetched in zip(urls, fetched_all):
        if isinstance(fetched, BaseException):
            if isinstance(fetched, httpx.HTTPError):
                errors.append({"url": url, "error": f"가져오기 실패: {fetched}"})
                continue
            raise fetched
        if not fetched["text"]:
            errors.append({"url": url, "error": "본문 추출 실패(빈 텍스트)"})
            continue
        items.append({"title": fetched["title"], "text": fetched["text"], "url": url})
    if not items:
        return [], errors
    # 문서 저장(DB+파일+임베딩)은 블로킹 → 워커 스레드에서 일괄 수행(임베딩 배치 1회)
    documents = await asyncio.to_thread(
        collection.add_crawled_documents, source["id"], source["name"], items
    )
    return documents, errors


async def collect_confluence_source(
    source: dict[str, Any], client: httpx.AsyncClient, *, limit: int = 25
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Confluence 페이지를 가져와 문서로 동기화한다(기존 문서는 교체)."""
    base, email, token = confluence.config_from_source(source)
    if not base or not email or not token:
        return [], [{"url": base or "(미설정)", "error": "Confluence base_url/이메일/토큰 설정 필요"}]
    try:
        pages = await confluence.fetch_pages(client, base, email, token, limit=limit)
    except httpx.HTTPError as e:
        return [], [{"url": base, "error": f"Confluence API 실패: {e}"}]
    # 재동기화: 기존 문서 제거 후 현재 페이지로 갱신
    # (DB+파일+임베딩 저장은 블로킹 → 워커 스레드에서 일괄 수행)
    def _sync() -> list[dict[str, Any]]:
        collection.delete_documents_by_source(source["id"])
        return collection.add_crawled_documents(
            source["id"], source["name"],
            [{"title": p["title"], "text": p["text"], "url": p["url"]} for p in pages],
        )

    return await asyncio.to_thread(_sync), []


async def collect_sec_source(
    source: dict[str, Any], client: httpx.AsyncClient, *, topic: str = "경쟁사IR"
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """SEC EDGAR 에서 경쟁사 실 IR/재무를 가져와 문서로 동기화한다(기존 문서 교체)."""
    cik, name = sec_edgar.config_from_source(source)
    if not cik:
        return [], [{"url": "(미설정)", "error": "SEC CIK 설정 필요(config.cik)"}]
    try:
        doc = await sec_edgar.fetch_company_ir(client, cik, name)
    except httpx.HTTPError as e:
        return [], [{"url": "data.sec.gov", "error": f"SEC API 실패: {e}"}]

    def _sync() -> dict[str, Any]:
        collection.delete_documents_by_source(source["id"])
        return collection.add_crawled_document(
            source["id"], source["name"], doc["title"], doc["text"], url=doc["url"], topic=topic
        )

    return [await asyncio.to_thread(_sync)], []


async def collect_dart_source(
    source: dict[str, Any], client: httpx.AsyncClient, *, topic: str = "경쟁사IR"
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """DART 에서 한국 경쟁사 실 IR/재무를 가져와 문서로 동기화한다(기존 문서 교체)."""
    corp_code, name = dart.config_from_source(source)
    if not corp_code:
        return [], [{"url": "(미설정)", "error": "DART corp_code 설정 필요(config.corp_code)"}]
    try:
        doc = await dart.fetch_company_ir(client, corp_code, name)
    except ValueError as e:  # DART_API_KEY 미설정 등
        return [], [{"url": "opendart.fss.or.kr", "error": str(e)}]
    except httpx.HTTPError as e:
        return [], [{"url": "opendart.fss.or.kr", "error": f"DART API 실패: {e}"}]

    def _sync() -> dict[str, Any]:
        collection.delete_documents_by_source(source["id"])
        return collection.add_crawled_document(
            source["id"], source["name"], doc["title"], doc["text"], url=doc["url"], topic=topic
        )

    return [await asyncio.to_thread(_sync)], []


async def collect_hankyung_source(
    source: dict[str, Any], client: httpx.AsyncClient, *, topic: str = "컨센서스"
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """한경 컨센서스 리포트 PDF 본문을 추출해 문서로 동기화한다(기존 문서 교체)."""
    cfg = source.get("config") or {}
    base = (cfg.get("base_url") or hankyung.BASE_DEFAULT).strip()
    try:
        limit = int(cfg.get("limit") or hankyung.LIMIT_DEFAULT)
    except (TypeError, ValueError):
        limit = hankyung.LIMIT_DEFAULT
    try:
        reports = await hankyung.fetch_reports(client, base, limit=limit)
    except httpx.HTTPError as e:
        return [], [{"url": base, "error": f"한경 컨센서스 수집 실패: {e}"}]
    if not reports:
        return [], [{"url": base, "error": "리포트 목록을 찾지 못했습니다."}]

    def _sync() -> list[dict[str, Any]]:
        collection.delete_documents_by_source(source["id"])
        return collection.add_crawled_documents(
            source["id"], source["name"],
            [{"title": r["title"], "text": r["text"], "url": r["url"], "topic": topic}
             for r in reports],
        )

    return await asyncio.to_thread(_sync), []


async def run_collection() -> dict[str, Any]:
    """URL 이 있는 활성 커넥터 소스를 모두 수집한다."""
    ingested = 0
    per_source: list[dict[str, Any]] = []
    targets = [
        source
        for source in collection.list_sources()
        if source["type"] in collection.CONNECTOR_TYPES and source["enabled"]
        # confluence/sec/dart/hankyung 는 API 동기화, 그 외는 URL 이 있어야 수집 대상
        and (source["type"] in ("confluence", "sec", "dart", "hankyung")
             or collection.source_urls(source))
    ]
    async with httpx.AsyncClient() as http:
        # 소스별 수집은 서로 독립 → 동시 수행(전체 시간 = 가장 느린 소스).
        # return_exceptions: 한 소스의 예기치 못한 실패가 다른 소스 수집을 막지 않게.
        results = await asyncio.gather(
            *(collect_source(s, http) for s in targets), return_exceptions=True
        )
    for source, res in zip(targets, results):
        if isinstance(res, BaseException):
            docs: list[dict[str, Any]] = []
            errors = [{"url": source["name"], "error": f"수집 실패: {res}"}]
        else:
            docs, errors = res
        if not docs and errors:
            await asyncio.to_thread(collection.mark_source_status, source["id"], "오류")
        ingested += len(docs)
        per_source.append(
            {"source": source["name"], "ingested": len(docs), "errors": errors}
        )
    return {"ingested": ingested, "sources": per_source}


def _save_digest(digest_obj: dict[str, Any], generated_at: str) -> str:
    """다이제스트를 timestamped JSON + latest.json 으로 저장. 저장 경로 반환."""
    config.DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.replace(":", "").replace("-", "").replace(" ", "_")
    record = {"generatedAt": generated_at, **digest_obj}
    path = config.DIGESTS_DIR / f"digest_{stamp}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (config.DIGESTS_DIR / "latest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(path)


async def run_digest(*, period: str, limit: int = 20) -> dict[str, Any]:
    """수집 문서로 다이제스트를 생성하고 저장한다."""
    docs = await asyncio.to_thread(collection.documents_for_digest, limit=limit)
    if not docs:
        raise ValueError("다이제스트로 만들 본문 있는 문서가 없습니다.")
    digest_obj = await digest.generate_digest(get_client(), docs, period=period)
    generated_at = collection.now()
    saved_path = _save_digest(digest_obj, generated_at)
    return {**digest_obj, "generatedAt": generated_at, "savedPath": saved_path}


def load_latest_digest() -> dict[str, Any] | None:
    """가장 최근 저장된 다이제스트(latest.json)를 읽는다. 없으면 None."""
    path = config.DIGESTS_DIR / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


async def run_pipeline(*, period: str = "자동 수집분", limit: int = 20) -> dict[str, Any]:
    """전체 파이프라인: 수집 → 다이제스트 생성·저장."""
    collected = await run_collection()
    result: dict[str, Any] = {"collected": collected}
    try:
        result["digest"] = await run_digest(period=period, limit=limit)
    except ValueError as e:
        result["digest"] = None
        result["digestError"] = str(e)
    return result
