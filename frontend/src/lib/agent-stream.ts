// 에이전트 SSE 스트림 클라이언트 — /agent/chat/stream, /digest/agent-comment/stream.
// 진행사항(progress: 도구 실행)·답변 델타(delta)를 콜백으로 중계하고,
// done 이벤트(검증·출처 포함)를 최종 결과로 반환한다.

import { API_BASE, type AgentChatResponse } from "./api";

export interface AgentProgress {
  tool?: string;
  emoji?: string;
  label?: string;
  toolCallId?: string;
  status?: "running" | "completed" | string;
}

export async function streamAgent(
  path: string,
  body: unknown,
  on: {
    progress?: (p: AgentProgress) => void;
    delta?: (text: string) => void;
  } = {},
): Promise<AgentChatResponse> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-json */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let done: AgentChatResponse | null = null;

  const handle = (chunk: string) => {
    const line = chunk.split("\n").find((l) => l.startsWith("data: "));
    if (!line) return;
    const ev = JSON.parse(line.slice(6));
    if (ev.type === "progress") on.progress?.(ev as AgentProgress);
    else if (ev.type === "delta") on.delta?.(ev.text as string);
    else if (ev.type === "done") done = ev as AgentChatResponse;
    else if (ev.type === "error") throw new Error(ev.detail ?? "에이전트 오류");
  };

  for (;;) {
    const { value, done: eof } = await reader.read();
    if (eof) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      handle(chunk);
    }
  }
  if (!done) throw new Error("에이전트 응답이 완료되지 않았습니다");
  return done;
}

// 진행 단계 목록 상태 갱신 — toolCallId 로 running → completed 를 매칭한다.
export interface ProgressStep {
  key: string;
  text: string;
  done: boolean;
}

export function applyProgress(steps: ProgressStep[], p: AgentProgress): ProgressStep[] {
  const key = p.toolCallId ?? `${p.tool}-${steps.length}`;
  if (p.status === "completed") {
    return steps.map((s) => (s.key === key ? { ...s, done: true } : s));
  }
  const text = `${p.emoji ?? "🛠"} ${p.tool ?? "도구"}${p.label ? ` — ${p.label}` : ""}`;
  return [...steps, { key, text, done: false }];
}
