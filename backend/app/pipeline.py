"""MI 파이프라인 — 수집 → 다이제스트 생성 → 저장 오케스트레이션.

스케줄(cron/launchd) 자동 실행과 HTTP 엔드포인트가 공유한다. 수집(소스 URL fetch
→ 본문 추출 → 문서 저장)과 다이제스트 생성을 한 번에 돌리고, 산출물을 JSON 으로
영속화해 나중에 조회할 수 있게 한다. 게이트웨이가 떠 있어야 다이제스트가 생성된다.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import collection, confluence, config, digest, fetcher, jira
from .gateway import get_client


async def collect_source(
    source: dict[str, Any], client: httpx.AsyncClient
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """한 소스를 수집한다. confluence/jira 는 API 동기화, 그 외는 URL fetch."""
    if source["type"] == "confluence":
        return await collect_confluence_source(source, client)
    if source["type"] == "jira":
        return await collect_jira_source(source, client)

    documents: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for url in collection.source_urls(source):
        try:
            fetched = await fetcher.fetch_url(client, url)
        except httpx.HTTPError as e:
            errors.append({"url": url, "error": f"가져오기 실패: {e}"})
            continue
        if not fetched["text"]:
            errors.append({"url": url, "error": "본문 추출 실패(빈 텍스트)"})
            continue
        documents.append(
            collection.add_crawled_document(
                source["id"], source["name"], fetched["title"], fetched["text"], url=url
            )
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
    collection.delete_documents_by_source(source["id"])
    documents = [
        collection.add_crawled_document(
            source["id"], source["name"], p["title"], p["text"], url=p["url"]
        )
        for p in pages
    ]
    return documents, []


async def collect_jira_source(
    source: dict[str, Any], client: httpx.AsyncClient, *, limit: int = 50
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Jira 프로젝트 이슈를 가져와 문서로 동기화한다(기존 문서는 교체)."""
    base, project, email, token = jira.config_from_source(source)
    if not base or not project or not email or not token:
        return [], [{"url": base or "(미설정)",
                     "error": "Jira base_url/project_key/이메일/토큰 설정 필요"}]
    try:
        issues = await jira.fetch_issues(client, base, project, email, token, limit=limit)
    except httpx.HTTPError as e:
        return [], [{"url": base, "error": f"Jira API 실패: {e}"}]
    # 재동기화: 기존 문서 제거 후 현재 이슈로 갱신
    collection.delete_documents_by_source(source["id"])
    documents = [
        collection.add_crawled_document(
            source["id"], source["name"], it["title"], it["text"], url=it["url"]
        )
        for it in issues
    ]
    return documents, []


async def run_collection() -> dict[str, Any]:
    """URL 이 있는 활성 커넥터 소스를 모두 수집한다."""
    ingested = 0
    per_source: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as http:
        for source in collection.list_sources():
            if source["type"] not in collection.CONNECTOR_TYPES or not source["enabled"]:
                continue
            # confluence/jira 는 API 동기화, 그 외는 URL 이 있어야 수집 대상
            if source["type"] not in ("confluence", "jira") and not collection.source_urls(source):
                continue
            docs, errors = await collect_source(source, http)
            if not docs and errors:
                collection.mark_source_status(source["id"], "오류")
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


async def run_digest(*, issue_no: int, period: str, limit: int = 20) -> dict[str, Any]:
    """수집 문서로 다이제스트를 생성하고 저장한다."""
    docs = collection.documents_for_digest(limit=limit)
    if not docs:
        raise ValueError("다이제스트로 만들 본문 있는 문서가 없습니다.")
    digest_obj = await digest.generate_digest(
        get_client(), docs, issue_no=issue_no, period=period
    )
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


async def run_pipeline(*, issue_no: int = 1, period: str = "자동 수집분", limit: int = 20) -> dict[str, Any]:
    """전체 파이프라인: 수집 → 다이제스트 생성·저장."""
    collected = await run_collection()
    result: dict[str, Any] = {"collected": collected}
    try:
        result["digest"] = await run_digest(issue_no=issue_no, period=period, limit=limit)
    except ValueError as e:
        result["digest"] = None
        result["digestError"] = str(e)
    return result
