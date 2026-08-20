"use client";

// 페이지 임베드형 에이전트 대화 카드 — /agent/chat 재사용.
// 첫 질문에 페이지 컨텍스트(다이제스트/경쟁사 분석 등)를 붙이고,
// 이후 턴은 같은 hermes 세션이 맥락을 기억한다(멀티턴).
// 답변에는 수치 검증 경고(⚠)와 관련 수집 문서(출처)가 함께 표시된다.

import { useState } from "react";
import { type AgentSource } from "@/lib/api";
import { applyProgress, streamAgent, type ProgressStep } from "@/lib/agent-stream";
import { loadUserId } from "@/lib/user";
import { Card, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  numbersGrounded?: boolean;
  ungroundedNumbers?: string[];
  sources?: AgentSource[];
}

// 에이전트 작업 중 진행사항(도구 실행 단계 + 스트리밍 답변) 표시.
export function AgentProgressView({
  steps,
  partial,
  title = "에이전트가 조사 중…",
}: {
  steps: ProgressStep[];
  partial: string;
  title?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-100/60 dark:bg-zinc-900/60 px-3 py-2">
      <p className="text-sm text-zinc-500">{title}</p>
      {steps.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {steps.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
              <span>{s.done ? "✅" : "⏳"}</span>
              <span className={s.done ? "text-zinc-500" : "text-zinc-700 dark:text-zinc-300"}>{s.text}</span>
            </li>
          ))}
        </ul>
      )}
      {partial && (
        <div className="mt-2 border-t border-zinc-200 dark:border-zinc-800 pt-2">
          <Markdown text={partial} className="text-sm text-zinc-700 dark:text-zinc-300" />
        </div>
      )}
    </div>
  );
}

export function AgentChatCard({
  title,
  description,
  context,
  placeholder,
}: {
  title: string;
  description: string;
  /** 첫 턴 질문 앞에 붙일 페이지 컨텍스트(없으면 질문만 전송) */
  context?: string | null;
  placeholder: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [partial, setPartial] = useState("");

  async function send() {
    const q = input.trim();
    if (!q || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    setLoading(true);
    setError(null);
    setSteps([]);
    setPartial("");
    try {
      // 첫 턴에만 컨텍스트를 붙인다 — 이후엔 세션이 기억.
      const message = !sessionId && context ? `${context}\n\n질문: ${q}` : q;
      const res = await streamAgent(
        "/agent/chat/stream",
        { message, sessionId: sessionId ?? undefined, userId: loadUserId() },
        {
          progress: (p) => setSteps((prev) => applyProgress(prev, p)),
          delta: (t) => setPartial((prev) => prev + t),
        },
      );
      setSessionId(res.sessionId);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          numbersGrounded: res.numbersGrounded,
          ungroundedNumbers: res.ungroundedNumbers,
          sources: res.sources,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "에이전트 응답 실패");
    } finally {
      setLoading(false);
      setSteps([]);
      setPartial("");
    }
  }

  return (
    <Card className="border-sky-100/40 dark:border-sky-900/40 bg-sky-50/10 dark:bg-sky-950/10">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-sky-800 dark:text-sky-200">{title}</h2>
          <p className="mt-0.5 text-xs text-zinc-600 dark:text-zinc-400">{description}</p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => {
              setMessages([]);
              setSessionId(null);
              setError(null);
            }}
            className="text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            새 질문
          </button>
        )}
      </div>
      {messages.length > 0 && (
        <div className="mt-3 flex flex-col gap-3">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="self-end rounded-lg bg-sky-50/60 dark:bg-sky-950/60 px-3 py-2 text-sm text-sky-900 dark:text-sky-100">
                {m.content}
              </div>
            ) : (
              <div key={i} className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-100/60 dark:bg-zinc-900/60 px-3 py-2">
                {m.numbersGrounded === false && m.ungroundedNumbers && m.ungroundedNumbers.length > 0 && (
                  <p className="mb-2 rounded-lg border border-amber-100/60 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/40 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                    ⚠ 다음 수치는 수집 문서에서 확인되지 않았습니다(웹 출처이거나 오류일 수 있음 — 검토 필요):{" "}
                    <span className="font-mono">{m.ungroundedNumbers.join(", ")}</span>
                  </p>
                )}
                <Markdown text={m.content} className="text-sm text-zinc-800 dark:text-zinc-200" />
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-3 border-t border-zinc-200 dark:border-zinc-800 pt-2">
                    <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                      관련 수집 문서
                    </p>
                    <ul className="flex flex-col gap-1">
                      {m.sources.map((s, j) => (
                        <li key={j} className="flex items-center gap-2 text-xs text-zinc-700 dark:text-zinc-300">
                          <Tag>{s.source}</Tag>
                          <span>{s.title}</span>
                          {s.publishedAt && <span className="text-zinc-500">· {s.publishedAt}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ),
          )}
        </div>
      )}
      {loading && (
        <div className="mt-3">
          <AgentProgressView steps={steps} partial={partial} />
        </div>
      )}
      {error && (
        <p className="mt-3 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !loading) send();
          }}
          placeholder={placeholder}
          className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
        >
          {loading ? "조사 중…" : "질문"}
        </button>
      </div>
    </Card>
  );
}
