"""SEC EDGAR 커넥터 — 미국 상장 경쟁사의 실(real) IR/재무 데이터.

data.sec.gov(무료 공식 API)에서 submissions(공시 목록) + companyfacts(XBRL 재무)를
받아 최근 분기 핵심 지표와 주요 공시를 '경쟁사 IR' 문서로 만든다. 경쟁사 분석(LLM)이
허구 데이터가 아니라 실제 공시·재무에 근거하도록 한다.

SEC 는 식별용 User-Agent 헤더를 요구한다(SEC_USER_AGENT 로 재정의). 순수 파싱
(parse_company_ir)과 네트워크(fetch_company_ir, 주입된 클라이언트)를 분리해 테스트한다.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

SEC_BASE = "https://data.sec.gov"
DEFAULT_UA = "mi-report/0.1 (contact: mi-report@example.com)"

# 핵심 재무 태그(us-gaap) → 표시명. 회사마다 매출 태그가 달라 여러 후보를 둔다.
KEY_TAGS: list[tuple[str, str]] = [
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "매출"),
    ("Revenues", "매출"),
    ("GrossProfit", "매출총이익"),
    ("OperatingIncomeLoss", "영업이익"),
    ("NetIncomeLoss", "순이익"),
    ("ResearchAndDevelopmentExpense", "R&D비용"),
    ("EarningsPerShareDiluted", "희석주당순이익(EPS)"),
]


class HttpClient(Protocol):
    async def get(self, url: str, **kwargs: Any) -> Any: ...


def _ua() -> str:
    return (os.getenv("SEC_USER_AGENT") or DEFAULT_UA).strip()


def config_from_source(source: dict[str, Any]) -> tuple[str | None, str]:
    """소스 config 에서 (cik(10자리 zero-pad), name) 구성."""
    cfg = source.get("config") or {}
    cik = str(cfg.get("cik") or "").strip().lstrip("CIK").lstrip("cik").strip()
    name = (cfg.get("name") or "").strip()
    if cik.isdigit():
        cik = cik.zfill(10)
    return (cik or None, name)


def _period_days(r: dict[str, Any]) -> int | None:
    """XBRL 항목의 보고 구간 일수(start~end). instant 항목은 None."""
    from datetime import date

    s, e = r.get("start"), r.get("end")
    if not s or not e:
        return None
    try:
        return (date.fromisoformat(e) - date.fromisoformat(s)).days
    except ValueError:
        return None


def _latest_quarterly(facts: dict[str, Any], tag: str):
    """태그의 '최근 분기(3개월)' 값(end,val,form,fp) 반환(없으면 None).

    같은 분기 보고에 분기(3개월)와 누적(YTD) 값이 함께 있어, 흐름 지표는 약 3개월
    구간(60~100일) 값을 우선해 누적치 혼입을 막는다.
    """
    node = (facts.get("facts", {}).get("us-gaap", {}) or {}).get(tag) or {}
    units = node.get("units", {}) or {}
    series = units.get("USD") or units.get("USD/shares")
    if series is None:
        series = next(iter(units.values()), [])
    rows = [x for x in series if x.get("form") in ("10-Q", "10-K") and x.get("end")]
    if not rows:
        return None
    quarterly = [r for r in rows if (d := _period_days(r)) is not None and 60 <= d <= 100]
    pool = quarterly or rows  # 분기 구간이 없으면(EPS/잔액 등) 전체에서 선택
    x = max(pool, key=lambda r: r.get("end", ""))
    return (x.get("end"), x.get("val"), x.get("form"), x.get("fp"))


def _fmt(val: Any) -> str:
    return f"{val:,}" if isinstance(val, (int, float)) else str(val)


def parse_company_ir(name_fallback: str, submissions: dict[str, Any],
                     facts: dict[str, Any]) -> dict[str, Any]:
    """submissions + companyfacts 를 경쟁사 IR 문서({id,title,text,url})로 구성."""
    name = facts.get("entityName") or submissions.get("name") or name_fallback or "Unknown"
    # 회사명의 '/'(예: "QUALCOMM INC/DE")는 제목 경로 처리에서 잘리므로 정리.
    name = name.replace("/", "-").strip()
    cik = str(facts.get("cik") or submissions.get("cik") or "")

    rec = (submissions.get("filings") or {}).get("recent") or {}
    forms, dates = rec.get("form", []), rec.get("filingDate", [])
    filing_lines: list[str] = []
    for i in range(len(forms)):
        if forms[i] in ("10-Q", "10-K", "8-K"):
            filing_lines.append(f"- {dates[i]} {forms[i]}")
        if len(filing_lines) >= 8:
            break

    fin_lines: list[str] = []
    seen: set[str] = set()
    for tag, label in KEY_TAGS:
        if label in seen:
            continue
        v = _latest_quarterly(facts, tag)
        if v:
            end, val, form, fp = v
            fin_lines.append(f"- {label}: {_fmt(val)} (기준 {end}, {form} {fp})")
            seen.add(label)

    text = (
        f"{name} (CIK {cik}) — SEC EDGAR 실제 공시·재무 요약\n\n"
        "## 최근 주요 공시\n" + ("\n".join(filing_lines) or "- (없음)") + "\n\n"
        "## 최근 분기 핵심 재무 (us-gaap, USD)\n" + ("\n".join(fin_lines) or "- (없음)") + "\n\n"
        f"출처: SEC EDGAR (data.sec.gov), CIK {cik}"
    )
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-Q"
    return {"id": cik, "title": f"[경쟁사 IR] {name} 실적·공시 (SEC EDGAR)", "text": text, "url": url}


async def fetch_company_ir(client: HttpClient, cik: str, name: str = "",
                           *, timeout: float = 25.0) -> dict[str, Any]:
    """SEC 공시+재무를 가져와 경쟁사 IR 문서로 반환. HTTP 오류는 전파."""
    headers = {"User-Agent": _ua(), "Accept": "application/json"}
    sub = await client.get(f"{SEC_BASE}/submissions/CIK{cik}.json", headers=headers, timeout=timeout)
    sub.raise_for_status()
    facts = await client.get(
        f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json", headers=headers, timeout=timeout
    )
    facts.raise_for_status()
    return parse_company_ir(name, sub.json(), facts.json())
