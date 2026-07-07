"""문서 이미지 OCR — 스캔 PDF·문서 내장 이미지의 텍스트 회수.

RapidOCR(PP-OCR 계열, onnxruntime 로컬 추론)로 이미지에서 텍스트를 뽑는다.
외부 API 호출이 없어 데이터 유출이 없다(온프렘/DRM 문서 보안 요건).
선택 의존성(extras: ocr) — 미설치·비활성이면 available()=False 가 되고
호출부(pdftext/officetext)는 이미지 텍스트 없이 기존 추출 결과만 쓴다.

한국어 주의: rapidocr 기본 인식 모델은 중·영문이다. 한국어 이미지 OCR 품질이
필요하면 PP-OCR korean 인식 모델(.onnx)을 받아 MI_OCR_REC_MODEL 에 경로를 준다.

비용 특성: 페이지/이미지당 수백 ms(CPU). 호출부가 페이지·이미지 수를 상한으로
묶는다. 끄기: MI_OCR=0 (설치돼 있어도 비활성).
"""

from __future__ import annotations

import os
import threading

_engine = None
_unavailable = False
_lock = threading.Lock()


def enabled() -> bool:
    """환경변수 스위치(기본 켜짐 — 설치 자체가 opt-in 이므로). MI_OCR=0 으로 끈다."""
    return os.getenv("MI_OCR", "1").strip().lower() not in ("0", "false", "no", "off")


def _get():
    """RapidOCR 엔진 싱글턴(최초 호출 시 모델 로드). 미설치/실패 시 None."""
    global _engine, _unavailable
    if _engine is not None:
        return _engine
    if _unavailable:
        return None
    with _lock:
        if _engine is not None:
            return _engine
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415

            kwargs = {}
            rec = os.getenv("MI_OCR_REC_MODEL", "").strip()
            if rec:  # 한국어 등 언어별 인식 모델 교체
                kwargs["rec_model_path"] = rec
            _engine = RapidOCR(**kwargs)
        except Exception:  # 미설치/모델 로드 실패 — 기능만 비활성, 추출은 계속
            _unavailable = True
            return None
    return _engine


def available() -> bool:
    """실제로 OCR 을 쓸 수 있는 상태(켜짐 + 엔진 로드 가능)."""
    return enabled() and _get() is not None


def ocr_bytes(data: bytes) -> str | None:
    """이미지 바이트(png/jpeg 등)에서 텍스트를 뽑는다. 비활성/실패/없음 → None."""
    if not data or not enabled():
        return None
    eng = _get()
    if eng is None:
        return None
    try:
        result, _ = eng(data)
        if not result:
            return None
        lines = [str(r[1]).strip() for r in result if len(r) > 1 and str(r[1]).strip()]
        return "\n".join(lines) or None
    except Exception:
        return None


def reset_for_test() -> None:
    """테스트용: 엔진 캐시 초기화(환경변수 변경 후 재평가)."""
    global _engine, _unavailable
    _engine = None
    _unavailable = False
