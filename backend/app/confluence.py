"""Confluence Cloud 커넥터 — REST API v2 로 페이지를 가져와 본문 텍스트를 추출한다.

`confluence` 타입 소스의 '수집'이 실제 동작하도록, Atlassian Cloud 의 페이지를
API 토큰(Basic 인증)으로 받아 storage(XHTML) 본문을 텍스트로 변환한다.
자격증명은 환경변수에서 읽는다(프로파일 .env 가 자동 로드):
  - CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN (소스 config 로 변수명 재정의 가능)

순수 추출(extract_text_from_html, fetcher 재사용)과 네트워크(주입된 httpx 클라이언트)를
분리해 네트워크 없이 단위 테스트한다.
"""

from __future__ import annotations

import base64
import os
from typing import Any, Protocol

from . import fetcher


class HttpClient(Protocol):
    async def get(self, url: str, **kwargs: Any) -> Any: ...


def _auth_header(email: str, token: str) -> str:
    raw = f"{email}:{token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def config_from_source(source: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """소스 config + 환경변수에서 (base_url, email, token) 을 구성한다.

    base_url 예: https://<site>.atlassian.net/wiki
    자격증명은 활성 프로파일 .env 에 있을 수 있으므로, 누락 시 프로파일을 로드해
    os.environ 에 채운다(게이트웨이 호출 전에도 동작하도록).
    """
    cfg = source.get("config") or {}
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    email_env = cfg.get("email_env", "CONFLUENCE_EMAIL")
    token_env = cfg.get("token_env", "CONFLUENCE_API_TOKEN")
    if email_env not in os.environ or token_env not in os.environ:
        try:
            from .profiles import load_profile

            load_profile()  # 활성 프로파일 .env 를 os.environ 에 적용(이미 있는 값은 보존)
        except Exception:
            pass
    return base, os.environ.get(email_env), os.environ.get(token_env)


def parse_pages(base_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """v2 pages 응답(JSON)에서 {id,title,text,url} 목록을 추출한다."""
    out: list[dict[str, Any]] = []
    for p in payload.get("results", []):
        storage = ((p.get("body") or {}).get("storage") or {}).get("value") or ""
        title = (p.get("title") or "untitled").strip() or "untitled"
        _, text = fetcher.extract_text_from_html(storage)
        if not text:
            text = title  # 본문이 비면 제목이라도 보존
        webui = ((p.get("_links") or {}).get("webui")) or f"/pages/{p.get('id')}"
        url = base_url.rstrip("/") + webui if webui.startswith("/") else webui
        out.append({"id": str(p.get("id")), "title": title, "text": text, "url": url})
    return out


async def fetch_pages(
    client: HttpClient,
    base_url: str,
    email: str,
    token: str,
    *,
    limit: int = 25,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Confluence 페이지를 storage 본문 포함으로 가져와 파싱한다.

    HTTP 오류는 httpx 예외로 전파(호출자가 처리).
    """
    url = f"{base_url.rstrip('/')}/api/v2/pages?limit={limit}&body-format=storage"
    resp = await client.get(
        url,
        headers={"Authorization": _auth_header(email, token), "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_pages(base_url, resp.json())
