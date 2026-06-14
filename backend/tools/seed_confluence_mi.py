"""Confluence 'Mi_report' 스페이스에 MI 문서를 시드한다(템플릿 구조 참조).

스페이스의 기존 템플릿(미팅 메모 / 의사 결정 문서 / 프로젝트 계획) 구조를 따라
실제(허구) MI 문서를 생성한다. mi-report 의 Confluence 커넥터가 이를 수집해
RAG/다이제스트가 참조하도록 한다.

실행:
  cd backend && .venv/bin/python -m tools.seed_confluence_mi
자격증명은 활성 프로파일 .env(CONFLUENCE_EMAIL/API_TOKEN). 모든 회사/수치는 허구.
"""

from __future__ import annotations

import base64
import html
import os
import sys

import httpx

from app.profiles import load_profile

SITE = "https://oseokkim2001-1776691210112.atlassian.net"
SPACE_ID = "7733415"  # Mi_report 스페이스


def _auth() -> dict[str, str]:
    load_profile()
    email = os.environ.get("CONFLUENCE_EMAIL")
    token = os.environ.get("CONFLUENCE_API_TOKEN")
    if not email or not token:
        print("CONFLUENCE_EMAIL/API_TOKEN 미설정", file=sys.stderr)
        raise SystemExit(1)
    raw = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}", "Accept": "application/json",
            "Content-Type": "application/json"}


def _e(s: str) -> str:
    """저장 포맷(XHTML)에 안전하도록 텍스트를 이스케이프(예: Q&A 의 &)."""
    return html.escape(s, quote=False)


def _kv_table(rows: list[tuple[str, str]]) -> str:
    trs = "".join(
        f"<tr><td data-highlight-colour='#f4f5f7'><p><strong>{_e(k)}</strong></p></td>"
        f"<td><p>{_e(v)}</p></td></tr>"
        for k, v in rows
    )
    return f"<table data-layout='default'><tbody>{trs}</tbody></table>"


def _ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li><p>{_e(i)}</p></li>" for i in items) + "</ul>"


# ── 템플릿 구조별 본문 빌더 ────────────────────────────────────────────────
def meeting_note(date: str, attendees: str, goal: str,
                 discussion: list[str], decisions: list[str], actions: list[str]) -> str:
    return (
        _kv_table([("날짜", date), ("참석자", attendees), ("목표", goal)])
        + "<h2>토론 항목</h2>" + _ul(discussion)
        + "<h2>결정 사항</h2>" + _ul(decisions)
        + "<h2>액션 아이템</h2>" + _ul(actions)
    )


def decision_doc(status: str, stakeholders: str, context: str,
                 options: list[str], outcome: str, impact: str) -> str:
    return (
        _kv_table([("결정 상태", status), ("관련 인원", stakeholders)])
        + "<h2>배경(맥락)</h2><p>" + _e(context) + "</p>"
        + "<h2>검토한 옵션</h2>" + _ul(options)
        + "<h2>결정 결과</h2><p>" + _e(outcome) + "</p>"
        + "<h2>영향</h2><p>" + _e(impact) + "</p>"
    )


def project_plan(owner: str, goal: str, due: str, deliverables: list[str],
                 scope_in: list[str], scope_out: list[str], milestones: list[str]) -> str:
    return (
        _kv_table([("진행자", owner), ("목표", goal), ("기한일", due)])
        + "<h2>주요 결과물</h2>" + _ul(deliverables)
        + "<h2>범위 — 포함</h2>" + _ul(scope_in)
        + "<h2>범위 — 제외</h2>" + _ul(scope_out)
        + "<h2>마일스톤</h2>" + _ul(milestones)
    )


# ── 시드할 문서(허구 MI) ───────────────────────────────────────────────────
PAGES: list[tuple[str, str]] = [
    ("[미팅 메모] 주간 MI 리뷰 2026-06-12", meeting_note(
        "2026-06-12", "MI팀, S.LSI 기획, 메모리 마케팅",
        "이번 주 반도체·IT 시그널 공유 및 대응 우선순위 합의",
        ["HBM4 12단 채택 공식화 — 차세대 AI 가속기 메모리 사양 고도화, 양산 목표 2027 상반기.",
         "경쟁사 Q FY26 Q2 콜 요약 공유 — 프리미엄 AP ASP 상승 지속, 차량용 두 자릿수 가이던스.",
         "가상 X사 2nm 위험생산 개시 보도(고객사·수율 미확인) — 신뢰도 중간."],
        ["HBM4 베이스 다이/컨트롤러 IP 기회를 이번 분기 핵심 추적 주제로 격상.",
         "2nm 보도는 추가 확인 전까지 '관찰' 등급 유지."],
        ["[행동] HBM4 12단 공급망 영향 분석 — 담당 MI팀, 6/19까지.",
         "[행동] 경쟁사 차량용 백로그 추세 다음 회의에 업데이트 — 담당 IR트래킹."],
    )),
    ("[미팅 메모] 경쟁사 IR 대응 회의 2026-06-05", meeting_note(
        "2026-06-05", "MI팀, 재무, 전략기획",
        "경쟁사 Q 분기 실적·컨센서스 변화 점검",
        ["경쟁사 Q 매출 117억 달러, QoQ +3.2%, 영업이익률 29.1%.",
         "핸드셋 매출 QoQ -2.1%이나 온디바이스 AI로 프리미엄 AP ASP 상승.",
         "HBM 밸류체인 목표주가 상향 흐름(가상 메모리 A, 가상 팹리스 Z)."],
        ["경쟁사 ASP 상승 동인을 온디바이스 AI 침투율과 연동해 추적."],
        ["[행동] 컨센서스 목표주가 변동 트래킹 자동화 검토 — 담당 MI팀, 6/12."],
    )),
    ("[의사결정] HBM4 12단 베이스 다이 우선 대응", decision_doc(
        "결정됨", "주도: MI팀 / 기여: 메모리사업부 / 이해관계자: S.LSI 기획",
        "차세대 AI 가속기의 HBM4 12단 채택이 공식화되며 메모리 사양 고도화가 가속. "
        "선단 패키징 캐파가 공급의 핵심 병목으로 지목됨. 수요 증가율이 서버 출하 증가율을 상회 전망.",
        ["A. HBM4 베이스 다이·컨트롤러 IP 수주 기회에 자원 집중(선택).",
         "B. 기존 HBM3E 중심 대응 유지.",
         "C. 의사결정 보류, 1개 분기 추가 관찰."],
        "옵션 A 채택 — HBM4 12단 전환을 최우선 추적 주제로 격상하고 베이스 다이/컨트롤러 IP "
        "기회를 분기 KPI 로 관리한다.",
        "MI 다이제스트·주간 리포트에서 HBM4 항목을 영향도 '상'으로 상시 노출. 선단 패키징 캐파 "
        "병목을 리스크로 병기.",
    )),
    ("[의사결정] 온디바이스 AI 보급형 AP 모니터링 체계 도입", decision_doc(
        "결정됨", "주도: MI팀 / 이해관계자: SET 상품기획",
        "온디바이스 AI가 프리미엄 AP ASP 상승을 견인하는 한편, 보급형 AP로 AI 기능이 확산되며 "
        "기능 차별화가 약화될 가능성. 침투율 추세의 정량 추적 필요.",
        ["A. 보급형/프리미엄 AP 침투율을 분리 추적하는 모니터링 지표 신설(선택).",
         "B. 기존 프리미엄 중심 추적 유지."],
        "옵션 A 채택 — 보급형 AP의 AI 탑재 확산을 별도 지표로 신설해 ASP 잠식 신호를 조기 포착.",
        "수요/시황 주제에 '보급형 AP AI 침투' 추적 항목 추가. 분기별 리포트에 반영.",
    )),
    ("[프로젝트 계획] 2026 H2 MI 자동화 로드맵", project_plan(
        "MI팀", "수집→분류→AI 생성→리포트 파이프라인을 반자동화하고 근거 추적성을 강화", "2026-12-31",
        ["주 2회 뉴스 다이제스트 자동 생성·메일링", "주제별 History 자동 갱신",
         "경쟁사 IR 분기 분석 자동화", "RAG 문서 Q&A 품질 검증셋 운영"],
        ["뉴스·증권사·컨센서스·Confluence 소스 수집 자동화", "하이브리드 검색(BM25+동의어+임베딩) 고도화",
         "생성물 지식 자산화 및 피드백 루프"],
        ["실시간 웹검색", "사내 DRM 문서 자동 인입(별도 COM 워커 트랙)"],
        ["M1(7월): 수집·분류 안정화", "M2(9월): RAG 검증셋 확장·성능 개선",
         "M3(11월): 경쟁사/주제 자동화", "M4(12월): 통합 주간 리포트 자동 발행"],
    )),
    ("[프로젝트 계획] 2nm 파운드리·EDA 생태계 추적", project_plan(
        "MI팀", "2nm 전환기의 파운드리 수율·생태계(EDA/IP) 동향을 체계적으로 추적", "2026-09-30",
        ["2nm 위험생산·수율 뉴스 타임라인", "EDA 레퍼런스 플로우/PPA 동향 요약",
         "설계 생태계가 수주 변별에 미치는 영향 분석"],
        ["가상 X사 2nm 위험생산 추적", "가상 Y사 EDA 레퍼런스 디자인 플로우 모니터링",
         "GAA 공정 수율 안정화 신호 수집"],
        ["장비(EUV) 상세 CAPEX 분석", "비-2nm 노드"],
        ["M1(7월): 뉴스 타임라인 구축", "M2(8월): EDA 생태계 맵핑", "M3(9월): 수주 영향 분석 리포트"],
    )),
]


def main() -> int:
    headers = _auth()
    with httpx.Client(timeout=30) as c:
        existing = set()
        r = c.get(f"{SITE}/wiki/api/v2/spaces/{SPACE_ID}/pages",
                  headers=headers, params={"limit": 100})
        r.raise_for_status()
        for p in r.json().get("results", []):
            existing.add(p.get("title"))

        created, skipped = 0, 0
        for title, body in PAGES:
            if title in existing:
                print(f"skip (이미 있음): {title}")
                skipped += 1
                continue
            payload = {
                "spaceId": SPACE_ID,
                "status": "current",
                "title": title,
                "body": {"representation": "storage", "value": body},
            }
            resp = c.post(f"{SITE}/wiki/api/v2/pages", headers=headers, json=payload)
            if resp.status_code in (200, 201):
                print(f"created: {title}")
                created += 1
            else:
                print(f"FAIL {resp.status_code}: {title} — {resp.text[:200]}")
        print(f"\n완료: 생성 {created} · 건너뜀 {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
