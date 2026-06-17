"""한경 컨센서스 커넥터 — 증권사 리포트 PDF 본문 추출.

consensus.hankyung.com 리스트에서 리포트별 PDF(`/analysis/downpdf?report_idx=...`)를
받아 본문 텍스트를 추출(pypdf)해 문서로 인입한다. HTML 요약보다 풍부한 실제 리포트 본문.

주의(저작권): PDF 는 각 증권사가 작성한 리서치 리포트로 저작권이 증권사에 있다. 한경은
개인 열람용으로 집계한다. 대량 수집·DB화·재배포는 이용약관/저작권 검토가 필요하므로,
기본 수집 건수를 보수적으로 제한한다(LIMIT_DEFAULT).

순수 파싱(parse_listing)과 네트워크(fetch_reports, 주입된 클라이언트)를 분리해 테스트한다.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

BASE_DEFAULT = "https://consensus.hankyung.com"
LIST_PATH = "/analysis/list?skinType=business"
LIMIT_DEFAULT = 10  # 저작권 고려: 보수적 기본 상한
_MAX_PAGES = 6      # PDF 당 추출 페이지 상한
_MAX_CHARS = 6000   # 문서당 본문 길이 상한

_ROW = re.compile(r'/analysis/downpdf\?report_idx=(\d+)"[^>]*>\s*([^<]+?)\s*</a>')


class HttpClient(Protocol):
    async def get(self, url: str, **kwargs: Any) -> Any: ...


def _headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 (mi-report)", "Referer": BASE_DEFAULT + "/"}


def parse_listing(html: str) -> list[dict[str, str]]:
    """리스트 HTML 에서 {report_idx, title} 목록을 추출(중복 제거, 순서 보존)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, text in _ROW.findall(html or ""):
        if idx in seen:
            continue
        seen.add(idx)
        title = re.sub(r"\s+", " ", text).strip()
        if title:
            out.append({"report_idx": idx, "title": title})
    return out


def extract_pdf_text(content: bytes) -> str:
    """PDF 바이트에서 앞 몇 페이지 텍스트를 추출. 실패 시 빈 문자열."""
    if not content or content[:4] != b"%PDF":
        return ""
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        parts = []
        for page in reader.pages[:_MAX_PAGES]:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t.strip())
        return "\n".join(parts)[:_MAX_CHARS]
    except Exception:
        return ""


def _doc(base: str, idx: str, title: str, body: str) -> dict[str, Any]:
    url = f"{base}/analysis/downpdf?report_idx={idx}"
    text = (f"{title}\n\n{body}".strip() if body else title) + f"\n\n출처: 한경 컨센서스(report_idx {idx})"
    return {"id": idx, "title": f"[증권사 리포트] {title}", "text": text, "url": url}


async def fetch_reports(client: HttpClient, base: str = BASE_DEFAULT, *,
                        limit: int = LIMIT_DEFAULT, timeout: float = 30.0) -> list[dict[str, Any]]:
    """리스트를 가져와 상위 limit 개 리포트 PDF 본문을 추출해 문서 목록으로 반환."""
    base = base.rstrip("/")
    listing = await client.get(base + LIST_PATH, headers=_headers(), timeout=timeout)
    listing.raise_for_status()
    rows = parse_listing(listing.text)[: max(1, min(limit, 30))]

    docs: list[dict[str, Any]] = []
    for row in rows:
        idx = row["report_idx"]
        try:
            resp = await client.get(f"{base}/analysis/downpdf?report_idx={idx}",
                                    headers=_headers(), timeout=timeout)
            resp.raise_for_status()
            body = extract_pdf_text(resp.content)
        except Exception:
            body = ""
        docs.append(_doc(base, idx, row["title"], body))
    return docs
