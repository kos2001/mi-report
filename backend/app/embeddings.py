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

# 한국어 포함 다국어, 384-dim, 로컬 ONNX. 교체 시 e5 계열은 프리픽스 자동 적용.
MODEL_NAME = os.getenv(
    "MI_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

_embedder = None
_unavailable = False
_lock = threading.Lock()


def enabled() -> bool:
    """환경변수로 임베딩 기능을 켰는지(기본 꺼짐 — 테스트·기본 설치는 BM25만)."""
    return os.getenv("MI_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes", "on")


def _get():
    """임베더 싱글턴(최초 호출 시 모델 로드/다운로드). 실패 시 None 으로 비활성화."""
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

            _embedder = TextEmbedding(model_name=MODEL_NAME)
        except Exception:  # 미설치/다운로드 실패 등 — 기능만 비활성, 앱은 계속 동작
            _unavailable = True
            return None
    return _embedder


def active() -> bool:
    """실제로 임베딩을 쓸 수 있는 상태(켜짐 + 로드 가능)."""
    return enabled() and _get() is not None


def _prefixed(texts: list[str], is_query: bool) -> list[str]:
    """e5 계열은 query:/passage: 프리픽스를 요구한다(다른 모델은 원문 그대로)."""
    if "e5" in MODEL_NAME.lower():
        tag = "query: " if is_query else "passage: "
        return [tag + t for t in texts]
    return texts


def embed(texts: list[str], *, is_query: bool = False):
    """텍스트들을 임베딩해 numpy 배열 (n, dim) 반환. 사용 불가 시 None."""
    if not texts:
        return None
    emb = _get()
    if emb is None:
        return None
    import numpy as np

    vecs = list(emb.embed(_prefixed(list(texts), is_query)))
    return np.asarray(vecs, dtype="float32")


def reset_for_test() -> None:
    """테스트에서 모델 캐시 상태를 초기화(환경변수 변경 후 재평가용)."""
    global _embedder, _unavailable
    _embedder = None
    _unavailable = False
