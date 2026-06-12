"""API 요청/응답 스키마."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    profile: str | None = Field(default=None, description="프로파일명. 미지정 시 활성 프로파일.")
    model: str | None = Field(default=None, description="모델 오버라이드.")
    temperature: float = 0.7
    session_id: str | None = None
    session_key: str | None = None


class RunRequest(BaseModel):
    """에이전틱 run 시작 요청 (Hermes 의 전체 툴셋 사용)."""

    input: str = Field(..., description="사용자 지시/질의.")
    instructions: str | None = Field(default=None, description="ephemeral 시스템 프롬프트.")
    conversation_history: list[ChatMessage] | None = None
    profile: str | None = None
    model: str | None = None
    session_id: str | None = None
    session_key: str | None = None


class ApprovalRequest(BaseModel):
    choice: Literal["once", "session", "always", "deny", "approve"]
    resolve_all: bool = False


class ProfileInfo(BaseModel):
    name: str
    isActive: bool
    model: str
    provider: str
    hasEnv: bool
    hasSoul: bool


class SessionChatRequest(BaseModel):
    message: str


class GatewayPassthrough(BaseModel):
    """게이트웨이 원문 응답을 그대로 담는 래퍼."""

    data: Any


# ── 데이터 수집 ────────────────────────────────────────────────────────
SourceType = Literal["edm", "confluence", "news", "broker", "consensus", "upload"]


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: SourceType
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
