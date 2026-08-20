"""SSO(OIDC) 로그인 — 표준 OIDC discovery 로 어떤 IdP든(Okta/Azure AD/Keycloak/
Google 등) 연동 가능한 일반 클라이언트. authlib 가 PKCE·state·nonce·JWKS 서명
검증을 처리한다(직접 구현하지 않음 — 토큰 검증을 손으로 짜는 건 보안 사고 원인).

환경변수(profile .env):
  OIDC_ISSUER         예: https://your-idp.example.com/ (뒤에 /.well-known/
                       openid-configuration 를 붙여 discovery)
  OIDC_CLIENT_ID
  OIDC_CLIENT_SECRET
  OIDC_REDIRECT_URI    백엔드 콜백 주소(기본 http://localhost:8000/auth/oidc/callback)
  OIDC_FRONTEND_URL    로그인 완료 후 앱 토큰을 실어 돌려보낼 프론트엔드 주소
                       (기본 http://localhost:3000/settings)

세 개(issuer/client_id/client_secret)가 모두 없으면 configured() 가 False —
기존 X-User-Token 로그인 흐름에는 아무 영향이 없다.
"""

from __future__ import annotations

import os
from typing import Any

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request

_oauth: OAuth | None = None


def configured() -> bool:
    return bool(
        os.getenv("OIDC_ISSUER") and os.getenv("OIDC_CLIENT_ID") and os.getenv("OIDC_CLIENT_SECRET")
    )


def _client():
    global _oauth
    if _oauth is None:
        oauth = OAuth()
        issuer = os.environ["OIDC_ISSUER"].rstrip("/")
        oauth.register(
            name="sso",
            client_id=os.environ["OIDC_CLIENT_ID"],
            client_secret=os.environ["OIDC_CLIENT_SECRET"],
            server_metadata_url=f"{issuer}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth.sso


def redirect_uri() -> str:
    return os.environ.get("OIDC_REDIRECT_URI", "http://localhost:8000/auth/oidc/callback")


def frontend_return_url() -> str:
    return os.environ.get("OIDC_FRONTEND_URL", "http://localhost:3000/settings")


async def login_redirect(request: Request):
    return await _client().authorize_redirect(request, redirect_uri())


async def handle_callback(request: Request) -> dict[str, Any]:
    """콜백에서 코드↔토큰 교환 + ID 토큰 검증(서명·발급자·audience·nonce, authlib 처리)
    후 claims 에서 사용자 식별 정보만 뽑아 돌려준다."""
    token = await _client().authorize_access_token(request)
    userinfo = token.get("userinfo") or await _client().userinfo(token=token)
    return {
        "sub": userinfo["sub"],
        "name_hint": userinfo.get("email") or userinfo.get("name") or userinfo["sub"],
    }
