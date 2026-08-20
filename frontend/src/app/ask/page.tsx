"use client";

import { useCallback, useEffect, useState } from "react";
import { agentApi, type AgentSessionInfo, type AgentSource } from "@/lib/api";
import { applyProgress, streamAgent, type ProgressStep } from "@/lib/agent-stream";
import { loadUserId } from "@/lib/user";
import { AgentProgressView } from "@/components/agent-chat";
import { QaAnswerCard } from "@/components/qa-answer-card";
import { Card, PageHeader } from "@/components/ui";

interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  // 환각 방어(assistant 전용): 답변 수치의 코퍼스 대조 결과 + 관련 수집 문서
  numbersGrounded?: boolean;
  ungroundedNumbers?: string[];
  sources?: AgentSource[];
  createdAt?: string;
}

function displayTime(value?: string): string {
  if (!value) return "";
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(parsed);
}

export default function AskPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AgentSessionInfo[]>([]);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [steps, setSteps] = useState<ProgressStep[]>([]);
  const [partial, setPartial] = useState("");

  const refreshSessions = useCallback(async (uid: string) => {
    try {
      setSessions(await agentApi.sessions(uid));
    } catch {
      /* 목록 실패는 대화를 막지 않는다 */
    }
  }, []);

  useEffect(() => {
    const uid = loadUserId();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage(브라우저 전용)를 마운트 후 1회 읽어야 SSR hydration 불일치가 없다
    setUserId(uid);
    refreshSessions(uid);
  }, [refreshSessions]);

  async function send() {
    const msg = input.trim();
    if (!msg || loading || !userId) return;
    setMessages((prev) => [...prev, { role: "user", content: msg, createdAt: new Date().toISOString() }]);
    setInput("");
    setLoading(true);
    setError(null);
    setSteps([]);
    setPartial("");
    try {
      const res = await streamAgent(
        "/agent/chat/stream",
        { message: msg, sessionId: sessionId ?? undefined, userId },
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
          createdAt: new Date().toISOString(),
        },
      ]);
      refreshSessions(userId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "에이전트 응답 실패");
    } finally {
      setLoading(false);
      setSteps([]);
      setPartial("");
    }
  }

  function newChat() {
    setMessages([]);
    setSessionId(null);
    setError(null);
  }

  async function openSession(sid: string) {
    if (!userId || loading) return;
    setError(null);
    try {
      const detail = await agentApi.session(sid, userId);
      setSessionId(sid);
      setMessages(
        detail.messages.map((m) => ({
          role: m.role,
          content: m.content,
          numbersGrounded: m.numbersGrounded,
          ungroundedNumbers: m.ungroundedNumbers,
          sources: m.sources,
          createdAt: m.createdAt,
        })),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "세션을 불러오지 못했습니다");
    }
  }

  async function removeSession(sid: string) {
    if (!userId) return;
    try {
      await agentApi.deleteSession(sid, userId);
      if (sid === sessionId) newChat();
      refreshSessions(userId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "세션 삭제 실패");
    }
  }

  return (
    <>
      <PageHeader
        title="문서 Q&A"
        description="에이전트가 수집 문서·웹을 스스로 검색해 답합니다 — 멀티턴 대화, 수치는 코퍼스 대조 검증"
      />

      {/* 어떻게 동작하나 · 응답 범위 */}
      <Card className="mb-6 border-sky-100/40 dark:border-sky-900/40 bg-sky-50/20 dark:bg-sky-950/20">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-sky-800 dark:text-sky-200">ⓘ 어떻게 동작하나 · 응답 범위</h2>
          <button
            onClick={() => setShowHelp((v) => !v)}
            className="text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            {showHelp ? "접기" : "펼치기"}
          </button>
        </div>
        {showHelp && (
          <div className="mt-3 grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-600 dark:text-sky-400">
                에이전트 동작
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-700 dark:text-zinc-300">
                <li>· hermes 에이전트가 질문을 보고 <strong className="text-zinc-900 dark:text-zinc-100">코퍼스 검색·웹 검색 도구를 스스로 조합</strong>해 답변</li>
                <li>· 코퍼스: 하이브리드 검색(BM25+동의어 ⊕ 의미 임베딩) — 수집 문서가 1차 근거</li>
                <li>· 이어지는 질문은 <strong className="text-zinc-900 dark:text-zinc-100">같은 세션에서 맥락을 기억</strong>(멀티턴)</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-600 dark:text-sky-400">
                수치 검증 · 출처
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-700 dark:text-zinc-300">
                <li>· 답변의 수치를 <strong className="text-zinc-900 dark:text-zinc-100">수집 문서와 자동 대조</strong>해 미확인 수치는 경고 표시</li>
                <li>· 경고 = 곧 오류는 아님 — <strong className="text-zinc-900 dark:text-zinc-100">웹 출처 수치</strong>일 수 있으니 원문 확인 권장</li>
                <li>· 답변마다 <strong className="text-zinc-900 dark:text-zinc-100">관련 수집 문서</strong>(출처)를 함께 표시</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-600 dark:text-sky-400">세션</p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-700 dark:text-zinc-300">
                <li>· 대화는 서버에 저장 — 왼쪽 목록에서 <strong className="text-zinc-900 dark:text-zinc-100">이전 대화를 이어서</strong> 할 수 있음</li>
                <li>· 세션은 사용자(브라우저)별로 분리 — 다른 사람에게 보이지 않음</li>
                <li>· 도구 사용 시 응답에 수십 초 소요</li>
              </ul>
            </div>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* 세션 목록(사용자별) */}
        <Card className="h-fit overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <div>
              <p className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">Q&A 이력</p>
              <p className="mt-0.5 text-[10px] text-zinc-500">저장된 대화 {sessions.length}건</p>
            </div>
            <button onClick={newChat} className="rounded-md bg-sky-600 px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-sky-500">
              + 새 대화
            </button>
          </div>
          <div className="max-h-[62vh] overflow-y-auto px-4 py-4">
            {sessions.length === 0 && (
              <p className="py-6 text-center text-xs text-zinc-500">저장된 대화가 없습니다.</p>
            )}
            {sessions.length > 0 && (
              <ol className="ml-1.5 flex flex-col gap-4 border-l-2 border-sky-200 pl-4 dark:border-sky-900">
                {sessions.map((s) => {
                  const active = s.id === sessionId;
                  return (
                    <li key={s.id} className="group relative">
                      <span
                        className={`absolute -left-[22px] top-2 h-2.5 w-2.5 rounded-full ring-2 ring-white dark:ring-zinc-950 ${
                          active ? "bg-sky-500" : "bg-zinc-300 dark:bg-zinc-700"
                        }`}
                      />
                      <button
                        onClick={() => openSession(s.id)}
                        className={`w-full rounded-lg px-2.5 py-2 text-left transition-colors ${
                          active
                            ? "bg-sky-50 ring-1 ring-sky-200 dark:bg-sky-950/50 dark:ring-sky-900"
                            : "hover:bg-zinc-100 dark:hover:bg-zinc-900"
                        }`}
                        title={s.title}
                      >
                        <span className="flex items-center gap-1.5">
                          <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-[10px] ${
                            active
                              ? "bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-300"
                              : "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                          }`}>
                            {displayTime(s.updatedAt)}
                          </span>
                          <span className="text-[10px] text-zinc-500">{s.messageCount}개 메시지</span>
                        </span>
                        <span className={`mt-1.5 block line-clamp-2 text-xs font-medium leading-5 ${
                          active ? "text-sky-900 dark:text-sky-100" : "text-zinc-800 dark:text-zinc-200"
                        }`}>
                          {s.title}
                        </span>
                      </button>
                      <button
                        onClick={() => removeSession(s.id)}
                        className="absolute right-1 top-1 hidden rounded px-1.5 py-1 text-[10px] text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400 group-hover:block"
                        title="삭제"
                      >
                        ✕
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
          {userId && (
            <p className="border-t border-zinc-200 px-4 py-2 text-[10px] text-zinc-400 dark:border-zinc-800 dark:text-zinc-600">
              사용자: <span className="font-mono">{userId}</span>
            </p>
          )}
        </Card>

        {/* 대화 영역 */}
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">
              에이전트 대화{" "}
              {sessionId && <span className="font-mono text-zinc-400 dark:text-zinc-600">· {sessionId.slice(0, 20)}…</span>}
            </p>
          </div>
          <div className="mt-3 flex flex-col gap-3">
            {messages.length === 0 && (
              <p className="text-sm text-zinc-500">
                수집 문서·웹을 스스로 검색해 답하는 에이전트입니다. 이어지는 질문은 맥락을 기억합니다.
              </p>
            )}
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="ml-auto max-w-[85%] rounded-xl rounded-br-sm bg-sky-600 px-4 py-3 text-sm text-white shadow-sm">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-sky-100">질문</p>
                  <p className="leading-relaxed">{m.content}</p>
                  {m.createdAt && <p className="mt-1.5 text-right text-[10px] text-sky-100">{displayTime(m.createdAt)}</p>}
                </div>
              ) : (
                <QaAnswerCard
                  key={i}
                  content={m.content}
                  numbersGrounded={m.numbersGrounded}
                  ungroundedNumbers={m.ungroundedNumbers}
                  sources={m.sources}
                  createdAt={displayTime(m.createdAt)}
                  turn={messages.slice(0, i + 1).filter((message) => message.role === "assistant").length}
                />
              ),
            )}
            {loading && <AgentProgressView steps={steps} partial={partial} />}
            {error && (
              <p className="rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-3 py-2 text-xs text-red-600 dark:text-red-400">
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
              className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim() || !userId}
              className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
            >
              {loading ? "조사 중…" : "보내기"}
            </button>
          </div>
        </Card>
      </div>
    </>
  );
}
