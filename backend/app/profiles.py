"""프로파일 로더.

  - 프로파일 = profiles/<name>/ 디렉토리
  - config.yaml: model.default / model.provider / model.base_url / providers
  - .env: 시크릿 (key_env 가 가리키는 변수)
  - active_profile 파일: 활성 프로파일 이름
  - 이름 규칙: ^[a-z0-9_][a-z0-9_-]{0,63}$
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import ACTIVE_PROFILE_FILE, DEFAULT_PROFILE, PROFILES_DIR

# profiles.ts 의 PROFILE_NAME_RE 와 동일
PROFILE_NAME_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}$")
PROFILE_NAME_ERROR = (
    "Profile names may contain lowercase letters, numbers, underscores, and "
    "hyphens, and cannot start with a hyphen."
)


def is_valid_profile_name(name: object) -> bool:
    return isinstance(name, str) and bool(PROFILE_NAME_RE.match(name))


@dataclass
class ProviderConfig:
    """OpenAI 호환 provider 연결 정보 (OpenRouter 등)."""

    name: str
    type: str
    base_url: str
    key_env: str
    extra_headers: dict[str, str]

    def resolve_api_key(self) -> str | None:
        """key_env 가 가리키는 환경변수에서 API 키를 읽는다."""
        return os.environ.get(self.key_env) if self.key_env else None


@dataclass
class Profile:
    name: str
    path: Path
    model: str
    provider_name: str
    base_url: str
    providers: dict[str, ProviderConfig]
    has_env: bool
    has_soul: bool

    def active_provider(self) -> ProviderConfig:
        """model.provider 가 가리키는 provider 를 반환.

        명시적 provider 정의가 없으면 model.base_url 기준으로 합성한다
        (key_env 기본값: OPENROUTER_API_KEY)."""
        if self.provider_name in self.providers:
            return self.providers[self.provider_name]
        return ProviderConfig(
            name=self.provider_name or "openrouter",
            type="openai-compatible",
            base_url=self.base_url,
            key_env="OPENROUTER_API_KEY",
            extra_headers={},
        )


def get_active_profile_name() -> str:
    """활성 프로파일 이름 결정. 우선순위: 환경변수 > active_profile 파일 > DEFAULT."""
    env = os.environ.get("MI_ACTIVE_PROFILE")
    if env and is_valid_profile_name(env):
        return env
    try:
        name = ACTIVE_PROFILE_FILE.read_text(encoding="utf-8").strip()
        if name and is_valid_profile_name(name):
            return name
    except OSError:
        pass
    return DEFAULT_PROFILE


def _load_dotenv(env_path: Path) -> None:
    """프로파일 .env 를 os.environ 에 로드 (이미 설정된 값은 덮어쓰지 않음)."""
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


def _parse_providers(raw: dict[str, Any]) -> dict[str, ProviderConfig]:
    providers: dict[str, ProviderConfig] = {}
    for key, val in (raw or {}).items():
        if not isinstance(val, dict):
            continue
        providers[key] = ProviderConfig(
            name=key,
            type=str(val.get("type", "openai-compatible")),
            base_url=str(val.get("base_url", "")),
            key_env=str(val.get("key_env", "")),
            extra_headers={
                str(k): str(v) for k, v in (val.get("extra_headers") or {}).items()
            },
        )
    return providers


def load_profile(name: str | None = None) -> Profile:
    """프로파일을 로드하고 그 .env 를 환경에 적용한다."""
    name = name or get_active_profile_name()
    if not is_valid_profile_name(name):
        raise ValueError(PROFILE_NAME_ERROR)

    profile_path = PROFILES_DIR / name
    config_file = profile_path / "config.yaml"
    if not config_file.is_file():
        raise FileNotFoundError(f"프로파일 '{name}' 의 config.yaml 을 찾을 수 없습니다: {config_file}")

    env_file = profile_path / ".env"
    has_env = env_file.is_file()
    if has_env:
        _load_dotenv(env_file)

    data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    model_cfg = data.get("model", {}) or {}

    return Profile(
        name=name,
        path=profile_path,
        model=str(model_cfg.get("default", "")),
        provider_name=str(model_cfg.get("provider", "")),
        base_url=str(model_cfg.get("base_url", "")),
        providers=_parse_providers(data.get("providers", {})),
        has_env=has_env,
        has_soul=(profile_path / "SOUL.md").is_file(),
    )


def list_profiles() -> list[dict[str, Any]]:
    """profiles/ 아래의 모든 프로파일을 요약(ProfileInfo 형태)으로 반환."""
    active = get_active_profile_name()
    out: list[dict[str, Any]] = []
    if not PROFILES_DIR.is_dir():
        return out
    for entry in sorted(PROFILES_DIR.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if not is_valid_profile_name(entry.name):
            continue
        try:
            p = load_profile(entry.name)
        except (FileNotFoundError, ValueError):
            # config.yaml 이 아직 없는 새 프로파일도 노출 (profiles.ts 동작과 동일)
            out.append(
                {
                    "name": entry.name,
                    "isActive": entry.name == active,
                    "model": "",
                    "provider": "",
                    "hasEnv": (entry / ".env").is_file(),
                    "hasSoul": (entry / "SOUL.md").is_file(),
                }
            )
            continue
        out.append(
            {
                "name": p.name,
                "isActive": p.name == active,
                "model": p.model,
                "provider": p.provider_name,
                "hasEnv": p.has_env,
                "hasSoul": p.has_soul,
            }
        )
    return out
