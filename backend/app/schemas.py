"""API 요청/응답 스키마."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileInfo(BaseModel):
    name: str
    isActive: bool
    model: str
    provider: str
    hasEnv: bool
    hasSoul: bool


# ── VOC (Voice of Customer) ───────────────────────────────────────────────
class VocCreate(BaseModel):
    reporter: str = Field(..., min_length=1, description="작성자(사용자).")
    content: str = Field(..., min_length=1, description="이 서비스에 대한 의견/요청/버그 내용.")
    area: str = Field(default="기타", description="기능 영역(대시보드/데이터수집/다이제스트/주제/경쟁사/문서Q&A/리포트/기타).")
    category: str = Field(default="문의", description="유형(기능요청/버그/개선/문의/칭찬).")
    sentiment: str = Field(default="중립", description="감정(긍정/중립/부정).")
    priority: str = Field(default="중", description="우선순위(상/중/하).")


class VocStatusUpdate(BaseModel):
    status: str = Field(..., description="처리 상태(신규/검토중/완료).")


# ── 문서 Q&A 골든 평가셋 ──────────────────────────────────────────────────
class ScheduleConfig(BaseModel):
    enabled: bool = False
    frequency: Literal["daily", "weekly"] = "daily"
    hour: int = Field(default=7, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: int = Field(default=0, ge=0, le=6, description="0=월 … 6=일 (weekly 일 때).")
    digestLimit: int = Field(default=20, ge=1, le=100)


class QaGoldenCreate(BaseModel):
    question: str = Field(..., min_length=1)
    kind: str = Field(default="answerable", description="answerable | negative")
    expectedIds: list[str] = Field(default_factory=list, description="근거 문서 라벨 목록.")
    keywords: list[str] = Field(default_factory=list, description="정답(반드시 포함) 키워드/수치.")
    forbidden: list[str] = Field(default_factory=list, description="나오면 안 되는 값(반올림/왜곡/환각).")
    note: str = ""


# ── 데이터 수집 ────────────────────────────────────────────────────────
SourceType = Literal["edm", "confluence", "sec", "dart", "hankyung", "news", "broker", "consensus", "upload"]


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


class FeedbackRequest(BaseModel):
    """생성물 피드백(자기 개선 신호)."""

    kind: str = Field(..., description="대상 종류(digest/topic/competitor/report 등).")
    ref: str | None = Field(default=None, description="대상 식별자(호수/주제/티커 등).")
    rating: Literal["up", "down"]
    note: str = ""


class DigestSendRequest(BaseModel):
    """다이제스트 메일 발송 요청(생성된 초안을 그대로 전달)."""

    issueNo: int = Field(default=1, ge=1)
    period: str = ""
    items: list[DigestItemOut] = Field(default_factory=list)
    to: list[str] | None = Field(default=None, description="수신자(미지정 시 SMTP_TO).")
    subject: str | None = None
    dryRun: bool = Field(default=False, description="true 면 발송하지 않고 미리보기만.")


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


# ── 문서 자동 분류 (AI agent) ─────────────────────────────────────────────
class DocClassificationOut(BaseModel):
    """LLM 이 산출하는 문서 분류 결과."""

    topic: str = ""
    category: TopicCategory = "수요/시황"
    tags: list[str] = Field(default_factory=list)


# ── 문서 코퍼스 Q&A (RAG) ─────────────────────────────────────────────────
class RagQueryRequest(BaseModel):
    """수집 문서 근거 자연어 질문."""

    question: str = Field(..., min_length=1, description="자연어 질문.")
    topic: str | None = Field(default=None, description="문서 topic 필터(선택).")
    q: str | None = Field(default=None, description="문서 전문검색어(선택, 제목·주제 기준).")
    limit: int = Field(default=8, ge=1, le=30, description="근거로 쓸 문서 최대 건수.")
    profile: str | None = None


# ── 주간 MI 리포트 통합 생성 (AI agent 오케스트레이션) ─────────────────────
class ReportGenerateRequest(BaseModel):
    """다이제스트 + 주제 요약 + 총평을 묶은 주간 리포트 생성 요청."""

    issueNo: int = Field(default=1, ge=1, description="리포트 호수.")
    period: str = Field(default="", description="대상 기간 표기.")
    maxTopics: int = Field(default=3, ge=0, le=10, description="요약할 주제 최대 개수.")
    digestLimit: int = Field(default=20, ge=1, le=100, description="다이제스트 입력 문서 수.")
    topicLimit: int = Field(default=20, ge=1, le=100, description="주제별 입력 문서 수.")
    template: str | None = Field(default=None, description="문서 렌더 템플릿({{토큰}}). 미지정 시 기본 템플릿.")
    profile: str | None = None
