"""COM 인제스트 워커 (Windows 실행).

사용 예 (Windows, DRM 클라이언트 + MS Office 설치 환경):
    python -m tools.com_ingest.worker "C:\\\\reports\\\\analysis.docx" --backend http://mi-host:8000
    python -m tools.com_ingest.worker "C:\\\\reports" --topic HBM      # 폴더 일괄

추출(=DRM 해제 상태의 평문)을 백엔드 /collection/ingest 로 등록한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .extractors import SUPPORTED_EXTENSIONS, AppFactory, extract_text

# 페이로드 한 건을 백엔드로 보내는 콜러블. 테스트에서 가짜로 대체한다.
Poster = Callable[[str, dict[str, Any]], Any]


def _httpx_poster(backend_url: str, payload: dict[str, Any]) -> Any:
    import httpx  # 지연 import: 테스트는 가짜 poster 를 쓰므로 불필요

    resp = httpx.post(f"{backend_url.rstrip('/')}/collection/ingest", json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def build_payload(path: str, text: str, topic: str | None = None) -> dict[str, Any]:
    p = Path(path)
    return {
        "title": p.stem,
        "text": text,
        "topic": topic,
        "original_filename": p.name,
    }


def ingest_file(path: str, backend_url: str, *, topic: str | None = None,
                extract: Callable[[str], str] = extract_text,
                poster: Poster | None = None,
                factories: dict[str, AppFactory] | None = None) -> dict[str, Any]:
    """파일 하나를 추출→등록. extract/poster 주입으로 테스트 가능."""
    text = extract(path) if factories is None else extract_text(path, factories)
    payload = build_payload(path, text, topic)
    post = poster or (lambda url, pl: _httpx_poster(url, pl))
    return post(backend_url, payload)


def collect_paths(target: str) -> list[str]:
    """파일이면 자기 자신, 폴더면 지원 확장자 파일들."""
    p = Path(target)
    if p.is_file():
        return [str(p)]
    if p.is_dir():
        return sorted(
            str(f) for f in p.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    raise FileNotFoundError(target)


def ingest_target(target: str, backend_url: str, *, topic: str | None = None,
                  poster: Poster | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in collect_paths(target):
        try:
            results.append(ingest_file(path, backend_url, topic=topic, poster=poster))
            print(f"[ok] {path}")
        except Exception as e:  # 한 파일 실패가 전체를 막지 않도록
            print(f"[fail] {path}: {e}")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MS Office COM 인제스트 워커 (Windows)")
    ap.add_argument("target", help="문서 파일 또는 폴더 경로")
    ap.add_argument("--backend", default="http://localhost:8000", help="백엔드 URL")
    ap.add_argument("--topic", default=None, help="주제 태그(선택)")
    args = ap.parse_args(argv)

    results = ingest_target(args.target, args.backend, topic=args.topic)
    print(f"\n총 {len(results)}건 등록 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
