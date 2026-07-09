"""환각 방어 — 생성물의 수치가 근거 문서에 실재하는지 검증한다.

재무/경영 서비스라 '없는 숫자'를 지어내면 치명적이다. LLM 답변에서 의미 있는 수치를
뽑아 근거 문서(원문)에 그 숫자가 실제로 등장하는지 대조하고, 등장하지 않는 수치를
'미근거 수치(ungrounded)'로 플래그한다. 비파괴적(삭제하지 않고 표시) — 사람이 검토한다.

휴리스틱이므로 단위 변형(예: 10,599,000,000 ↔ $10.6B)은 미근거로 잡힐 수 있다(보수적:
거짓음성보다 거짓양성을 택해 검토를 유도). 인용 인덱스([문서 N])의 작은 수는 제외한다.
"""

from __future__ import annotations

import math
import re

# 콤마/소수 포함 숫자 토큰. 통화기호·% 는 경계로 둔다.
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")

# 가수(mantissa) 일치 허용오차 — 단위 환산/반올림 흡수, 우연 일치 억제.
_MANTISSA_TOL = 0.005


def _norm(tok: str) -> str:
    """콤마 제거 + 끝의 점 제거 → 비교용 숫자 문자열."""
    return tok.replace(",", "").rstrip(".")


def _mantissa(x: float) -> float:
    """x(>0)의 10의 거듭제곱을 제거한 가수 ∈ [1,10). 단위 환산 무시 비교용.

    예: 403.19 · 40,319,000,000 → 모두 ≈4.0319. 반올림(46.988→46.99)은 허용오차로 흡수.
    """
    return x / (10 ** math.floor(math.log10(x)))


def _floats(s: str) -> list[float]:
    """문자열에서 양수 실수 목록을 추출(콤마 정규화)."""
    out: list[float] = []
    for m in _NUM.findall(s):
        try:
            v = float(_norm(m))
        except ValueError:
            continue
        if v > 0:
            out.append(v)
    return out


def extract_numbers(text: str) -> list[str]:
    """텍스트에서 의미 있는 수치(정규화 문자열)를 등장 순서로 추출.

    한 자리(문서 인덱스 등)는 제외하고, 2자리 이상 또는 소수만 대상으로 한다.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _NUM.findall(text or ""):
        n = _norm(m)
        digits = n.replace(".", "")
        if len(digits) < 2:  # 1자리(예: [문서 1])는 잡지 않음
            continue
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def ungrounded_numbers(text: str, source_texts: list[str], *,
                       mantissa_fallback: bool = True) -> list[str]:
    """답변의 수치 중 근거 문서 원문에 등장하지 않는 것을 반환.

    1) 직접 매칭: 콤마 정규화 후 부분문자열로 등장하는가(연도·날짜·표기 그대로).
    2) 가수 매칭(폴백): 원문 어느 수치와 10의 거듭제곱·반올림을 무시하고 같은가
       (예: 원문 40,319,000,000 → 답변 403.19억/40.3B). 단위 환산·반올림을 흡수하되
       허용오차(0.5%)로 우연 일치를 억제해 진짜 환각은 계속 잡는다.

    mantissa_fallback=False 는 1)만 쓴다 — 대조 문서가 많아 수치가 수백 개면
    가수 공간([1,10))이 우연 일치로 채워져 폴백이 무력화되므로, 넓은 문서 집합
    (에이전트 답변 검증 등)에는 strict 매칭이 맞다.
    """
    src = _norm(" ".join(t for t in source_texts if t))
    src_mant = [_mantissa(v) for v in _floats(src)] if mantissa_fallback else []
    bad: list[str] = []
    for n in extract_numbers(text):
        if n in src:
            continue
        try:
            m = _mantissa(float(n))
        except (ValueError, OverflowError):
            bad.append(n)
            continue
        if any(abs(m - sm) <= _MANTISSA_TOL * sm for sm in src_mant):
            continue  # 단위 환산/반올림 — 같은 수치로 인정
        bad.append(n)
    return bad


def check(text: str, source_texts: list[str], *, mantissa_fallback: bool = True) -> dict:
    """수치 근거 검증 결과: {numbersGrounded, ungroundedNumbers}."""
    bad = ungrounded_numbers(text, source_texts, mantissa_fallback=mantissa_fallback)
    return {"numbersGrounded": not bad, "ungroundedNumbers": bad}


def caveat_line(ungrounded: list[str]) -> str:
    """미근거 수치가 있을 때 답변에 덧붙일 경고 문구."""
    if not ungrounded:
        return ""
    nums = ", ".join(ungrounded[:8])
    return f"\n\n※ 다음 수치는 제공된 문서에서 그대로 확인되지 않아 검토가 필요합니다: {nums}"
