"""Hermes Gateway 클라이언트.

활성 프로파일(base_url + Bearer 토큰)을 읽어 Hermes Agent 게이트웨이의
전체 기능을 감싼다. CLI 의 에이전틱 기능을 HTTP 로 그대로 사용한다:
  - 디스커버리: health / capabilities / models / skills / toolsets
  - 단순 대화: POST /v1/chat/completions
  - 에이전틱 run: POST /v1/runs → 상태 폴링 / SSE 이벤트 / 승인 / 중단
  - 세션: /api/sessions (생성·조회·메시지·대화·fork·삭제)

게이트웨이가 OpenAI 호환이므로 provider 만 바꾸면 다른 게이트웨이로도 동작한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, AsyncIterator

import httpx

from .profiles import Profile, ProviderConfig, get_active_profile_name, load_profile


class HermesGatewayError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"Hermes Gateway {status}: {detail}")


class HermesGatewayClient:
    """Hermes Gateway HTTP 래퍼. 동기 호출은 httpx.Client, SSE 는 async 스트림."""

    def __init__(self, profile: Profile | None = None, *, profile_name: str | None = None):
        self.profile = profile or load_profile(profile_name)
        self.provider: ProviderConfig = self.profile.active_provider()
        self.base_url = self.provider.base_url.rstrip("/")
        self.model = self.profile.model or "hermes-agent"
        # 영속 클라이언트: keep-alive 커넥션 풀을 재사용한다(요청마다 새 연결 생성 방지).
        self._http = httpx.Client()

    def close(self) -> None:
        self._http.close()

    # ---- 내부 헬퍼 -----------------------------------------------------
    def _headers(self, session_id: str | None = None, session_key: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self.provider.resolve_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        # 게이트웨이 전용 세션 헤더
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id
        if session_key:
            headers["X-Hermes-Session-Key"] = session_key
        headers.update(self.provider.extra_headers or {})
        return headers

    def _url(self, path: str) -> str:
        # base_url 은 .../v1 로 끝난다. /v1 으로 시작하는 경로는 base 의 호스트에 붙인다.
        if path.startswith("/v1"):
            root = self.base_url[: -len("/v1")] if self.base_url.endswith("/v1") else self.base_url
            return f"{root}{path}"
        if path.startswith("/api") or path.startswith("/health"):
            root = self.base_url[: -len("/v1")] if self.base_url.endswith("/v1") else self.base_url
            return f"{root}{path}"
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, json: Any = None, params: Any = None,
                 session_id: str | None = None, session_key: str | None = None,
                 timeout: float = 60.0) -> Any:
        resp = self._http.request(
            method, self._url(path), json=json, params=params,
            headers=self._headers(session_id, session_key), timeout=timeout,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise HermesGatewayError(resp.status_code, detail)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    # ---- 디스커버리 ----------------------------------------------------
    def health(self) -> Any:
        return self._request("GET", "/health")

    def capabilities(self) -> Any:
        return self._request("GET", "/v1/capabilities")

    def models(self) -> Any:
        return self._request("GET", "/v1/models")

    def skills(self) -> Any:
        return self._request("GET", "/v1/skills")

    def toolsets(self) -> Any:
        return self._request("GET", "/v1/toolsets")

    # ---- 단순 대화 -----------------------------------------------------
    def chat(self, messages: list[dict[str, str]], *, model: str | None = None,
             temperature: float = 0.7, session_id: str | None = None,
             session_key: str | None = None) -> Any:
        return self._request(
            "POST", "/v1/chat/completions",
            json={
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
            },
            session_id=session_id, session_key=session_key,
        )

    # ---- 에이전틱 run --------------------------------------------------
    def start_run(self, user_input: str, *, instructions: str | None = None,
                  conversation_history: list[dict[str, str]] | None = None,
                  session_id: str | None = None, model: str | None = None,
                  session_key: str | None = None) -> Any:
        """POST /v1/runs — 에이전트 run 시작. run_id 즉시 반환(202)."""
        body: dict[str, Any] = {"input": user_input, "model": model or self.model}
        if instructions:
            body["instructions"] = instructions
        if conversation_history:
            body["conversation_history"] = conversation_history
        if session_id:
            body["session_id"] = session_id
        return self._request("POST", "/v1/runs", json=body,
                             session_id=session_id, session_key=session_key)

    def get_run(self, run_id: str) -> Any:
        return self._request("GET", f"/v1/runs/{run_id}")

    def approve_run(self, run_id: str, choice: str, *, resolve_all: bool = False) -> Any:
        """승인 응답. choice: once | session | always | deny (approve→once 별칭)."""
        return self._request("POST", f"/v1/runs/{run_id}/approval",
                             json={"choice": choice, "all": resolve_all})

    def stop_run(self, run_id: str) -> Any:
        return self._request("POST", f"/v1/runs/{run_id}/stop")

    async def stream_run_events(self, run_id: str) -> AsyncIterator[str]:
        """GET /v1/runs/{run_id}/events — SSE 원문 라인을 그대로 흘려보낸다."""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET", self._url(f"/v1/runs/{run_id}/events"), headers=self._headers()
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise HermesGatewayError(resp.status_code, body.decode("utf-8", "replace"))
                async for line in resp.aiter_lines():
                    yield line

    # ---- 세션 ----------------------------------------------------------
    def list_sessions(self) -> Any:
        return self._request("GET", "/api/sessions")

    def create_session(self) -> Any:
        return self._request("POST", "/api/sessions", json={})

    def get_session(self, session_id: str) -> Any:
        return self._request("GET", f"/api/sessions/{session_id}")

    def session_messages(self, session_id: str) -> Any:
        return self._request("GET", f"/api/sessions/{session_id}/messages")

    def session_chat(self, session_id: str, message: str) -> Any:
        return self._request("POST", f"/api/sessions/{session_id}/chat",
                             json={"message": message})

    def fork_session(self, session_id: str) -> Any:
        return self._request("POST", f"/api/sessions/{session_id}/fork", json={})

    def delete_session(self, session_id: str) -> Any:
        return self._request("DELETE", f"/api/sessions/{session_id}")


@lru_cache(maxsize=8)
def _client_for(name: str) -> HermesGatewayClient:
    """프로파일별 클라이언트 싱글턴. 프로파일(config.yaml/.env) 로드를 1회로 줄이고
    keep-alive httpx 커넥션을 재사용한다."""
    return HermesGatewayClient(profile_name=name)


def get_client(profile_name: str | None = None) -> HermesGatewayClient:
    name = profile_name or get_active_profile_name()
    return _client_for(name)


def reset_clients() -> None:
    """프로파일 설정 변경 시 캐시 무효화(예: active_profile 전환)."""
    _client_for.cache_clear()
