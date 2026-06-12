// MI Report Agent 백엔드(FastAPI) 클라이언트.
// 기본 베이스 URL 은 환경변수로 재정의 가능: NEXT_PUBLIC_API_BASE

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type SourceType =
  | "edm"
  | "confluence"
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
    req<{ source: Source; ingested: number; stub: boolean }>(
      `/collection/sources/${id}/collect`,
      { method: "POST" },
    ),

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

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  edm: "EDM",
  confluence: "Confluence",
  news: "뉴스",
  broker: "증권사",
  consensus: "컨센서스",
  upload: "수동 업로드",
};
