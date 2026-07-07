"""COM 인제스트 워커 (Windows 실행).

사용 예 (Windows, DRM 클라이언트 + MS Office 설치 환경):
    python -m tools.com_ingest.worker "C:\\\\reports\\\\analysis.docx" --backend http://mi-host:8000
    python -m tools.com_ingest.worker "C:\\\\reports" --topic HBM      # 폴더 일괄

추출(=DRM 해제 상태의 평문)을 백엔드 /collection/ingest/batch 로 등록한다.

배치 성능 설계:
  - 확장자 타입별 Office 앱 1개를 배치 전체에서 재사용(파일마다 기동/종료 제거).
  - COM 은 만든 스레드에서만 쓴다(STA) → 타입별 전용 러너 스레드에서 앱 생성·추출.
  - 파일당 타임아웃: DRM 대화상자 등으로 행이 걸리면 앱을 버리고 재기동(배치 지속).
  - 추출 결과는 batch_size 건씩 묶어 한 번에 전송(임베딩·트랜잭션 일괄 처리).
  - (size, mtime) 매니페스트로 기수집 파일을 건너뛴다(재실행 멱등).
"""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from .extractors import (
    SUPPORTED_EXTENSIONS,
    AppFactory,
    BaseExtractor,
    extract_text,
    extractor_class,
)

# 페이로드 한 건을 백엔드로 보내는 콜러블. 테스트에서 가짜로 대체한다.
Poster = Callable[[str, dict[str, Any]], Any]
# 페이로드 여러 건을 한 번에 보내고 등록된 문서 목록을 돌려주는 콜러블.
BatchPoster = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]

DEFAULT_TIMEOUT = 120.0      # 파일당 추출 제한(초) — DRM 모달/행 방어
DEFAULT_RECYCLE_AFTER = 100  # N건마다 Office 앱 재기동(메모리 누적 방지)
DEFAULT_BATCH_SIZE = 16      # 백엔드 배치 전송 단위(임베딩 배치와 트랜잭션 상각)
MAX_BATCH_SIZE = 200         # 서버 IngestBatch(documents max_length=200)와 동기
DEFAULT_STATE_PATH = Path.home() / ".mi-com-ingest-state.json"


class ExtractTimeout(RuntimeError):
    """파일 추출이 제한 시간을 넘겼다(대개 DRM/변환 대화상자로 행)."""


def _co_initialize() -> None:
    if sys.platform == "win32":
        import pythoncom  # type: ignore  # noqa: PLC0415

        pythoncom.CoInitialize()


def _co_uninitialize() -> None:
    if sys.platform == "win32":
        import pythoncom  # type: ignore  # noqa: PLC0415

        pythoncom.CoUninitialize()


class ExtractorRunner:
    """추출기 하나를 전용 스레드(COM 아파트)에서 실행하고 파일당 타임아웃을 강제한다.

    COM 객체는 만든 스레드에서만 써야 하므로 앱 생성과 모든 추출을 한 스레드에서
    수행하고, 호출 스레드는 결과를 타임아웃으로 기다린다. 초과 시 스레드·앱을
    버리고 새로 시작한다(행 걸린 앱은 PID 를 알면 강제 종료, 모르면 경고만).
    """

    def __init__(self, cls: type[BaseExtractor], app_factory: AppFactory | None = None, *,
                 timeout: float = DEFAULT_TIMEOUT,
                 recycle_after: int = DEFAULT_RECYCLE_AFTER):
        self._cls = cls
        self._app_factory = app_factory
        self._timeout = timeout
        self._recycle_after = recycle_after
        self._pid: int | None = None
        self._start()

    def _start(self) -> None:
        self._jobs: queue.Queue[str | None] = queue.Queue()
        self._results: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop, args=(self._jobs, self._results), daemon=True
        )
        self._thread.start()

    def _loop(self, jobs: queue.Queue, results: queue.Queue) -> None:
        try:
            _co_initialize()
            with self._cls(self._app_factory) as ex:
                self._pid = ex.pid()
                done = 0
                while True:
                    path = jobs.get()
                    if path is None:
                        return
                    if done and done % self._recycle_after == 0:
                        try:
                            ex.restart()
                            self._pid = ex.pid()
                        except Exception:
                            pass  # 재기동 실패 → 다음 추출이 앱을 다시 띄운다
                    try:
                        results.put(("ok", ex.extract(path)))
                    except Exception as e:
                        results.put(("err", e))
                        # 실패한 파일이 앱 상태를 오염시켰을 수 있다(모달 직전 에러 등).
                        # 구버전의 '파일마다 종료' 의미론을 실패 시에만 복원해 연쇄 실패를 막는다.
                        try:
                            ex.restart()
                            self._pid = ex.pid()
                        except Exception:
                            pass  # 재기동 실패 → 다음 추출이 앱을 다시 띄운다
                    done += 1
        except Exception as e:
            # 앱 기동 자체가 실패(비 Windows, Office 미설치 등) — 잡마다 즉시 실패 응답
            while True:
                path = jobs.get()
                if path is None:
                    return
                results.put(("err", e))
        finally:
            _co_uninitialize()

    def extract(self, path: str) -> str:
        self._jobs.put(path)
        try:
            kind, val = self._results.get(timeout=self._timeout)
        except queue.Empty:
            self._abandon()
            raise ExtractTimeout(
                f"추출 {self._timeout:.0f}s 초과 (DRM 대화상자/행 의심): {path}"
            ) from None
        if kind == "err":
            raise val
        return val

    def _abandon(self) -> None:
        """행 걸린 스레드·앱을 버리고 새로 시작한다."""
        pid = self._pid
        self._jobs.put(None)  # 행이 풀리면 옛 스레드가 스스로 종료하도록
        if pid and sys.platform == "win32":
            # 해당 Office 프로세스만 강제 종료(사용자의 다른 Office 세션은 건드리지 않음)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, check=False,
            )
        else:
            print(f"[warn] 행 걸린 {self._cls.prog_id} 를 강제 종료할 수 없습니다"
                  f"(PID 미상) — 숨은 프로세스가 남을 수 있습니다.")
        self._start()

    def close(self) -> None:
        self._jobs.put(None)
        self._thread.join(timeout=10)


def _httpx_poster(backend_url: str, payload: dict[str, Any]) -> Any:
    import httpx  # 지연 import: 테스트는 가짜 poster 를 쓰므로 불필요

    resp = httpx.post(f"{backend_url.rstrip('/')}/collection/ingest", json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def _httpx_batch_poster(backend_url: str) -> tuple[BatchPoster, Callable[[], None]]:
    """배치 전송 poster 와 close 콜러블. 커넥션(keep-alive)을 배치 수명 동안 재사용한다."""
    import httpx  # 지연 import

    client = httpx.Client(base_url=backend_url.rstrip("/"), timeout=120.0)

    def post(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        r = client.post("/collection/ingest/batch", json={"documents": payloads})
        if r.status_code == 404:
            # 조용한 폴백 금지: 404 는 대개 구버전 백엔드 또는 잘못된 --backend URL.
            # 단건 경로로 몰래 격하하면 배치·서버 dedup 의미론을 잃고 오설정이 묻힌다.
            raise RuntimeError(
                "백엔드에 /collection/ingest/batch 가 없습니다 — "
                "백엔드를 업데이트하거나 --backend URL 을 확인하세요."
            )
        r.raise_for_status()
        return r.json().get("documents", [])

    return post, client.close


def _is_client_error(e: Exception) -> bool:
    """HTTP 4xx(페이로드 문제일 가능성) 여부 — 단건 격리 재시도 대상 판별."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    return status is not None and 400 <= int(status) < 500


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
    """파일 하나를 추출→등록(일회성). extract/poster 주입으로 테스트 가능."""
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


# ── 기수집 매니페스트 (재실행 멱등) ────────────────────────────────────
def _load_state(path: Path | None) -> dict[str, list[int]]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}  # 손상된 매니페스트는 무시하고 새로 만든다


def _save_state(path: Path, state: dict[str, list[int]]) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _file_sig(path: str) -> list[int]:
    st = Path(path).stat()
    return [st.st_size, int(st.st_mtime)]


def ingest_target(target: str, backend_url: str, *, topic: str | None = None,
                  poster: Poster | None = None,
                  batch_poster: BatchPoster | None = None,
                  batch_size: int = DEFAULT_BATCH_SIZE,
                  timeout: float = DEFAULT_TIMEOUT,
                  recycle_after: int = DEFAULT_RECYCLE_AFTER,
                  state_path: Path | None = None,
                  force: bool = False,
                  factories: dict[str, AppFactory] | None = None) -> list[dict[str, Any]]:
    """폴더/파일을 배치 인제스트한다. 한 파일 실패가 전체를 막지 않는다."""
    batch_size = max(1, min(batch_size, MAX_BATCH_SIZE))  # 서버 스키마 상한 준수
    # 매니페스트는 백엔드 URL 별로 네임스페이스한다 — 다른 백엔드로 전환해 재실행할 때
    # 이전 백엔드의 기록 때문에 전량 skip 되는 사고를 막는다.
    full_state = _load_state(state_path)
    if any(not isinstance(v, dict) for v in full_state.values()):
        full_state = {}  # 구형식(경로→sig 평면) 폐기 — 재전송은 서버 해시 dedup 이 막는다
    state = full_state.setdefault(backend_url.rstrip("/"), {})

    close_client: Callable[[], None] | None = None
    if batch_poster is None:
        if poster is not None:
            def batch_poster(payloads: list[dict[str, Any]], _p: Poster = poster
                             ) -> list[dict[str, Any]]:
                return [_p(backend_url, pl) for pl in payloads]
        else:
            batch_poster, close_client = _httpx_batch_poster(backend_url)

    results: list[dict[str, Any]] = []
    # (path, 스캔 시점 sig, payload). sig 를 추출 전에 고정해 두어야
    # 추출~flush 사이에 수정된 파일이 새 sig 로 기록돼 영구 skip 되는 일이 없다.
    pending: list[tuple[str, list[int], dict[str, Any]]] = []

    def record_ok(batch: list[tuple[str, list[int], dict[str, Any]]],
                  docs: list[dict[str, Any]]) -> None:
        results.extend(docs)
        for p, sig, _ in batch:
            print(f"[ok] {p}")
            state[p] = sig
        if state_path is not None:
            _save_state(state_path, full_state)

    def flush() -> None:
        if not pending:
            return
        batch = list(pending)
        pending.clear()
        try:
            record_ok(batch, batch_poster([pl for _, _, pl in batch]))
            return
        except Exception as e:
            if not _is_client_error(e):  # 서버/네트워크 장애 — 단건 재시도 무의미
                for p, _, _ in batch:
                    print(f"[fail] {p}: {e}")
                return
        # 4xx: 배치 안의 불량 페이로드 1건이 원인일 수 있다 → 단건으로 격리 재시도
        # ('한 파일 실패가 전체를 막지 않는다'를 전송 단계에도 적용).
        for item in batch:
            try:
                record_ok([item], batch_poster([item[2]]))
            except Exception as ee:
                print(f"[fail] {item[0]}: {ee}")

    runners: dict[type[BaseExtractor], ExtractorRunner] = {}
    try:
        for path in collect_paths(target):
            try:
                sig = _file_sig(path)
            except OSError as e:  # 스캔 후 삭제/이동된 파일 — 이 파일만 건너뜀
                print(f"[fail] {path}: {e}")
                continue
            if state_path is not None and not force and state.get(path) == sig:
                print(f"[skip] {path} (변경 없음)")
                continue
            try:
                cls = extractor_class(path)
                runner = runners.get(cls)
                if runner is None:
                    runner = runners[cls] = ExtractorRunner(
                        cls, (factories or {}).get(cls.prog_id),
                        timeout=timeout, recycle_after=recycle_after,
                    )
                text = runner.extract(path)
            except Exception as e:
                print(f"[fail] {path}: {e}")
                continue
            pending.append((path, sig, build_payload(path, text, topic)))
            if len(pending) >= batch_size:
                flush()
        flush()
    finally:
        for r in runners.values():
            r.close()
        if close_client is not None:
            close_client()
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MS Office COM 인제스트 워커 (Windows)")
    ap.add_argument("target", help="문서 파일 또는 폴더 경로")
    ap.add_argument("--backend", default="http://localhost:8000", help="백엔드 URL")
    ap.add_argument("--topic", default=None, help="주제 태그(선택)")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                    help="배치 전송 단위(기본 %(default)s건)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help="파일당 추출 제한 초(기본 %(default)s)")
    ap.add_argument("--state", default=str(DEFAULT_STATE_PATH),
                    help="기수집 매니페스트 경로. '' 이면 비활성(전부 재인제스트)")
    ap.add_argument("--force", action="store_true",
                    help="매니페스트를 무시하고 전부 다시 인제스트(매니페스트는 갱신)")
    args = ap.parse_args(argv)

    results = ingest_target(
        args.target, args.backend, topic=args.topic,
        batch_size=args.batch_size, timeout=args.timeout,
        state_path=Path(args.state) if args.state else None, force=args.force,
    )
    print(f"\n총 {len(results)}건 등록 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
