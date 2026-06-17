"""DART(전자공시) 커넥터 — 한국 상장 경쟁사의 실(real) IR/재무 데이터.

금융감독원 OpenDART(opendart.fss.or.kr, 무료 공식 API)에서 기업개황 + 최근 공시 +
최근 재무(매출액/영업이익/당기순이익)를 받아 '경쟁사 IR' 문서로 만든다.
인증키는 환경변수 DART_API_KEY(프로파일 .env). corp_code 는 DART 8자리 고유번호.

순수 파싱(parse_company_ir)과 네트워크(fetch_company_ir, 주입된 클라이언트)를 분리한다.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

DART_BASE = "https://opendart.fss.or.kr/api"
# 재무제표 주요 계정(연결재무제표 손익) 추출 대상
_FIN_ACCOUNTS = ("매출액", "영업이익", "당기순이익")


class HttpClient(Protocol):
    async def get(self, url: str, **kwargs: Any) -> Any: ...


def _key() -> str | None:
    return (os.getenv("DART_API_KEY") or "").strip() or None


def config_from_source(source: dict[str, Any]) -> tuple[str | None, str]:
    """소스 config 에서 (corp_code(8자리), name) 구성."""
    cfg = source.get("config") or {}
    corp = str(cfg.get("corp_code") or "").strip()
    if corp.isdigit():
        corp = corp.zfill(8)
    name = (cfg.get("name") or "").strip()
    return (corp or None, name)


def _amount(s: Any) -> str:
    """DART 금액 문자열('1,234,000')을 정리(빈 값은 '-')."""
    txt = str(s or "").strip()
    return txt or "-"


def parse_company_ir(name_fallback: str, overview: dict[str, Any],
                     disclosures: dict[str, Any], financials: dict[str, Any]) -> dict[str, Any]:
    """company/list/fnlttSinglAcnt 응답을 경쟁사 IR 문서({id,title,text,url})로 구성."""
    name = (overview.get("corp_name") or name_fallback or "Unknown").strip()
    corp_code = str(overview.get("corp_code") or "").strip()
    stock = (overview.get("stock_code") or "").strip()
    ceo = (overview.get("ceo_nm") or "").strip()

    # 최근 공시(분기·반기·사업보고서 등)
    filing_lines: list[str] = []
    for it in (disclosures.get("list") or [])[:8]:
        filing_lines.append(f"- {it.get('rcept_dt', '')} {it.get('report_nm', '').strip()}")

    # 최근 재무(연결 손익 주요 계정)
    fin_lines: list[str] = []
    seen: set[str] = set()
    for row in financials.get("list") or []:
        acc = (row.get("account_nm") or "").strip()
        if acc in _FIN_ACCOUNTS and acc not in seen:
            yr = row.get("bsns_year", "")
            fin_lines.append(f"- {acc}: {_amount(row.get('thstrm_amount'))} (FY{yr}, 당기)")
            seen.add(acc)

    text = (
        f"{name} (DART corp_code {corp_code}"
        + (f", 종목 {stock}" if stock else "") + ")"
        + (f" — 대표 {ceo}" if ceo else "") + "\n"
        "DART 전자공시 실제 개황·공시·재무 요약\n\n"
        "## 최근 주요 공시\n" + ("\n".join(filing_lines) or "- (없음)") + "\n\n"
        "## 최근 재무(연결 손익, 원)\n" + ("\n".join(fin_lines) or "- (없음)") + "\n\n"
        f"출처: DART(opendart.fss.or.kr), corp_code {corp_code}"
    )
    url = f"https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm={name}"
    return {"id": corp_code, "title": f"[경쟁사 IR] {name} 개황·공시·재무 (DART)", "text": text, "url": url}


async def fetch_company_ir(client: HttpClient, corp_code: str, name: str = "",
                           *, year: int | None = None, timeout: float = 25.0) -> dict[str, Any]:
    """DART 개황+공시+재무를 가져와 경쟁사 IR 문서로 반환. HTTP 오류는 전파.

    재무는 최근 연도의 사업보고서(11011)부터 시도해 데이터가 있는 첫 해를 사용한다.
    """
    key = _key()
    if not key:
        raise ValueError("DART_API_KEY 미설정")
    if year is None:
        from datetime import datetime, timezone

        year = datetime.now(timezone.utc).year

    ov = await client.get(f"{DART_BASE}/company.json",
                          params={"crtfc_key": key, "corp_code": corp_code}, timeout=timeout)
    ov.raise_for_status()
    overview = ov.json()

    dl = await client.get(f"{DART_BASE}/list.json",
                          params={"crtfc_key": key, "corp_code": corp_code,
                                  "pblntf_ty": "A", "page_count": 10}, timeout=timeout)
    dl.raise_for_status()
    disclosures = dl.json()

    financials: dict[str, Any] = {}
    for y in (year, year - 1, year - 2):  # 최근 연도부터 데이터 있는 해 사용
        fin = await client.get(f"{DART_BASE}/fnlttSinglAcnt.json",
                               params={"crtfc_key": key, "corp_code": corp_code,
                                       "bsns_year": str(y), "reprt_code": "11011",
                                       "fs_div": "CFS"}, timeout=timeout)
        fin.raise_for_status()
        data = fin.json()
        if data.get("status") == "000" and data.get("list"):
            financials = data
            break

    return parse_company_ir(name, overview, disclosures, financials)
