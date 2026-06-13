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


class IngestText(BaseModel):
    """COM 인제스트 워커가 보내는, DRM 해제 상태로 추출된 평문 텍스트."""

    title: str = Field(..., min_length=1)
    text: str
    topic: str | None = None
    original_filename: str | None = None
    source_name: str | None = None


# ── 뉴스 다이제스트 (AI agent 생성) ───────────────────────────────────────
ImpactLevel = Literal["high", "medium", "low"]


class DigestItemOut(BaseModel):
    """LLM 이 산출하는 다이제스트 항목(프론트 DigestItem 과 매칭, id 는 서버가 부여)."""

    title: str = Field(..., min_length=1)
    source: str = ""
    publishedAt: str = ""
    summary: str = ""
    slsiRelevance: str = ""
    demandImpact: str = ""
    risk: str = ""
    impact: ImpactLevel = "medium"
    tags: list[str] = Field(default_factory=list)


class DigestGenerateRequest(BaseModel):
    """수집 문서로부터 다이제스트 초안 생성 요청."""

    source: str | None = Field(default=None, description="소스 ID 필터(선택).")
    topic: str | None = Field(default=None, description="주제 필터(선택).")
    limit: int = Field(default=20, ge=1, le=100, description="입력 문서 최대 건수.")
    issueNo: int = Field(default=1, ge=1, description="다이제스트 호수.")
    period: str = Field(default="", description="대상 기간 표기(예: 2026.06.08 – 06.11).")
    profile: str | None = None


# ── 주제별 History (AI agent 생성) ────────────────────────────────────────
TopicCategory = Literal["SET", "반도체 설계", "반도체 제조", "수요/시황"]


class TopicHistoryEntry(BaseModel):
    date: str = ""
    event: str = ""
    source: str = ""


class TopicSummaryOut(BaseModel):
    """LLM 이 산출하는 주제 요약(프론트 Topic 과 매칭, id/title/메타는 서버가 부여)."""

    category: TopicCategory = "수요/시황"
    summary: str = ""
    insight: str = ""
    history: list[TopicHistoryEntry] = Field(default_factory=list)


class TopicSummarizeRequest(BaseModel):
    """주제별 누적 문서로부터 이력·인사이트 생성 요청."""

    topic: str = Field(..., min_length=1, description="요약할 주제(문서 topic 값).")
    limit: int = Field(default=30, ge=1, le=100, description="입력 문서 최대 건수.")
    profile: str | None = None


# ── 경쟁사 IR (AI agent 생성) ─────────────────────────────────────────────
ConsensusDirection = Literal["up", "down", "flat"]


class CompetitorFinancial(BaseModel):
    metric: str = ""
    value: str = ""
    # 문서에 수치가 없을 수 있으므로 nullable(환각 방지: 없으면 null).
    qoq: float | None = None
    yoy: float | None = None


class ConsensusEntry(BaseModel):
    metric: str = ""
    current: str = ""
    previous: str = ""
    revisedAt: str = ""
    broker: str = ""
    direction: ConsensusDirection = "flat"


class CompetitorAnalysisOut(BaseModel):
    """LLM 이 산출하는 경쟁사 분기 분석(프론트 Competitor 와 매칭, id/name 은 서버 부여)."""

    fiscalQuarter: str = ""
    reportedAt: str = ""
    financials: list[CompetitorFinancial] = Field(default_factory=list)
    callSummary: list[str] = Field(default_factory=list)
    qoqChanges: list[str] = Field(default_factory=list)
    consensus: list[ConsensusEntry] = Field(default_factory=list)


class CompetitorAnalyzeRequest(BaseModel):
    """경쟁사 IR/실적 문서로부터 분기 분석 생성 요청."""

    name: str = Field(..., min_length=1, description="경쟁사 이름.")
    ticker: str = Field(default="", description="티커(선택).")
    topic: str | None = Field(default=None, description="문서 topic 필터(선택).")
    q: str | None = Field(default=None, description="문서 전문검색어(선택).")
    limit: int = Field(default=20, ge=1, le=100, description="입력 문서 최대 건수.")
    profile: str | None = None
