"""Jira 프로젝트에 MI 문서를 이슈로 시드한다(미팅 메모/의사결정/프로젝트 계획).

Jira 가 사이트에 활성화되면 바로 실행할 수 있도록 준비된 스크립트.
문서 유형을 summary 접두([미팅 메모]/[의사결정]/[프로젝트 계획])로 담아, 기본 이슈
유형(Task)만으로도 mi-report 의 Jira 커넥터가 분류 정보를 보존하게 한다.

실행:
  cd backend && .venv/bin/python -m tools.seed_jira <PROJECT_KEY>
자격증명은 활성 프로파일 .env(CONFLUENCE_EMAIL/API_TOKEN = 계정 토큰, Jira 공용).
모든 회사/수치는 허구. 먼저 Jira REST 도달 가능 여부를 점검하고, 불가하면 안내한다.
"""

from __future__ import annotations

import base64
import os
import sys

import httpx

from app.profiles import load_profile

SITE = "https://oseokkim2001-1776691210112.atlassian.net"


def _headers() -> dict[str, str]:
    load_profile()
    email = os.environ.get("CONFLUENCE_EMAIL")
    token = os.environ.get("CONFLUENCE_API_TOKEN")
    if not email or not token:
        print("CONFLUENCE_EMAIL/API_TOKEN(계정 토큰) 미설정", file=sys.stderr)
        raise SystemExit(1)
    raw = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}", "Accept": "application/json",
            "Content-Type": "application/json"}


def _adf(blocks: list[tuple[str, object]]) -> dict:
    """간단한 ADF 문서 생성. blocks: ('h', 텍스트) | ('p', 텍스트) | ('ul', [텍스트...])."""
    content: list[dict] = []
    for kind, val in blocks:
        if kind == "h":
            content.append({"type": "heading", "attrs": {"level": 3},
                            "content": [{"type": "text", "text": str(val)}]})
        elif kind == "p":
            content.append({"type": "paragraph",
                            "content": [{"type": "text", "text": str(val)}]})
        elif kind == "ul":
            items = [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": str(t)}]}]}
                for t in val  # type: ignore[union-attr]
            ]
            content.append({"type": "bulletList", "content": items})
    return {"type": "doc", "version": 1, "content": content}


# ── 시드할 이슈(허구 MI) — Confluence 시드와 동일 주제 ──────────────────────
ISSUES: list[tuple[str, dict]] = [
    ("[미팅 메모] 주간 MI 리뷰 2026-06-12", _adf([
        ("p", "날짜: 2026-06-12 / 참석: MI팀, S.LSI 기획, 메모리 마케팅"),
        ("h", "토론 항목"),
        ("ul", ["HBM4 12단 채택 공식화 — 양산 목표 2027 상반기.",
                "경쟁사 Q FY26 Q2 콜: 프리미엄 AP ASP 상승, 차량용 두 자릿수 가이던스.",
                "가상 X사 2nm 위험생산 개시 보도(고객사·수율 미확인)."]),
        ("h", "액션 아이템"),
        ("ul", ["HBM4 12단 공급망 영향 분석 — MI팀, 6/19까지.",
                "경쟁사 차량용 백로그 추세 업데이트 — IR트래킹."]),
    ])),
    ("[미팅 메모] 경쟁사 IR 대응 회의 2026-06-05", _adf([
        ("p", "날짜: 2026-06-05 / 참석: MI팀, 재무, 전략기획"),
        ("h", "토론 항목"),
        ("ul", ["경쟁사 Q 매출 117억 달러, QoQ +3.2%, 영업이익률 29.1%.",
                "핸드셋 QoQ -2.1%이나 온디바이스 AI로 프리미엄 AP ASP 상승.",
                "HBM 밸류체인 목표주가 상향(가상 메모리 A, 가상 팹리스 Z)."]),
        ("h", "액션 아이템"),
        ("ul", ["컨센서스 목표주가 변동 트래킹 자동화 검토 — MI팀, 6/12."]),
    ])),
    ("[의사결정] HBM4 12단 베이스 다이 우선 대응", _adf([
        ("p", "상태: 결정됨 / 주도: MI팀, 기여: 메모리사업부"),
        ("h", "배경"),
        ("p", "HBM4 12단 채택 공식화로 메모리 사양 고도화 가속. 선단 패키징 캐파가 핵심 병목."),
        ("h", "검토한 옵션"),
        ("ul", ["A. HBM4 베이스 다이·컨트롤러 IP 수주 기회 집중(선택).",
                "B. 기존 HBM3E 중심 유지.", "C. 보류, 1개 분기 관찰."]),
        ("h", "결정/영향"),
        ("p", "옵션 A 채택. 다이제스트·주간 리포트에서 HBM4 항목을 영향도 '상'으로 상시 노출, "
              "선단 패키징 캐파 병목을 리스크로 병기."),
    ])),
    ("[의사결정] 온디바이스 AI 보급형 AP 모니터링 체계 도입", _adf([
        ("p", "상태: 결정됨 / 주도: MI팀, 이해관계자: SET 상품기획"),
        ("h", "배경"),
        ("p", "온디바이스 AI가 프리미엄 AP ASP 상승을 견인하나, 보급형 확산 시 차별화 약화 우려."),
        ("h", "결정/영향"),
        ("p", "보급형 AP의 AI 탑재 확산을 별도 지표로 신설해 ASP 잠식 신호를 조기 포착. "
              "수요/시황 주제에 '보급형 AP AI 침투' 추적 항목 추가."),
    ])),
    ("[프로젝트 계획] 2026 H2 MI 자동화 로드맵", _adf([
        ("p", "진행자: MI팀 / 기한: 2026-12-31"),
        ("h", "목표"),
        ("p", "수집→분류→AI 생성→리포트 파이프라인 반자동화 및 근거 추적성 강화."),
        ("h", "마일스톤"),
        ("ul", ["M1(7월): 수집·분류 안정화", "M2(9월): RAG 검증셋 확장·성능 개선",
                "M3(11월): 경쟁사/주제 자동화", "M4(12월): 통합 주간 리포트 자동 발행"]),
    ])),
    ("[프로젝트 계획] 2nm 파운드리·EDA 생태계 추적", _adf([
        ("p", "진행자: MI팀 / 기한: 2026-09-30"),
        ("h", "목표"),
        ("p", "2nm 전환기의 파운드리 수율·생태계(EDA/IP) 동향 체계적 추적."),
        ("h", "범위 — 제외"),
        ("ul", ["장비(EUV) 상세 CAPEX 분석", "비-2nm 노드"]),
        ("h", "마일스톤"),
        ("ul", ["M1(7월): 뉴스 타임라인", "M2(8월): EDA 생태계 맵핑", "M3(9월): 수주 영향 분석"]),
    ])),
]


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: python -m tools.seed_jira <PROJECT_KEY>", file=sys.stderr)
        return 2
    project_key = sys.argv[1]
    issue_type = sys.argv[2] if len(sys.argv) > 2 else "Task"
    headers = _headers()
    with httpx.Client(timeout=30) as c:
        # 0) Jira 도달 가능 여부 점검
        probe = c.get(f"{SITE}/rest/api/3/myself", headers=headers)
        if probe.status_code == 404:
            print("Jira 미활성(REST 404). admin.atlassian.com 에서 Jira 제품을 추가한 뒤 재실행하세요.",
                  file=sys.stderr)
            return 1
        probe.raise_for_status()

        created = 0
        for summary, description in ISSUES:
            payload = {"fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }}
            r = c.post(f"{SITE}/rest/api/3/issue", headers=headers, json=payload)
            if r.status_code in (200, 201):
                print(f"created: {r.json().get('key')}  {summary}")
                created += 1
            else:
                print(f"FAIL {r.status_code}: {summary} — {r.text[:200]}")
        print(f"\n완료: 이슈 생성 {created}/{len(ISSUES)} (프로젝트 {project_key})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
