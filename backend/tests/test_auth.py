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


def test_auth_me(client):
    r = client.get("/auth/me")
    assert r.json() == {"user": {"name": "(인증 비활성)", "role": "admin"}, "authEnabled": False}
    admin = client.post("/auth/users", json={"name": "김오석", "role": "admin"}).json()
    r = client.get("/auth/me", headers={"X-User-Token": admin["token"]})
    assert r.json() == {"user": {"name": "김오석", "role": "admin"}, "authEnabled": True}
