"use client";

import { useState } from "react";
import { ragApi, type RagAnswer } from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <>
      <PageHeader
        title="문서 Q&A"
        description="수집된 문서를 근거로 자연어 질문에 답합니다 — 답변은 [문서 N] 근거 인용 포함"
      />

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
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
            {answer.answer}
          </p>
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
  );
}
