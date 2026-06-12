"""Hermes Gateway 클라이언트 (async).

활성 프로파일(base_url + Bearer 토큰)을 읽어 Hermes Agent 게이트웨이의
전체 기능을 감싼다. CLI 의 에이전틱 기능을 HTTP 로 그대로 사용한다:
  - 디스커버리: health / capabilities / models / skills / toolsets
  - 단순 대화: POST /v1/chat/completions
  - 에이전틱 run: POST /v1/runs → 상태 폴링 / SSE 이벤트 / 승인 / 중단
  - 세션: /api/sessions (생성·조회·메시지·대화·fork·삭제)

비동기 + 영속 httpx.AsyncClient(keep-alive 풀)로, 동시 요청이 스레드풀을
점유하지 않고 커넥션을 재사용한다. provider 만 바꾸면 다른 게이트웨이로도 동작한다.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from .profiles import Profile, ProviderConfig, get_active_profile_name, load_profile


class HermesGatewayError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"Hermes Gateway {status}: {detail}")


class HermesGatewayClient:
    """Hermes Gateway HTTP 래퍼 (async)."""

    def __init__(self, profile: Profile | None = None, *, profile_name: str | None = None):
        self.profile = profile or load_profile(profile_name)
        self.provider: ProviderConfig = self.profile.active_provider()
        self.base_url = self.provider.base_url.rstrip("/")
        self.model = self.profile.model or "hermes-agent"
        # 영속 AsyncClient(keep-alive 풀)를 지연 생성한다.
        # 헤더/URL 구성만 하는 호출(테스트 등)에서는 클라이언트를 만들지 않는다.
        self._http_client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

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

    async def _request(self, method: str, path: str, *, json: Any = None, params: Any = None,
                       session_id: str | None = None, session_key: str | None = None,
                       timeout: float = 60.0) -> Any:
        resp = await self._http().request(
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
    async def health(self) -> Any:
        return await self._request("GET", "/health")

    async def capabilities(self) -> Any:
        return await self._request("GET", "/v1/capabilities")

    async def models(self) -> Any:
        return await self._request("GET", "/v1/models")

    async def skills(self) -> Any:
        return await self._request("GET", "/v1/skills")

    async def toolsets(self) -> Any:
        return await self._request("GET", "/v1/toolsets")

    # ---- 단순 대화 -----------------------------------------------------
    async def chat(self, messages: list[dict[str, str]], *, model: str | None = None,
                   temperature: float = 0.7, session_id: str | None = None,
                   session_key: str | None = None) -> Any:
        return await self._request(
            "POST", "/v1/chat/completions",
            json={
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
            },
            session_id=session_id, session_key=session_key,
        )

    # ---- 에이전틱 run --------------------------------------------------
    async def start_run(self, user_input: str, *, instructions: str | None = None,
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
        return await self._request("POST", "/v1/runs", json=body,
                                   session_id=session_id, session_key=session_key)

    async def get_run(self, run_id: str) -> Any:
        return await self._request("GET", f"/v1/runs/{run_id}")

    async def approve_run(self, run_id: str, choice: str, *, resolve_all: bool = False) -> Any:
        """승인 응답. choice: once | session | always | deny (approve→once 별칭)."""
        return await self._request("POST", f"/v1/runs/{run_id}/approval",
                                   json={"choice": choice, "all": resolve_all})

    async def stop_run(self, run_id: str) -> Any:
        return await self._request("POST", f"/v1/runs/{run_id}/stop")

    async def stream_run_events(self, run_id: str) -> AsyncIterator[str]:
        """GET /v1/runs/{run_id}/events — SSE 원문 라인을 그대로 흘려보낸다."""
        async with self._http().stream(
            "GET", self._url(f"/v1/runs/{run_id}/events"),
            headers=self._headers(), timeout=None,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise HermesGatewayError(resp.status_code, body.decode("utf-8", "replace"))
            async for line in resp.aiter_lines():
                yield line

    # ---- 세션 ----------------------------------------------------------
    async def list_sessions(self) -> Any:
        return await self._request("GET", "/api/sessions")

    async def create_session(self) -> Any:
        return await self._request("POST", "/api/sessions", json={})

    async def get_session(self, session_id: str) -> Any:
        return await self._request("GET", f"/api/sessions/{session_id}")

    async def session_messages(self, session_id: str) -> Any:
        return await self._request("GET", f"/api/sessions/{session_id}/messages")

    async def session_chat(self, session_id: str, message: str) -> Any:
        return await self._request("POST", f"/api/sessions/{session_id}/chat",
                                   json={"message": message})

    async def fork_session(self, session_id: str) -> Any:
        return await self._request("POST", f"/api/sessions/{session_id}/fork", json={})

    async def delete_session(self, session_id: str) -> Any:
        return await self._request("DELETE", f"/api/sessions/{session_id}")


# 프로파일별 클라이언트 싱글턴. 프로파일(config.yaml/.env) 로드를 1회로 줄이고
# keep-alive 커넥션을 재사용한다.
_clients: dict[str, HermesGatewayClient] = {}


def get_client(profile_name: str | None = None) -> HermesGatewayClient:
    name = profile_name or get_active_profile_name()
    client = _clients.get(name)
    if client is None:
        client = HermesGatewayClient(profile_name=name)
        _clients[name] = client
    return client


async def close_all() -> None:
    """앱 종료 시 영속 커넥션 정리."""
    for client in _clients.values():
        await client.aclose()
    _clients.clear()


def reset_clients() -> None:
    """프로파일 설정 변경 시 캐시 무효화(예: active_profile 전환)."""
    _clients.clear()
