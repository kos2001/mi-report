"""로컬 의미 임베딩(fastembed) — RAG 하이브리드 검색용.

fastembed(ONNX, 로컬)로 텍스트를 임베딩한다. 외부 API 호출이 없어 데이터 유출이 없다
(사내/온프렘 보안 요건 충족). 미설치 또는 비활성 시 available()=False 가 되어
호출부가 BM25 검색으로 우아하게 폴백한다.

참조 설계: gitspace/lsi_error_analyzer (FastEmbed 로컬 임베딩 + RRF 하이브리드,
기본 모델 paraphrase-multilingual-MiniLM-L12-v2, e5 계열 query/passage 프리픽스).

활성화 조건: 환경변수 MI_EMBEDDINGS=1 + fastembed 설치(extras: embeddings).
"""

from __future__ import annotations

import os
import threading

# 코드 기본값(로컬 fastembed): 한국어 포함 다국어, 384-dim, ONNX.
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# OpenRouter 백엔드 기본 모델(다국어·한국어 강함, 1024-dim).
DEFAULT_OPENROUTER_EMBED_MODEL = "baai/bge-m3"

_embedder = None
_unavailable = False
_lock = threading.Lock()


def enabled() -> bool:
    """환경변수로 임베딩 기능을 켰는지(기본 꺼짐 — 테스트·기본 설치는 BM25만)."""
    return os.getenv("MI_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes", "on")


def backend() -> str:
    """임베딩 백엔드: 'fastembed'(로컬, 기본) | 'openrouter'(API)."""
    return (os.getenv("MI_EMBED_BACKEND") or "fastembed").strip().lower()


def model_name() -> str:
    """현재 임베딩 모델명(env MI_EMBED_MODEL). 백엔드별 기본값 적용."""
    env = (os.getenv("MI_EMBED_MODEL") or "").strip()
    if env:
        return env
    return DEFAULT_OPENROUTER_EMBED_MODEL if backend() == "openrouter" else DEFAULT_EMBED_MODEL


def _get():
    """로컬 임베더 싱글턴(최초 호출 시 모델 로드/다운로드). 실패 시 None."""
    global _embedder, _unavailable
    if _embedder is not None:
        return _embedder
    if _unavailable:
        return None
    with _lock:
        if _embedder is not None:
            return _embedder
        try:
            from fastembed import TextEmbedding

            _embedder = TextEmbedding(model_name=model_name())
        except Exception:  # 미설치/다운로드 실패 등 — 기능만 비활성, 앱은 계속 동작
            _unavailable = True
            return None
    return _embedder


def active() -> bool:
    """실제로 임베딩을 쓸 수 있는 상태(켜짐 + 백엔드 사용 가능)."""
    if not enabled():
        return False
    if backend() == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    return _get() is not None


def _prefixed(texts: list[str], is_query: bool) -> list[str]:
    """e5 계열은 query:/passage: 프리픽스를 요구한다(다른 모델은 원문 그대로)."""
    if "e5" in model_name().lower():
        tag = "query: " if is_query else "passage: "
        return [tag + t for t in texts]
    return texts


def _parse_embed_payload(payload: dict) -> list[list[float]]:
    """OpenRouter /embeddings 응답(data[].embedding, index)을 index 순 벡터 목록으로."""
    data = sorted(payload.get("data", []), key=lambda x: x.get("index", 0))
    return [d["embedding"] for d in data]


def _embed_openrouter(texts: list[str], is_query: bool):
    """OpenRouter /embeddings 로 임베딩(배치). 사내 식별 헤더도 첨부. 키 없으면 None."""
    import httpx
    import numpy as np

    from .gateway import DEFAULT_BASE_URL, _custom_headers

    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    base = (os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               **_custom_headers()}
    prefixed = _prefixed(texts, is_query)
    out: list[list[float]] = []
    with httpx.Client(timeout=60.0) as c:
        for i in range(0, len(prefixed), 64):  # 배치 64
            r = c.post(f"{base}/embeddings", headers=headers,
                       json={"model": model_name(), "input": prefixed[i:i + 64]})
            r.raise_for_status()
            out.extend(_parse_embed_payload(r.json()))
    return np.asarray(out, dtype="float32") if out else None


def embed(texts: list[str], *, is_query: bool = False):
    """텍스트들을 임베딩해 numpy 배열 (n, dim) 반환. 사용 불가/실패 시 None.

    어떤 예외(네트워크·HTTP·모델 로드 실패)도 삼켜 None 을 돌려준다 → 호출부가
    BM25(어휘) 검색으로 폴백한다(임베딩 장애가 검색·인입을 막지 않음).
    """
    if not texts:
        return None
    try:
        if backend() == "openrouter":
            return _embed_openrouter(list(texts), is_query)
        emb = _get()
        if emb is None:
            return None
        import numpy as np

        vecs = list(emb.embed(_prefixed(list(texts), is_query)))
        return np.asarray(vecs, dtype="float32")
    except Exception:
        return None


def reset_for_test() -> None:
    """테스트에서 모델 캐시 상태를 초기화(환경변수 변경 후 재평가용)."""
    global _embedder, _unavailable
    _embedder = None
    _unavailable = False
