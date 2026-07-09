"use client";

import { useState } from "react";
import { agentApi, type AgentSource } from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";

interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  // 환각 방어(assistant 전용): 답변 수치의 코퍼스 대조 결과 + 관련 수집 문서
  numbersGrounded?: boolean;
  ungroundedNumbers?: string[];
  sources?: AgentSource[];
}

export default function AskPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(true);

  async function send() {
    const msg = input.trim();
    if (!msg || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const res = await agentApi.chat({ message: msg, sessionId: sessionId ?? undefined });
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
    }
  }

  function reset() {
    setMessages([]);
    setSessionId(null);
    setError(null);
  }

  return (
    <>
      <PageHeader
        title="문서 Q&A"
        description="에이전트가 수집 문서·웹을 스스로 검색해 답합니다 — 멀티턴 대화, 수치는 코퍼스 대조 검증"
      />

      {/* 어떻게 동작하나 · 응답 범위 */}
      <Card className="mb-6 border-sky-900/40 bg-sky-950/20">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-sky-200">ⓘ 어떻게 동작하나 · 응답 범위</h2>
          <button
            onClick={() => setShowHelp((v) => !v)}
            className="text-xs text-zinc-400 hover:text-zinc-200"
          >
            {showHelp ? "접기" : "펼치기"}
          </button>
        </div>
        {showHelp && (
          <div className="mt-3 grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
                에이전트 동작
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-300">
                <li>· hermes 에이전트가 질문을 보고 <strong className="text-zinc-100">코퍼스 검색·웹 검색 도구를 스스로 조합</strong>해 답변</li>
                <li>· 코퍼스: 하이브리드 검색(BM25+동의어 ⊕ 의미 임베딩) — 수집 문서가 1차 근거</li>
                <li>· 이어지는 질문은 <strong className="text-zinc-100">같은 세션에서 맥락을 기억</strong>(멀티턴)</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
                수치 검증 (환각 방어)
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-300">
                <li>· 답변의 수치를 <strong className="text-zinc-100">수집 문서와 자동 대조</strong>해 미확인 수치는 경고 표시</li>
                <li>· 경고 = 곧 오류는 아님 — <strong className="text-zinc-100">웹 출처 수치</strong>일 수 있으니 원문 확인 권장</li>
                <li>· 근거 문서 제목·출처 인용은 에이전트 답변 본문에 포함</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">한계</p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-300">
                <li>· 도구 사용 시 응답에 수십 초 소요</li>
                <li>· 웹 검색 결과의 정확성은 출처에 의존 — 코퍼스/웹 근거를 구분해 읽을 것</li>
                <li>· 텍스트 본문 위주 — 바이너리/이미지 추출은 제한적</li>
              </ul>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">
            에이전트 대화{" "}
            {sessionId && <span className="font-mono text-zinc-600">· {sessionId.slice(0, 20)}…</span>}
          </p>
          {messages.length > 0 && (
            <button onClick={reset} className="text-xs text-zinc-400 hover:text-zinc-200">
              새 대화
            </button>
          )}
        </div>
        <div className="mt-3 flex flex-col gap-3">
          {messages.length === 0 && (
            <p className="text-sm text-zinc-500">
              수집 문서·웹을 스스로 검색해 답하는 에이전트입니다. 이어지는 질문은 맥락을 기억합니다.
            </p>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="self-end rounded-lg bg-sky-950/60 px-3 py-2 text-sm text-sky-100">
                {m.content}
              </div>
            ) : (
              <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                {m.numbersGrounded === false && m.ungroundedNumbers && m.ungroundedNumbers.length > 0 && (
                  <p className="mb-2 rounded-lg border border-amber-900/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
                    ⚠ 다음 수치는 수집 문서에서 확인되지 않았습니다(웹 출처이거나 오류일 수 있음 — 검토 필요):{" "}
                    <span className="font-mono">{m.ungroundedNumbers.join(", ")}</span>
                  </p>
                )}
                <Markdown text={m.content} className="text-sm text-zinc-200" />
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-3 border-t border-zinc-800 pt-2">
                    <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                      관련 수집 문서
                    </p>
                    <ul className="flex flex-col gap-1">
                      {m.sources.map((s, j) => (
                        <li key={j} className="flex items-center gap-2 text-xs text-zinc-300">
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
          {loading && <p className="text-sm text-zinc-500">에이전트가 조사 중… (도구 사용 시 수십 초)</p>}
          {error && (
            <p className="rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
              {error}
            </p>
          )}
        </div>
        <div className="mt-4 flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !loading) send();
            }}
            placeholder="예: 이번 주 HBM 관련 수집 문서 핵심만 정리해줘. 최신 뉴스도 보강해서."
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
          >
            {loading ? "조사 중…" : "보내기"}
          </button>
        </div>
      </Card>
    </>
  );
}
