"""사용자 토큰 인증 + admin/viewer 권한.

config.DATA_DIR/users.yaml 에 사용자를 적으면 인증이 켜진다. 파일이 없거나
비어 있으면 인증이 꺼져 있다고 보고 모든 요청을 admin 으로 취급한다 — 기존
배포(로컬/Docker)를 깨지 않기 위한 옵트인이며, weekly-report-harness 와
동일한 관례다. main.py 의 미들웨어가 GET 이 아닌 모든 요청에 대해 이 모듈로
인증·권한을 검사한다.
"""

from __future__ import annotations

import secrets
import threading
from pathlib import Path
from typing import Any

import yaml

from . import config

ROLES = ("admin", "viewer")

_lock = threading.Lock()

DISABLED_USER = {"name": "(인증 비활성)", "role": "admin"}


def _path() -> Path:
    return config.DATA_DIR / "users.yaml"


def _load() -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("users") or []


def _save(users: list[dict[str, Any]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump({"users": users}, f, allow_unicode=True, sort_keys=False)


def enabled() -> bool:
    """users.yaml 에 사용자가 하나라도 있으면 인증 활성."""
    return len(_load()) > 0


def authenticate(token: str | None) -> dict[str, Any] | None:
    """토큰으로 사용자를 찾는다. 인증이 꺼져 있으면 합성 admin 을 돌려준다."""
    users = _load()
    if not users:
        return dict(DISABLED_USER)
    if not token:
        return None
    for u in users:
        if u.get("token") == token:
            return {"name": u["name"], "role": u["role"]}
    return None


def list_users() -> list[dict[str, Any]]:
    return [{"name": u["name"], "role": u["role"], "token": u["token"]} for u in _load()]


def create_user(name: str, role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"잘못된 역할: {role} (허용: {', '.join(ROLES)})")
    name = name.strip()
    if not name:
        raise ValueError("이름이 비어 있습니다.")
    with _lock:
        users = _load()
        if any(u["name"] == name for u in users):
            raise ValueError(f"이미 있는 이름: {name}")
        token = secrets.token_urlsafe(24)
        users.append({"name": name, "role": role, "token": token})
        _save(users)
    return {"name": name, "role": role, "token": token}


def delete_user(name: str) -> None:
    with _lock:
        users = _load()
        remaining = [u for u in users if u["name"] != name]
        if len(remaining) == len(users):
            raise KeyError(name)
        _save(remaining)
