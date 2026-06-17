"""프로파일 로더 테스트."""

from __future__ import annotations

from app import profiles


def test_name_validation():
    assert profiles.is_valid_profile_name("mi-report")
    assert profiles.is_valid_profile_name("mi_report-1")
    assert not profiles.is_valid_profile_name("-bad")       # 하이픈 시작 불가
    assert not profiles.is_valid_profile_name("BAD")        # 대문자 불가
    assert not profiles.is_valid_profile_name("a" * 65)     # 64자 초과


def test_load_mi_report_profile():
    """동봉된 mi-report 프로파일(OpenRouter)이 정상 로드되는지."""
    p = profiles.load_profile("mi-report")
    assert p.name == "mi-report"
    assert p.model == "minimax/minimax-m3"
    assert p.provider_name == "openrouter"
    assert p.base_url.endswith("/v1")


def test_active_provider_resolution():
    p = profiles.load_profile("mi-report")
    provider = p.active_provider()
    assert provider.type == "openai-compatible"
    assert provider.key_env == "OPENROUTER_API_KEY"


def test_list_profiles_includes_mi_report():
    names = {p["name"] for p in profiles.list_profiles()}
    assert "mi-report" in names
