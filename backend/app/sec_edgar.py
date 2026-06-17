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

# 외국 기업(IFRS, 20-F/6-K) 태그 — 예: TSMC. data.sec.gov 의 ifrs-full 택소노미.
KEY_TAGS_IFRS: list[tuple[str, str]] = [
    ("Revenue", "매출"),
    ("GrossProfit", "매출총이익"),
    ("ProfitLossFromOperatingActivities", "영업이익"),
    ("ProfitLoss", "순이익"),
    ("ResearchAndDevelopmentExpense", "R&D비용"),
    ("DilutedEarningsLossPerShare", "희석주당순이익(EPS)"),
]
_US_FORMS = ("10-Q", "10-K")
_FOREIGN_FORMS = ("20-F", "6-K", "40-F")
_FILING_FORMS = ("10-Q", "10-K", "8-K", "20-F", "6-K", "40-F")


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


def _pick_unit(units: dict[str, Any]) -> tuple[str, list]:
    """통화 단위 선택 — USD(또는 USD/shares) 우선, 없으면 첫 단위. (단위명, 시계열) 반환."""
    for key in ("USD", "USD/shares"):
        if units.get(key):
            return key, units[key]
    for key, series in units.items():  # TWD 등 외화
        if series:
            return key, series
    return "", []


def _latest_fact(facts: dict[str, Any], taxonomy: str, tag: str, forms: tuple[str, ...],
                 *, quarterly: bool):
    """태그의 최신 값(end,val,form,fp,unit) 반환(없으면 None).

    quarterly=True(us-gaap 분기): 약 3개월(60~100일) 구간을 우선해 누적치 혼입 방지.
    quarterly=False(IFRS 연차 20-F): 최신 보고 값을 그대로 사용. 통화는 USD 우선.
    """
    node = (facts.get("facts", {}).get(taxonomy, {}) or {}).get(tag) or {}
    unit, series = _pick_unit(node.get("units", {}) or {})
    rows = [x for x in series if x.get("form") in forms and x.get("end")]
    if not rows:
        return None
    if quarterly:
        q = [r for r in rows if (d := _period_days(r)) is not None and 60 <= d <= 100]
        rows = q or rows
    x = max(rows, key=lambda r: r.get("end", ""))
    return (x.get("end"), x.get("val"), x.get("form"), x.get("fp"), unit)


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
        if forms[i] in _FILING_FORMS:
            filing_lines.append(f"- {dates[i]} {forms[i]}")
        if len(filing_lines) >= 8:
            break

    # 택소노미 자동 판별: us-gaap(미국 기업, 분기) vs ifrs-full(외국 기업, 20-F 연차).
    # 외국 발행자(예: ASML)는 빈약한 us-gaap 키와 충실한 ifrs-full 을 함께 가질 수 있어,
    # '키 존재' 만으로 고르면 재무가 비어버린다. 실제 재무 라인이 더 많이 나오는 쪽을 채택한다.
    taxos = facts.get("facts", {})

    def _extract(taxo: str, tags, forms, quarterly: bool) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for tag, label in tags:
            if label in seen:
                continue
            v = _latest_fact(facts, taxo, tag, forms, quarterly=quarterly)
            if v:
                end, val, form, fp, unit = v
                lines.append(f"- {label}: {_fmt(val)} {unit} (기준 {end}, {form} {fp})".replace("  ", " "))
                seen.add(label)
        return lines

    candidates = []
    if taxos.get("us-gaap"):
        candidates.append((_extract("us-gaap", KEY_TAGS, _US_FORMS, True), True, "최근 분기 핵심 재무 (us-gaap)"))
        # us-gaap 로 보고하지만 20-F(외국 발행자, 연차)로 제출하는 기업(예: ASML).
        candidates.append((_extract("us-gaap", KEY_TAGS, _FOREIGN_FORMS, False), False,
                           "최근 핵심 재무 (us-gaap, 20-F)"))
    if taxos.get("ifrs-full"):
        candidates.append((_extract("ifrs-full", KEY_TAGS_IFRS, _FOREIGN_FORMS, False), False,
                           "최근 핵심 재무 (IFRS, 20-F)"))
    if not candidates:  # 둘 다 없으면 us-gaap 가정(빈 결과)
        candidates.append(([], True, "최근 분기 핵심 재무 (us-gaap)"))
    fin_lines, quarterly, fin_label = max(candidates, key=lambda c: len(c[0]))

    # 검색(회수)용 별칭·티커 — 예: 'TSMC'(별칭) / 'TSM'(티커)로도 이 문서를 찾도록.
    tickers = submissions.get("tickers") or []
    aliases = [a for a in [name_fallback, *tickers] if a and a.lower() not in name.lower()]
    alias_line = (f"별칭/티커: {', '.join(dict.fromkeys(aliases))}\n" if aliases else "")

    text = (
        f"{name} (CIK {cik}) — SEC EDGAR 실제 공시·재무 요약\n"
        + alias_line + "\n"
        "## 최근 주요 공시\n" + ("\n".join(filing_lines) or "- (없음)") + "\n\n"
        f"## {fin_label}\n" + ("\n".join(fin_lines) or "- (없음)") + "\n\n"
        f"출처: SEC EDGAR (data.sec.gov), CIK {cik}"
    )
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-Q"
    # 통칭/티커를 제목에도 노출 — 'AMD'·'TSMC' 같은 통칭으로 회수/표시되도록.
    title_name = f"{name} ({', '.join(dict.fromkeys(aliases))})" if aliases else name
    return {"id": cik, "title": f"[경쟁사 IR] {title_name} 실적·공시 (SEC EDGAR)", "text": text, "url": url}


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
