"""환각 방어 — 생성물의 수치가 근거 문서에 실재하는지 검증한다.

재무/경영 서비스라 '없는 숫자'를 지어내면 치명적이다. LLM 답변에서 의미 있는 수치를
뽑아 근거 문서(원문)에 그 숫자가 실제로 등장하는지 대조하고, 등장하지 않는 수치를
'미근거 수치(ungrounded)'로 플래그한다. 비파괴적(삭제하지 않고 표시) — 사람이 검토한다.

휴리스틱이므로 단위 변형(예: 10,599,000,000 ↔ $10.6B)은 미근거로 잡힐 수 있다(보수적:
거짓음성보다 거짓양성을 택해 검토를 유도). 인용 인덱스([문서 N])의 작은 수는 제외한다.
"""

from __future__ import annotations

import re

# 콤마/소수 포함 숫자 토큰. 통화기호·% 는 경계로 둔다.
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(tok: str) -> str:
    """콤마 제거 + 끝의 점 제거 → 비교용 숫자 문자열."""
    return tok.replace(",", "").rstrip(".")


def _sig(tok: str) -> str:
    """유효숫자열 — 콤마·소수점·앞뒤 0 제거. 단위 재환산/반올림 비교용.

    예: 61,157(백만) · 61.157(십억) · 61,157,000,000 → 모두 '61157'.
    """
    return tok.replace(",", "").replace(".", "").strip("0")


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


def ungrounded_numbers(text: str, source_texts: list[str]) -> list[str]:
    """답변의 수치 중 근거 문서 원문에 등장하지 않는 것을 반환.

    1) 직접 매칭: 콤마 정규화 후 부분문자열로 등장하는가.
    2) 재환산 매칭(폴백): 유효숫자열이 원문 어느 수치의 유효숫자열과 접두 관계인가
       (예: 원문 61,157 → 답변 61.157B/61.1B). 짧은 수(<3자리)는 폴백을 쓰지 않아
       우연한 자릿수 일치로 환각을 놓치지 않는다.
    """
    src = _norm(" ".join(t for t in source_texts if t))
    src_sigs = [s for s in (_sig(m) for m in _NUM.findall(src)) if len(s) >= 3]
    bad: list[str] = []
    for n in extract_numbers(text):
        if n in src:
            continue
        nsig = _sig(n)
        if len(nsig) >= 3 and any(s.startswith(nsig) or nsig.startswith(s) for s in src_sigs):
            continue  # 단위 재환산/반올림 — 같은 수치로 인정
        bad.append(n)
    return bad


def check(text: str, source_texts: list[str]) -> dict:
    """수치 근거 검증 결과: {numbersGrounded, ungroundedNumbers}."""
    bad = ungrounded_numbers(text, source_texts)
    return {"numbersGrounded": not bad, "ungroundedNumbers": bad}


def caveat_line(ungrounded: list[str]) -> str:
    """미근거 수치가 있을 때 답변에 덧붙일 경고 문구."""
    if not ungrounded:
        return ""
    nums = ", ".join(ungrounded[:8])
    return f"\n\n※ 다음 수치는 제공된 문서에서 그대로 확인되지 않아 검토가 필요합니다: {nums}"
