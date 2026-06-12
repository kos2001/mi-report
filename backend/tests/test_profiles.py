"""프로파일 로더 테스트."""

from __future__ import annotations

from app import profiles


def test_name_validation():
    assert profiles.is_valid_profile_name("hermes")
    assert profiles.is_valid_profile_name("mi_report-1")
    assert not profiles.is_valid_profile_name("-bad")       # 하이픈 시작 불가
    assert not profiles.is_valid_profile_name("BAD")        # 대문자 불가
    assert not profiles.is_valid_profile_name("a" * 65)     # 64자 초과


def test_load_hermes_profile():
    """리포지토리에 동봉된 hermes 프로파일이 정상 로드되는지."""
    p = profiles.load_profile("hermes")
    assert p.name == "hermes"
    assert p.model == "hermes-agent"
    assert p.provider_name == "hermes-gateway"
    assert p.base_url.endswith("/v1")


def test_active_provider_resolution():
    p = profiles.load_profile("hermes")
    provider = p.active_provider()
    assert provider.type == "openai-compatible"
    assert provider.key_env == "HERMES_GATEWAY_API_KEY"


def test_list_profiles_includes_hermes():
    names = {p["name"] for p in profiles.list_profiles()}
    assert "hermes" in names
