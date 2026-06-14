"""LLM 클라이언트 — agno + OpenRouter (OpenAI 호환).

기능 모듈(digest/topics/competitors/classify/rag/report)은 오직
`client.chat(messages, temperature=...)` 만 사용하고 OpenAI 호환 completion 을
기대한다. 이 클라이언트는 agno 의 Agent + OpenRouter 모델로 그 계약을 충족한다.

연결 정보는 환경변수로 설정한다(활성 프로파일 .env 자동 로드):
  - OPENROUTER_API_KEY  (필수)
  - OPENROUTER_MODEL    (기본 deepseek/deepseek-v4-flash, .env 로 재정의)
  - OPENROUTER_BASE_URL (기본 https://openrouter.ai/api/v1)

참조 설계: gitspace/lsi_error_analyzer (agno.models.openrouter.OpenRouter + Agent).
"""

from __future__ import annotations

import os
from typing import Any

from .profiles import load_profile

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class LLMError(RuntimeError):
    """LLM 호출 오류(엔드포인트가 HTTP 상태로 변환)."""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"LLM 오류 {status}: {detail}")


# 기존 import 명 하위호환(점진적 정리용 별칭).
HermesGatewayError = LLMError


class LLMClient:
    """agno + OpenRouter 백엔드의 OpenAI 호환 chat 클라이언트."""

    def __init__(self) -> None:
        self.model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)

    def _build_agent(self, model: str | None, temperature: float, instructions: list[str]):
        """요청마다 가벼운 Agent 를 구성한다(시스템 메시지는 instructions 로)."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise LLMError(401, "OPENROUTER_API_KEY 미설정 — 프로파일 .env 에 키를 넣으세요.")
        from agno.agent import Agent
        from agno.models.openrouter import OpenRouter

        return Agent(
            name="mi-report",
            model=OpenRouter(
                id=model or self.model,
                api_key=api_key,
                base_url=self.base_url,
                temperature=temperature,
            ),
            instructions=instructions or None,
            markdown=False,
            telemetry=False,
        )

    @staticmethod
    def _to_prompt(messages: list[dict[str, str]]) -> tuple[list[str], str]:
        """OpenAI 메시지 목록을 (system instructions, 사용자 프롬프트)로 변환."""
        system = [m["content"] for m in messages
                  if m.get("role") == "system" and m.get("content")]
        convo = [m for m in messages if m.get("role") != "system"]
        if len(convo) == 1:
            prompt = convo[0].get("content", "")
        else:
            prompt = "\n\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in convo
            )
        return system, prompt

    async def chat(self, messages: list[dict[str, str]], *, model: str | None = None,
                   temperature: float = 0.7, **_ignored: Any) -> dict[str, Any]:
        """OpenAI 호환 completion 형태로 반환: {'choices':[{'message':{'content':...}}]}."""
        system, prompt = self._to_prompt(messages)
        agent = self._build_agent(model, temperature, system)
        try:
            resp = await agent.arun(prompt)
        except LLMError:
            raise
        except Exception as e:  # agno/OpenRouter 호출 실패 → 502 로 표준화
            raise LLMError(502, f"OpenRouter 호출 실패: {e}") from e
        content = getattr(resp, "content", None)
        if content is None:
            content = str(resp)
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}

    async def aclose(self) -> None:
        return None


def get_client(profile_name: str | None = None) -> LLMClient:
    """활성 프로파일 .env(OPENROUTER_*/CONFLUENCE_*)를 로드하고 LLM 클라이언트를 만든다."""
    try:
        load_profile(profile_name)  # .env 를 os.environ 에 반영(이미 있는 값은 보존)
    except Exception:
        pass
    return LLMClient()


async def close_all() -> None:
    """lifespan 종료 훅용(영속 커넥션 없음 — no-op)."""
    return None
