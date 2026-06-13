"""URL 수집 — 웹 페이지를 가져와 본문 텍스트를 추출한다.

커넥터 소스(뉴스 등)의 '지금 수집'이 실제로 동작하도록, 등록된 URL 을 fetch 해
HTML 에서 제목·본문 텍스트를 뽑는다. HTML→텍스트 추출은 stdlib html.parser 기반의
가벼운 방식(스크립트/스타일 제거 + 공백 정리)이라 포털 홈처럼 동적인 페이지는
추출이 부실할 수 있다(기사 URL 이 더 잘 맞는다).

순수 추출 로직(extract_text_from_html)과 네트워크(fetch_url, 주입된 httpx 클라이언트)를
분리해, 네트워크 없이 추출을 단위 테스트한다.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Protocol

# 본문에서 제외할 컨테이너 태그(이 안의 텍스트는 버린다).
# 주의: 닫는 태그가 없는 void 태그(meta/link 등)는 넣지 않는다 — starttag 에서만
# depth 가 올라가고 영영 안 내려가 이후 본문을 통째로 건너뛰게 된다. 어차피 void
# 태그는 텍스트 콘텐츠가 없어 제외할 필요도 없다.
_SKIP_TAGS = {"script", "style", "noscript", "head", "template", "svg"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)


def extract_text_from_html(html: str) -> tuple[str, str]:
    """HTML 문자열에서 (제목, 본문 텍스트)를 추출한다(공백 정리)."""
    parser = _TextExtractor()
    parser.feed(html)
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    text = "\n".join(parser.text_parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


class HttpClient(Protocol):
    async def get(self, url: str, **kwargs: Any) -> Any: ...


async def fetch_url(
    client: HttpClient, url: str, *, max_chars: int = 8000, timeout: float = 15.0
) -> dict[str, Any]:
    """URL 을 가져와 {url, title, text} 로 반환한다. HTML 이면 본문을 추출한다.

    HTTP 오류는 httpx 예외로 전파된다(호출자가 처리).
    """
    resp = await client.get(
        url,
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MI-Report-Agent/1.0)"},
    )
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()
    body = resp.text
    if "html" in content_type or body.lstrip()[:1] == "<":
        title, text = extract_text_from_html(body)
    else:
        title, text = "", body.strip()
    if not title:
        title = url
    return {"url": url, "title": title[:200], "text": text[:max_chars]}
