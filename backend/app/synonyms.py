"""반도체/IT MI 도메인 동의어 사전 — 검색 질의 확장.

BM25(어휘 매칭)는 '시험양산'과 '위험생산'을 다른 토큰으로 본다. 도메인 동의어를
질의에 덧붙여(OR 매칭) 동의어/약어 격차를 결정적으로 메운다. 외부 호출이 없어
유출 위험이 없고, 검증셋으로 효과를 측정할 수 있다.

확장: SYNONYM_GROUPS 에 같은 의미 표현들을 한 묶음으로 추가한다.
"""

from __future__ import annotations

# 한 묶음 안의 표현들은 서로 동의어/약어로 취급한다(양방향).
SYNONYM_GROUPS: list[frozenset[str]] = [
    frozenset({"HBM", "고대역폭메모리", "고대역폭 메모리"}),
    frozenset({"위험생산", "시험양산", "리스크프로덕션", "risk production"}),
    frozenset({"2nm", "미세공정", "선단공정", "선단 공정", "첨단공정"}),
    frozenset({"ADAS", "자율주행", "첨단운전자보조"}),
    frozenset({"CXL", "컴퓨트익스프레스링크", "compute express link"}),
    frozenset({"파운드리", "위탁생산", "foundry"}),
    frozenset({"EDA", "설계자동화"}),
    frozenset({"NPU", "신경망처리장치"}),
    frozenset({"온디바이스", "온디바이스 AI", "단말 AI", "on-device"}),
    frozenset({"팹리스", "fabless"}),
    frozenset({"컨센서스", "시장기대치", "consensus"}),
    frozenset({"AP", "애플리케이션프로세서", "애플리케이션 프로세서", "두뇌칩", "두뇌 칩"}),
    frozenset({"ASP", "평균판매가격", "평균 판매가격", "average selling price"}),
    frozenset({"DRAM", "D램", "디램"}),
    frozenset({"캐파", "생산능력", "생산 능력", "capacity"}),
    frozenset({"선단패키징", "선단 패키징", "첨단패키징", "후공정", "적층결합"}),
    frozenset({"목표주가", "적정가", "target price"}),
]


def expand_query(q: str) -> str:
    """질의에 도메인 동의어를 덧붙여 반환(매칭되는 묶음이 없으면 원문 그대로).

    예: '시험양산' -> '시험양산 위험생산 리스크프로덕션 ...'
    이미 질의에 있는 표현은 중복으로 추가하지 않는다.
    """
    if not q or not q.strip():
        return q
    ql = q.lower()
    seen: set[str] = set()
    extra: list[str] = []
    for group in SYNONYM_GROUPS:
        if not any(m.lower() in ql for m in group):
            continue
        for term in group:
            k = term.lower()
            if k in seen or k in ql:
                continue
            seen.add(k)
            extra.append(term)
    if not extra:
        return q
    return q + " " + " ".join(extra)
