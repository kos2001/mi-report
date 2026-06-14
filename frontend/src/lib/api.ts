// MI Report Agent 백엔드(FastAPI) 클라이언트.
// 기본 베이스 URL 은 환경변수로 재정의 가능: NEXT_PUBLIC_API_BASE

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type SourceType =
  | "edm"
  | "confluence"
  | "jira"
  | "news"
  | "broker"
  | "consensus"
  | "upload";

export interface Source {
  id: string;
  name: string;
  type: SourceType;
  config: Record<string, unknown>;
  enabled: boolean;
  status: string;
  lastRun: string | null;
  count: number;
  createdAt: string;
}

export interface CollectedDoc {
  id: string;
  sourceId: string | null;
  sourceName: string;
  title: string;
  filename: string | null;
  topic: string | null;
  publishedAt: string | null;
  status: string;
  createdAt: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-json */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listSources: () =>
    req<{ sources: Source[] }>("/collection/sources").then((d) => d.sources),

  // 대시보드용: 소스 목록 + 문서 개수를 한 번에 (문서 전체 목록 전송 회피).
  collectionOverview: () =>
    req<{ sources: Source[]; documentCount: number }>("/collection/sources"),

  createSource: (body: {
    name: string;
    type: SourceType;
    config?: Record<string, unknown>;
    enabled?: boolean;
  }) =>
    req<Source>("/collection/sources", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateSource: (
    id: string,
    body: { name?: string; config?: Record<string, unknown>; enabled?: boolean },
  ) =>
    req<Source>(`/collection/sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteSource: (id: string) =>
    req<void>(`/collection/sources/${id}`, { method: "DELETE" }),

  collect: (id: string) =>
    req<{
      source: Source;
      ingested: number;
      stub: boolean;
      documents?: CollectedDoc[];
      errors?: { url: string; error: string }[];
    }>(`/collection/sources/${id}/collect`, { method: "POST" }),

  listDocuments: (params?: { source?: string; q?: string; topic?: string }) => {
    const qs = new URLSearchParams();
    if (params?.source) qs.set("source", params.source);
    if (params?.q) qs.set("q", params.q);
    if (params?.topic) qs.set("topic", params.topic);
    const suffix = qs.toString() ? `?${qs}` : "";
    return req<{ documents: CollectedDoc[] }>(
      `/collection/documents${suffix}`,
    ).then((d) => d.documents);
  },

  deleteDocument: (id: string) =>
    req<void>(`/collection/documents/${id}`, { method: "DELETE" }),

  // AI 자동 분류: 단일 문서의 주제를 부여한다.
  classifyDocument: (id: string) =>
    req<{ document: CollectedDoc; classification: { topic: string; category: string; tags: string[] } }>(
      `/collection/documents/${id}/classify`,
      { method: "POST" },
    ),

  // AI 자동 분류: 주제 미부여 문서들을 일괄 분류한다.
  classifyUntagged: (limit = 20) =>
    req<{ classified: { id: string; title: string; topic: string; category: string }[]; count: number }>(
      `/collection/classify-untagged?limit=${limit}`,
      { method: "POST" },
    ),

  upload: async (file: File, topic?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (topic) fd.append("topic", topic);
    const res = await fetch(`${API_BASE}/collection/upload`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(`업로드 실패: ${res.status}`);
    return res.json() as Promise<CollectedDoc>;
  },
};

// ── 뉴스 다이제스트 (AI agent 생성) ───────────────────────────────────────
export interface GeneratedDigestItem {
  id: string;
  title: string;
  source: string;
  publishedAt: string;
  summary: string;
  slsiRelevance: string;
  demandImpact: string;
  risk: string;
  impact: "high" | "medium" | "low";
  tags: string[];
}

export interface GeneratedDigest {
  issueNo: number;
  period: string;
  mailedAt: string | null;
  generated: boolean;
  sourceDocCount: number;
  items: GeneratedDigestItem[];
  generatedAt?: string; // 스케줄 파이프라인이 저장한 경우에만
}

export const digestApi = {
  generate: (body?: {
    issueNo?: number;
    period?: string;
    limit?: number;
    source?: string;
    topic?: string;
  }) =>
    req<GeneratedDigest>("/digest/generate", {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),

  // 스케줄 파이프라인이 마지막으로 저장한 다이제스트(없으면 null)
  latest: () =>
    req<{ digest: GeneratedDigest | null }>("/digest/latest").then((d) => d.digest),

  // 다이제스트 메일 발송(SMTP 미설정 시 미리보기만 반환)
  send: (body: {
    issueNo: number;
    period: string;
    items: GeneratedDigestItem[];
    to?: string[];
    dryRun?: boolean;
  }) =>
    req<{
      status: "sent" | "not_sent" | "error";
      reason?: string;
      detail?: string;
      subject: string;
      to?: string[];
      preview?: string;
    }>("/digest/send", { method: "POST", body: JSON.stringify(body) }),
};

// ── 주제별 History (AI agent 생성) ────────────────────────────────────────
export interface TopicListItem {
  topic: string;
  count: number;
}

export interface GeneratedTopic {
  id: string;
  title: string;
  category: "SET" | "반도체 설계" | "반도체 제조" | "수요/시황";
  summary: string;
  insight: string;
  sourceCount: number;
  updatedAt: string;
  generated: boolean;
  history: { date: string; event: string; source: string }[];
}

export const topicsApi = {
  list: () => req<{ topics: TopicListItem[] }>("/topics").then((d) => d.topics),

  summarize: (body: { topic: string; limit?: number }) =>
    req<GeneratedTopic>("/topics/summarize", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ── 경쟁사 IR (AI agent 생성) ─────────────────────────────────────────────
export interface GeneratedCompetitor {
  id: string;
  name: string;
  ticker: string;
  fiscalQuarter: string;
  reportedAt: string;
  financials: { metric: string; value: string; qoq: number | null; yoy: number | null }[];
  callSummary: string[];
  qoqChanges: string[];
  consensus: {
    metric: string;
    current: string;
    previous: string;
    revisedAt: string;
    broker: string;
    direction: "up" | "down" | "flat";
  }[];
  sourceDocCount: number;
  generated: boolean;
}

export const competitorsApi = {
  analyze: (body: { name: string; ticker?: string; topic?: string; q?: string; limit?: number }) =>
    req<GeneratedCompetitor>("/competitors/analyze", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ── 문서 코퍼스 Q&A (RAG) ─────────────────────────────────────────────────
export interface RagAnswer {
  question: string;
  answer: string;
  sources: { index: number; title: string; source: string }[];
  usedDocCount: number;
}

export const ragApi = {
  query: (body: { question: string; topic?: string; q?: string; limit?: number }) =>
    req<RagAnswer>("/rag/query", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ── 주간 MI 리포트 통합 생성 ──────────────────────────────────────────────
export interface GeneratedReport {
  generatedAt: string;
  period: string;
  issueNo: number;
  overview: string;
  digest: GeneratedDigest | null;
  topics: GeneratedTopic[];
}

export const reportApi = {
  generate: (body?: {
    issueNo?: number;
    period?: string;
    maxTopics?: number;
    digestLimit?: number;
    topicLimit?: number;
  }) =>
    req<GeneratedReport>("/report/generate", {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
};

// ── 지식 자산(생성물 누적) + 자기 개선(피드백) ─────────────────────────────
export interface ArtifactMeta {
  id: string;
  kind: string;
  title: string;
  ref: string | null;
  createdAt: string;
}

export interface ArtifactFull extends ArtifactMeta {
  payload: Record<string, unknown>;
}

export const artifactsApi = {
  list: (params?: { kind?: string; ref?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.kind) qs.set("kind", params.kind);
    if (params?.ref) qs.set("ref", params.ref);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs}` : "";
    return req<{ artifacts: ArtifactMeta[]; count: number }>(`/artifacts${suffix}`);
  },
  get: (id: string) => req<ArtifactFull>(`/artifacts/${id}`),
  count: () => req<{ count: number }>("/artifacts?limit=1").then((d) => d.count),
};

export const feedbackApi = {
  send: (body: { kind: string; ref?: string; rating: "up" | "down"; note?: string }) =>
    req<{ id: string; rating: string }>("/feedback", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  edm: "EDM",
  confluence: "Confluence",
  jira: "Jira",
  news: "뉴스",
  broker: "증권사",
  consensus: "컨센서스",
  upload: "수동 업로드",
};
