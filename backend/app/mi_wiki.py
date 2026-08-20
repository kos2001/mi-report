"""MI Report용 LLM Wiki 계층.

원문 코퍼스/검색 저장소를 대체하지 않는다. 생성에 성공한 주차별 다이제스트를
출처 메타데이터와 함께 Markdown으로 누적하고, 다음 생성 시 최근 주차의 정제된
맥락을 제공한다. Wiki 갱신 실패는 주 생성 흐름을 막지 않는 best-effort 경로다.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date
from pathlib import Path
from typing import Any

from . import config

_LOCK = threading.Lock()
_STATE_FILE = ".mi-wiki-state.json"


def enabled() -> bool:
    return os.getenv("MI_WIKI_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def wiki_path() -> Path:
    configured = (os.getenv("MI_WIKI_PATH") or "").strip().strip('"').strip("'")
    return Path(configured).expanduser() if configured else config.DATA_DIR / "wiki"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", value.strip().lower()).strip("-")
    return slug or "untagged"


def _week_key(label: str) -> str:
    match = re.fullmatch(r"(\d{4})년\s*(\d{1,2})주차", (label or "").strip())
    if match:
        return f"{int(match.group(1)):04d}-W{int(match.group(2)):02d}"
    iso = date.today().isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "weeks": {}}


def _load_state(root: Path) -> dict[str, Any]:
    path = root / _STATE_FILE
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    return data if isinstance(data, dict) and isinstance(data.get("weeks"), dict) else _empty_state()


def init_wiki() -> Path | None:
    """Wiki 기본 구조를 멱등 생성한다. 비활성화 시 None."""
    if not enabled():
        return None
    root = wiki_path()
    with _LOCK:
        for folder in ("weekly", "concepts", "entities", "comparisons", "queries", "raw"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        schema = root / "SCHEMA.md"
        if not schema.exists():
            _atomic_write(schema, """# MI Wiki Schema

## Domain
반도체·IT 시장 인텔리전스의 주차별 변화, 기업, 제품, 수요 및 리스크를 추적한다.

## Rules
- 원문 코퍼스가 사실의 원장이다. Wiki는 생성된 정제 지식 계층이다.
- 수치와 주장은 각 주차 페이지의 출처·발행일로 추적 가능해야 한다.
- 같은 ISO 주차는 교체하고, 다른 주차는 누적한다.
- 새 정보가 기존 결론과 다르면 이전 결론을 삭제하지 말고 주차별 차이로 남긴다.
- 최종 보고서의 수치와 인용은 반드시 원문 코퍼스로 다시 검증한다.
""")
        state_path = root / _STATE_FILE
        if not state_path.exists():
            _atomic_write(state_path, json.dumps(_empty_state(), ensure_ascii=False, indent=2))
        _render_meta(root, _load_state(root))
    return root


def init_wiki_safe() -> None:
    """Wiki 초기화 실패가 애플리케이션 시작을 막지 않게 한다."""
    try:
        init_wiki()
    except Exception:
        pass


def _render_week(entry: dict[str, Any]) -> str:
    lines = [
        "---",
        f"title: {entry['week']}",
        f"week_key: {entry['key']}",
        f"updated: {entry['updated']}",
        "type: weekly-digest",
        "---",
        "",
        f"# {entry['week']} MI 다이제스트",
        "",
        f"**기간**: {entry.get('period') or '—'}  ",
        f"**생성 시각**: {entry['updated']}  ",
        f"**입력 문서 수**: {entry.get('sourceDocCount', 0)}",
        "",
    ]
    for item in entry.get("items", []):
        tags = ", ".join(f"[[concepts/{_slug(t)}|{t}]]" for t in item.get("tags", []) if t)
        lines.extend([
            f"## {item.get('title') or '제목 없음'}",
            "",
            item.get("summary") or "",
            "",
            f"- 출처: {item.get('source') or '미상'}",
            f"- 발행일: {item.get('publishedAt') or '미상'}",
            f"- 영향도: {item.get('impact') or 'medium'}",
            f"- S.LSI 연관성: {item.get('slsiRelevance') or '—'}",
            f"- 수요 영향: {item.get('demandImpact') or '—'}",
            f"- 리스크: {item.get('risk') or '—'}",
            f"- 태그: {tags or '—'}",
            "",
        ])
    unsupported = entry.get("unsupportedClaims") or []
    if unsupported:
        lines.extend(["## 검토 필요 주장", ""] + [f"- {claim}" for claim in unsupported] + [""])
    return "\n".join(lines).rstrip() + "\n"


def _render_meta(root: Path, state: dict[str, Any]) -> None:
    weeks = sorted(state.get("weeks", {}).values(), key=lambda x: x["key"], reverse=True)
    index = [
        "# MI Wiki Index",
        "",
        "> 원문 코퍼스를 대체하지 않는 주차별 정제 지식 계층.",
        f"> 총 {len(weeks)}주차",
        "",
        "## Weekly Digests",
        "",
    ]
    index += [f"- [[weekly/{w['key']}|{w['week']}]] — {len(w.get('items', []))}개 항목" for w in weeks]
    index += ["", "## Concepts", ""]

    concepts: dict[str, dict[str, Any]] = {}
    for week in reversed(weeks):
        for item in week.get("items", []):
            for tag in item.get("tags", []):
                if not tag:
                    continue
                concept = concepts.setdefault(_slug(tag), {"label": tag, "entries": []})
                concept["entries"].append((week, item))
    expected_concept_files = {f"{slug}.md" for slug in concepts}
    for existing in (root / "concepts").glob("*.md"):
        if existing.name not in expected_concept_files:
            existing.unlink()
    for slug, concept in sorted(concepts.items(), key=lambda pair: pair[1]["label"]):
        index.append(f"- [[concepts/{slug}|{concept['label']}]]")
        body = [
            "---", f"title: {concept['label']}", "type: concept", "---", "",
            f"# {concept['label']}", "", "## 주차별 관측", "",
        ]
        for week, item in reversed(concept["entries"]):
            body.extend([
                f"### [[weekly/{week['key']}|{week['week']}]] — {item.get('title') or '제목 없음'}",
                "", item.get("summary") or "", "",
                f"- 출처: {item.get('source') or '미상'} / {item.get('publishedAt') or '미상'}",
                f"- 수요 영향: {item.get('demandImpact') or '—'}",
                f"- 리스크: {item.get('risk') or '—'}", "",
            ])
        _atomic_write(root / "concepts" / f"{slug}.md", "\n".join(body).rstrip() + "\n")

    _atomic_write(root / "index.md", "\n".join(index).rstrip() + "\n")
    log = ["# MI Wiki Log", ""]
    log += [f"## [{w['updated']}] digest | {w['week']}\n- {len(w.get('items', []))}개 항목으로 갱신" for w in reversed(weeks)]
    _atomic_write(root / "log.md", "\n\n".join(log).rstrip() + "\n")


def update_digest(payload: dict[str, Any]) -> Path | None:
    """성공한 다이제스트를 같은 주차는 교체, 다른 주차는 누적한다."""
    root = init_wiki()
    if root is None:
        return None
    week = str(payload.get("week") or "").strip()
    key = _week_key(week)
    entry = {
        "key": key,
        "week": week or key,
        "updated": str(payload.get("generatedAt") or date.today().isoformat()),
        "period": payload.get("period") or "",
        "sourceDocCount": payload.get("sourceDocCount") or 0,
        "items": payload.get("items") or [],
        "unsupportedClaims": payload.get("unsupportedClaims") or [],
    }
    with _LOCK:
        state = _load_state(root)
        state["weeks"][key] = entry
        _atomic_write(root / "weekly" / f"{key}.md", _render_week(entry))
        _atomic_write(root / _STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))
        _render_meta(root, state)
    return root / "weekly" / f"{key}.md"


def update_digest_safe(payload: dict[str, Any]) -> None:
    try:
        update_digest(payload)
    except Exception:
        pass


def digest_context(*, current_week: str, max_chars: int = 6000, max_weeks: int = 4) -> str:
    """다음 다이제스트 생성용 최근 Wiki 맥락. 현재 주차는 재생성 오염 방지를 위해 제외."""
    if not enabled():
        return ""
    root = wiki_path()
    state = _load_state(root)
    current_key = _week_key(current_week)
    weeks = [w for key, w in state.get("weeks", {}).items() if key != current_key]
    weeks.sort(key=lambda x: x["key"], reverse=True)
    blocks: list[str] = []
    for week in weeks[:max_weeks]:
        lines = [f"[{week['week']}] 기간: {week.get('period') or '—'}"]
        for item in week.get("items", []):
            lines.append(
                f"- {item.get('title', '')}: {item.get('summary', '')} "
                f"| 수요: {item.get('demandImpact', '')} | 리스크: {item.get('risk', '')} "
                f"| 출처: {item.get('source', '')} ({item.get('publishedAt', '')})"
            )
        blocks.append("\n".join(lines))
    text = "\n\n".join(blocks)
    return text[:max_chars]
