"""문서 이미지 → 텍스트: 로컬 OCR + VLM 캡셔닝 2단 구조.

1단 OCR: RapidOCR(PP-OCR 계열, onnxruntime 로컬 추론)로 이미지의 글자를 뽑는다.
외부 API 호출이 없다. 선택 의존성(extras: ocr) — 미설치·비활성이면
available()=False 가 되고 해당 단계만 건너뛴다.

2단 VLM: OCR 로 글자가 거의 안 나오는 이미지(차트·다이어그램)는 OpenRouter 의
비전 모델(기본: 레포 기본 LLM 인 minimax/minimax-m3 — 이미지 입력 지원)로
내용을 요약시킨다. 외부 API 로 이미지가 전송되므로 opt-in(MI_VLM=1).

호출부(pdftext/officetext)는 image_text() 하나만 쓴다: OCR 우선, 빈약하면 VLM.

한국어 주의: rapidocr 기본 인식 모델은 중·영문이다. 한국어 이미지 OCR 품질이
필요하면 PP-OCR korean 인식 모델(.onnx)을 받아 MI_OCR_REC_MODEL 에 경로를 준다.

비용 특성: OCR 페이지/이미지당 수백 ms(CPU, 무료), VLM 이미지당 왕복 수 초·소액 과금.
호출부가 페이지·이미지 수를 상한으로 묶는다. 끄기: MI_OCR=0 / MI_VLM 미설정.
"""

from __future__ import annotations

import os
import threading

_engine = None
_unavailable = False
_lock = threading.Lock()
_http_client = None  # VLM 호출용 재사용 커넥션(keep-alive)

# OCR 결과가 이보다 짧으면 글자 없는 그림(차트·다이어그램)으로 보고 VLM 캡셔닝을 시도
_VLM_MIN_OCR_CHARS = 40
_VLM_MAX_TOKENS = 500
_VLM_PROMPT = (
    "이 이미지는 사내 문서에 포함된 그림이다. 차트/다이어그램/표라면 담긴 수치·추세·"
    "구조를 한국어로 간결히 요약하고, 보이는 텍스트는 그대로 옮겨라. 5문장 이내."
)


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


# ── VLM 캡셔닝 (OpenRouter 비전 모델, 기본 minimax-m3) ────────────────
def vlm_enabled() -> bool:
    """VLM 캡셔닝 opt-in 여부: MI_VLM=1 + OPENROUTER_API_KEY 필요.

    이미지가 외부 API 로 전송되므로 기본 꺼짐(명시적 opt-in).
    """
    on = os.getenv("MI_VLM", "").strip().lower() in ("1", "true", "yes", "on")
    return on and bool(os.getenv("OPENROUTER_API_KEY"))


def _vlm_model() -> str:
    """비전 모델명: MI_VLM_MODEL > OPENROUTER_MODEL(레포 기본 minimax-m3)."""
    from .gateway import DEFAULT_MODEL  # noqa: PLC0415

    return (os.getenv("MI_VLM_MODEL") or os.getenv("OPENROUTER_MODEL")
            or DEFAULT_MODEL).strip()


def _http():
    """VLM 호출용 httpx.Client 싱글턴 — 이미지마다 TLS 핸드셰이크 반복 제거."""
    global _http_client
    if _http_client is None:
        with _lock:
            if _http_client is None:
                import httpx  # noqa: PLC0415

                _http_client = httpx.Client(timeout=60.0)
    return _http_client


def _mime(data: bytes) -> str:
    """이미지 매직 바이트로 MIME 추정(data URL 용). 모르면 png 로 간주."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return "image/png"


def describe_bytes(data: bytes) -> str | None:
    """VLM 으로 이미지 내용을 한국어로 설명. 비활성/실패 → None(OCR 결과만 사용)."""
    if not data or not vlm_enabled():
        return None
    try:
        import base64  # noqa: PLC0415

        from .gateway import DEFAULT_BASE_URL, _custom_headers  # noqa: PLC0415

        base = (os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                   "Content-Type": "application/json", **_custom_headers()}
        url = f"data:{_mime(data)};base64,{base64.b64encode(data).decode()}"
        r = _http().post(f"{base}/chat/completions", headers=headers, json={
            "model": _vlm_model(),
            "max_tokens": _VLM_MAX_TOKENS,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": _VLM_PROMPT},
                {"type": "image_url", "image_url": {"url": url}},
            ]}],
        })
        r.raise_for_status()
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
        return text or None
    except Exception:  # 네트워크/모델 오류 — 캡셔닝만 생략, 추출은 계속
        return None


def active() -> bool:
    """이미지에서 텍스트를 얻을 수단이 하나라도 있는가(OCR 또는 VLM)."""
    return available() or vlm_enabled()


def image_text(data: bytes) -> str | None:
    """이미지 → 텍스트(호출부 단일 진입점).

    OCR 우선(무료·로컬), 글자가 빈약하면 차트·다이어그램으로 보고 VLM 캡셔닝으로
    보완한다. 둘 다 없으면 None.
    """
    ocr = ocr_bytes(data)
    if ocr and len(ocr) >= _VLM_MIN_OCR_CHARS:
        return ocr
    caption = describe_bytes(data)
    if caption and ocr:
        return f"{ocr}\n{caption}"
    return caption or ocr


def reset_for_test() -> None:
    """테스트용: 엔진·클라이언트 캐시 초기화(환경변수 변경 후 재평가)."""
    global _engine, _unavailable, _http_client
    _engine = None
    _unavailable = False
    _http_client = None
