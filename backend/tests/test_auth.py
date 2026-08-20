"""사용자 토큰 인증(admin/viewer) 테스트."""

from __future__ import annotations

import pytest

from app import auth


def test_disabled_when_no_users(isolated):
    assert auth.enabled() is False
    assert auth.authenticate(None) == {"name": "(인증 비활성)", "role": "admin"}
    assert auth.authenticate("아무 토큰") == {"name": "(인증 비활성)", "role": "admin"}


def test_create_user_enables_auth_and_authenticates(isolated):
    created = auth.create_user("김오석", "admin")
    assert created["name"] == "김오석" and created["role"] == "admin"
    assert created["token"]

    assert auth.enabled() is True
    assert auth.authenticate(created["token"]) == {"name": "김오석", "role": "admin"}


def test_authenticate_wrong_or_missing_token_once_enabled(isolated):
    auth.create_user("김오석", "admin")
    assert auth.authenticate("잘못된 토큰") is None
    assert auth.authenticate(None) is None


def test_create_user_duplicate_name_raises(isolated):
    auth.create_user("김오석", "admin")
    with pytest.raises(ValueError):
        auth.create_user("김오석", "viewer")


def test_create_user_invalid_role_raises(isolated):
    with pytest.raises(ValueError):
        auth.create_user("뷰어1", "superadmin")


def test_list_users(isolated):
    auth.create_user("김오석", "admin")
    auth.create_user("뷰어1", "viewer")
    users = auth.list_users()
    names = {u["name"] for u in users}
    assert names == {"김오석", "뷰어1"}
    assert all("token" in u and "role" in u for u in users)


def test_delete_user(isolated):
    auth.create_user("김오석", "admin")
    auth.create_user("뷰어1", "viewer")
    auth.delete_user("뷰어1")
    assert {u["name"] for u in auth.list_users()} == {"김오석"}


def test_delete_user_missing_raises(isolated):
    auth.create_user("김오석", "admin")
    with pytest.raises(KeyError):
        auth.delete_user("없는사람")


def test_update_user_role(isolated):
    auth.create_user("뷰어1", "viewer")
    updated = auth.update_user_role("뷰어1", "admin")
    assert updated["role"] == "admin"
    assert auth.authenticate(updated["token"])["role"] == "admin"


def test_update_user_role_invalid_raises(isolated):
    auth.create_user("뷰어1", "viewer")
    with pytest.raises(ValueError):
        auth.update_user_role("뷰어1", "superadmin")


def test_update_user_role_missing_raises(isolated):
    with pytest.raises(KeyError):
        auth.update_user_role("없는사람", "admin")


# ── OIDC(SSO) 로그인 연동 ──────────────────────────────────────────────────
def test_find_or_create_oidc_user_creates_viewer_on_first_login(isolated):
    user = auth.find_or_create_oidc_user(sub="oidc|abc123", name_hint="kim@example.com")
    assert user["role"] == "viewer"  # 최초 SSO 로그인은 항상 viewer — 관리자가 승격
    assert user["token"]
    assert auth.enabled() is True


def test_find_or_create_oidc_user_reuses_existing_on_second_login(isolated):
    first = auth.find_or_create_oidc_user(sub="oidc|abc123", name_hint="kim@example.com")
    # 관리자가 승격시켰다고 가정 — 재로그인해도 역할·토큰이 유지되어야 한다(강등 방지).
    auth.update_user_role(first["name"], "admin")
    second = auth.find_or_create_oidc_user(sub="oidc|abc123", name_hint="kim@example.com")
    assert second["name"] == first["name"]
    assert second["token"] == first["token"]
    assert second["role"] == "admin"


def test_find_or_create_oidc_user_dedupes_name_collision(isolated):
    auth.create_user("kim@example.com", "viewer")  # 수동으로 같은 이름의 사용자가 이미 있음
    user = auth.find_or_create_oidc_user(sub="oidc|new-sub", name_hint="kim@example.com")
    assert user["name"] != "kim@example.com"  # 충돌 없이 구분되는 이름을 받는다


# ── 엔드포인트(게이트 미들웨어) ────────────────────────────────────────────
def test_write_endpoint_open_when_auth_disabled(client):
    # 아직 아무도 안 만들었으면(테스트 tmp DB 는 항상 이 상태) 인증 없이도 통과 —
    # 기존 배포가 auth 도입으로 깨지지 않는다는 것을 보장.
    r = client.post("/feedback", json={"kind": "digest", "ref": "1", "rating": "up"})
    assert r.status_code == 201


def test_bootstrap_first_admin_without_token(client):
    # 최초 관리자 생성 자체도 "쓰기" 요청이지만, 아직 인증이 꺼져 있으므로 토큰 없이 성공.
    r = client.post("/auth/users", json={"name": "김오석", "role": "admin"})
    assert r.status_code == 201
    assert r.json()["role"] == "admin"


def test_write_endpoint_requires_admin_after_first_user(client):
    admin = client.post("/auth/users", json={"name": "김오석", "role": "admin"}).json()
    viewer = client.post(
        "/auth/users", json={"name": "뷰어1", "role": "viewer"},
        headers={"X-User-Token": admin["token"]},
    ).json()

    # 토큰 없음 → 401
    r = client.post("/feedback", json={"kind": "digest", "ref": "1", "rating": "up"})
    assert r.status_code == 401

    # viewer 토큰 → 403
    r = client.post(
        "/feedback", json={"kind": "digest", "ref": "1", "rating": "up"},
        headers={"X-User-Token": viewer["token"]},
    )
    assert r.status_code == 403

    # admin 토큰 → 통과
    r = client.post(
        "/feedback", json={"kind": "digest", "ref": "1", "rating": "up"},
        headers={"X-User-Token": admin["token"]},
    )
    assert r.status_code == 201


def test_get_endpoint_open_to_viewer_after_users_exist(client):
    admin = client.post("/auth/users", json={"name": "김오석", "role": "admin"}).json()
    viewer = client.post(
        "/auth/users", json={"name": "뷰어1", "role": "viewer"},
        headers={"X-User-Token": admin["token"]},
    ).json()
    r = client.get("/feedback/summary", headers={"X-User-Token": viewer["token"]})
    assert r.status_code == 200
    # GET 은 토큰 없이도 통과(viewer 이하 공개 읽기)
    assert client.get("/feedback/summary").status_code == 200


def test_auth_users_list_requires_admin(client):
    admin = client.post("/auth/users", json={"name": "김오석", "role": "admin"}).json()
    viewer = client.post(
        "/auth/users", json={"name": "뷰어1", "role": "viewer"},
        headers={"X-User-Token": admin["token"]},
    ).json()
    # GET 이지만 토큰이 그대로 노출되므로 admin 만 허용.
    assert client.get("/auth/users").status_code == 403
    assert client.get("/auth/users", headers={"X-User-Token": viewer["token"]}).status_code == 403
    r = client.get("/auth/users", headers={"X-User-Token": admin["token"]})
    assert r.status_code == 200
    assert {u["name"] for u in r.json()["users"]} == {"김오석", "뷰어1"}


def test_auth_users_update_role_endpoint(client):
    admin = client.post("/auth/users", json={"name": "김오석", "role": "admin"}).json()
    viewer = client.post(
        "/auth/users", json={"name": "뷰어1", "role": "viewer"},
        headers={"X-User-Token": admin["token"]},
    ).json()

    # viewer 토큰으로는 승격 불가(쓰기=admin 게이트)
    r = client.patch(
        "/auth/users/뷰어1/role", json={"role": "admin"},
        headers={"X-User-Token": viewer["token"]},
    )
    assert r.status_code == 403

    r = client.patch(
        "/auth/users/뷰어1/role", json={"role": "admin"},
        headers={"X-User-Token": admin["token"]},
    )
    assert r.status_code == 200 and r.json()["role"] == "admin"

    r = client.patch(
        "/auth/users/없는사람/role", json={"role": "admin"},
        headers={"X-User-Token": admin["token"]},
    )
    assert r.status_code == 404


def test_auth_oidc_status_unconfigured_by_default(client):
    r = client.get("/auth/oidc/status")
    assert r.json() == {"configured": False}


def test_auth_oidc_login_501_when_unconfigured(client):
    r = client.get("/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 501


def test_auth_me(client):
    r = client.get("/auth/me")
    assert r.json() == {"user": {"name": "(인증 비활성)", "role": "admin"}, "authEnabled": False}
    admin = client.post("/auth/users", json={"name": "김오석", "role": "admin"}).json()
    r = client.get("/auth/me", headers={"X-User-Token": admin["token"]})
    assert r.json() == {"user": {"name": "김오석", "role": "admin"}, "authEnabled": True}
