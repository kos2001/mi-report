"use client";

import { useState } from "react";
import { agentApi, ragApi, type RagAnswer } from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";

interface AgentMessage {
  role: "user" | "assistant";
  content: string;
}

export default function AskPage() {
  const [mode, setMode] = useState<"rag" | "agent">("rag");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(true);

  // 에이전트 대화(멀티턴) 상태 — sessionId 로 hermes 세션을 잇는다.
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [agentInput, setAgentInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

  async function ask() {
    const qq = question.trim();
    if (!qq) return;
    setLoading(true);
    setError(null);
    try {
      setAnswer(await ragApi.query({ question: qq }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "답변 생성 실패");
    } finally {
      setLoading(false);
    }
  }

  async function sendAgent() {
    const msg = agentInput.trim();
    if (!msg || agentLoading) return;
    setAgentMessages((prev) => [...prev, { role: "user", content: msg }]);
    setAgentInput("");
    setAgentLoading(true);
    setAgentError(null);
    try {
      const res = await agentApi.chat({ message: msg, sessionId: sessionId ?? undefined });
      setSessionId(res.sessionId);
      setAgentMessages((prev) => [...prev, { role: "assistant", content: res.answer }]);
    } catch (e) {
      setAgentError(e instanceof Error ? e.message : "에이전트 응답 실패");
    } finally {
      setAgentLoading(false);
    }
  }

  function resetAgent() {
    setAgentMessages([]);
    setSessionId(null);
    setAgentError(null);
  }

  return (
    <>
      <PageHeader
        title="문서 Q&A"
        description="수집된 문서를 근거로 자연어 질문에 답합니다 — 답변은 [문서 N] 근거 인용 포함"
      />

      {/* 모드 전환: 완결형 RAG ↔ hermes 에이전트 대화 */}
      <div className="mb-6 flex items-center gap-2">
        <button
          onClick={() => setMode("rag")}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            mode === "rag"
              ? "bg-sky-600 text-white"
              : "border border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
          }`}
        >
          문서 Q&A
        </button>
        <button
          onClick={() => setMode("agent")}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            mode === "agent"
              ? "bg-sky-600 text-white"
              : "border border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
          }`}
        >
          에이전트 대화
        </button>
        <span className="text-xs text-zinc-500">
          {mode === "rag"
            ? "수집 문서 안에서만 · 단발 질문"
            : "hermes 에이전트 · 멀티턴 · 코퍼스+웹 검색 도구 사용"}
        </span>
      </div>

      {mode === "agent" && (
        <Card className="mb-8">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">
              에이전트 대화 {sessionId && <span className="font-mono text-zinc-600">· {sessionId.slice(0, 20)}…</span>}
            </p>
            {agentMessages.length > 0 && (
              <button onClick={resetAgent} className="text-xs text-zinc-400 hover:text-zinc-200">
                새 대화
              </button>
            )}
          </div>
          <div className="mt-3 flex flex-col gap-3">
            {agentMessages.length === 0 && (
              <p className="text-sm text-zinc-500">
                수집 문서·웹을 스스로 검색해 답하는 에이전트입니다. 이어지는 질문은 맥락을 기억합니다.
              </p>
            )}
            {agentMessages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="self-end rounded-lg bg-sky-950/60 px-3 py-2 text-sm text-sky-100">
                  {m.content}
                </div>
              ) : (
                <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                  <Markdown text={m.content} className="text-sm text-zinc-200" />
                </div>
              ),
            )}
            {agentLoading && <p className="text-sm text-zinc-500">에이전트가 조사 중… (도구 사용 시 수십 초)</p>}
            {agentError && (
              <p className="rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
                {agentError}
              </p>
            )}
          </div>
          <div className="mt-4 flex items-center gap-2">
            <input
              value={agentInput}
              onChange={(e) => setAgentInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !agentLoading) sendAgent();
              }}
              placeholder="예: 이번 주 HBM 관련 수집 문서 핵심만 정리해줘. 최신 뉴스도 보강해서."
              className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
            />
            <button
              onClick={sendAgent}
              disabled={agentLoading || !agentInput.trim()}
              className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
            >
              {agentLoading ? "조사 중…" : "보내기"}
            </button>
          </div>
        </Card>
      )}

      {mode === "rag" && (
      <>

      {/* 어떻게 동작하나 · 응답 범위 (입력→DB화, 검색·응답 범위, 한계) */}
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
                입력 → DB 저장
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-300">
                <li>· 입력: 업로드 · URL 수집(뉴스·증권사·컨센서스) · Confluence · COM 인제스트</li>
                <li>· 저장: SQLite <code className="text-zinc-400">documents</code>(제목·출처·주제·수집일) + 본문은 파일(.txt)</li>
                <li>· 색인: 제목·주제·본문 <strong className="text-zinc-100">FTS5(BM25)</strong> + <strong className="text-zinc-100">의미 임베딩 벡터</strong>(로컬 e5-large)</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
                검색 → 응답 범위
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-300">
                <li>· 질문 → <strong className="text-zinc-100">하이브리드 검색</strong>(BM25+동의어 확장 ⊕ 의미 임베딩, RRF 결합) → <strong className="text-zinc-100">LLM 재랭킹</strong> → 상위 N건만 컨텍스트</li>
                <li>· <strong className="text-zinc-100">수집 문서 안에서만</strong> 답변(외부·일반 지식 사용 안 함)</li>
                <li>· 답변은 <code className="text-zinc-400">[문서 N]</code> 인용, <strong className="text-zinc-100">실제 인용된 문서만</strong> 근거 표시</li>
                <li>· 문서에 없으면 “확인되지 않음”</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">한계</p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-300">
                <li>· 어휘+의미 하이브리드 검색 — 사전 밖 희귀 패러프레이즈는 코퍼스·모델 규모에 따라 한계</li>
                <li>· 텍스트 본문 위주 — 바이너리/이미지 추출은 제한적</li>
                <li>· 최신성 = 마지막 수집 시점(실시간 웹검색 아님)</li>
              </ul>
            </div>
          </div>
        )}
      </Card>

      <Card className="mb-8">
        <div className="flex items-center gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !loading) ask();
            }}
            placeholder="예: HBM4 양산 시점과 증권사 전망은?"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
          />
          <button
            onClick={ask}
            disabled={loading || !question.trim()}
            className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
          >
            {loading ? "생성 중…" : "질문"}
          </button>
        </div>
        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </Card>

      {answer && (
        <Card>
          <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">답변</p>
          {answer.numbersGrounded === false && answer.ungroundedNumbers && answer.ungroundedNumbers.length > 0 && (
            <p className="mt-2 rounded-lg border border-amber-900/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
              ⚠ 환각 주의 — 다음 수치는 제공 문서에서 그대로 확인되지 않았습니다(검토 필요):{" "}
              <span className="font-mono">{answer.ungroundedNumbers.join(", ")}</span>
            </p>
          )}
          <Markdown text={answer.answer} className="mt-2 text-sm text-zinc-200" />
          <div className="mt-4 border-t border-zinc-800 pt-3">
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
              근거 문서 ({answer.usedDocCount})
            </p>
            <ul className="flex flex-col gap-1.5">
              {answer.sources.map((s) => (
                <li key={s.index} className="flex items-center gap-2 text-sm text-zinc-300">
                  <Tag>문서 {s.index}</Tag>
                  <span>{s.title}</span>
                  <span className="text-xs text-zinc-500">· {s.source}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}
      </>
      )}
    </>
  );
}
