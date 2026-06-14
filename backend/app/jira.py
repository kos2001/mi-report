"""Jira Cloud 커넥터 — REST API v3 로 프로젝트 이슈를 가져와 본문 텍스트를 추출한다.

`jira` 타입 소스의 '수집'이 실제 동작하도록, Atlassian Cloud 의 이슈를 API 토큰
(Basic 인증)으로 받아 summary + description(ADF) 을 텍스트로 변환한다.
자격증명은 환경변수에서 읽는다(프로파일 .env 자동 로드). Atlassian API 토큰은 계정
단위라 Confluence 와 동일 토큰이 Jira 에도 동작하므로 기본값을 CONFLUENCE_* 로 둔다.
  - 기본: CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN (소스 config 로 변수명 재정의 가능)

순수 파싱(adf_to_text, parse_issues)과 네트워크(주입된 httpx 클라이언트)를 분리해
네트워크 없이 단위 테스트한다.
"""

from __future__ import annotations

import base64
import os
from typing import Any, Protocol


class HttpClient(Protocol):
    async def post(self, url: str, **kwargs: Any) -> Any: ...


def _auth_header(email: str, token: str) -> str:
    raw = f"{email}:{token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def config_from_source(
    source: dict[str, Any],
) -> tuple[str, str | None, str | None, str | None]:
    """소스 config + 환경변수에서 (base_url, project_key, email, token) 을 구성한다.

    base_url 예: https://<site>.atlassian.net (Jira REST 는 사이트 루트의 /rest/api/3).
    Confluence base_url(.../wiki)이 주어지면 /wiki 를 떼어 사이트 루트로 보정한다.
    """
    cfg = source.get("config") or {}
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if base.endswith("/wiki"):
        base = base[: -len("/wiki")]
    project = (cfg.get("project_key") or cfg.get("project") or "").strip()
    email_env = cfg.get("email_env", "CONFLUENCE_EMAIL")
    token_env = cfg.get("token_env", "CONFLUENCE_API_TOKEN")
    if email_env not in os.environ or token_env not in os.environ:
        try:
            from .profiles import load_profile

            load_profile()  # 활성 프로파일 .env 를 os.environ 에 적용(이미 있는 값은 보존)
        except Exception:
            pass
    return base, project, os.environ.get(email_env), os.environ.get(token_env)


def adf_to_text(node: Any) -> str:
    """Atlassian Document Format(ADF) JSON 을 평문 텍스트로 변환(재귀).

    text 노드의 텍스트를 모으고, 블록 경계(문단/제목/리스트 항목)에 줄바꿈을 넣는다.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return ""
    ntype = node.get("type")
    if ntype == "text":
        return node.get("text", "")
    if ntype == "hardBreak":
        return "\n"
    inner = adf_to_text(node.get("content"))
    # 블록 레벨 노드는 뒤에 줄바꿈을 붙여 가독성/검색 토큰 분리를 보존
    if ntype in ("paragraph", "heading", "listItem", "blockquote", "codeBlock", "rule"):
        return inner + "\n"
    return inner


# 기본(범용) 이슈 유형 — 제목 접두로 달면 노이즈라 생략한다(MI 문서 유형만 접두).
_GENERIC_TYPES = {
    "task", "sub-task", "subtask", "story", "epic", "bug",
    "작업", "하위 작업", "스토리", "에픽", "버그",
}


def parse_issues(base_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Jira 검색 응답(JSON)에서 {id,title,text,url} 목록을 추출한다."""
    out: list[dict[str, Any]] = []
    site = base_url.rstrip("/")
    for it in payload.get("issues", []):
        key = it.get("key") or str(it.get("id") or "")
        fields = it.get("fields") or {}
        summary = (fields.get("summary") or "untitled").strip() or "untitled"
        itype = ((fields.get("issuetype") or {}).get("name") or "").strip()
        body = adf_to_text(fields.get("description")).strip()
        # 커스텀 유형(의사결정/미팅메모/프로젝트계획 등)만 제목 접두로 분류 정보를 보존.
        # 이미 summary 가 대괄호로 시작하면 중복 접두를 피한다.
        prefix = itype and itype.lower() not in _GENERIC_TYPES and not summary.startswith("[")
        title = f"[{itype}] {summary}" if prefix else summary
        text = body or summary
        out.append(
            {"id": key, "title": title, "text": text, "url": f"{site}/browse/{key}"}
        )
    return out


async def fetch_issues(
    client: HttpClient,
    base_url: str,
    project_key: str,
    email: str,
    token: str,
    *,
    limit: int = 50,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """프로젝트 이슈를 description 포함으로 가져와 파싱한다(enhanced JQL search).

    HTTP 오류는 httpx 예외로 전파(호출자가 처리).
    """
    url = f"{base_url.rstrip('/')}/rest/api/3/search/jql"
    body = {
        "jql": f'project = "{project_key}" ORDER BY updated DESC',
        "fields": ["summary", "description", "issuetype", "updated"],
        "maxResults": limit,
    }
    resp = await client.post(
        url,
        headers={
            "Authorization": _auth_header(email, token),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_issues(base_url, resp.json())
