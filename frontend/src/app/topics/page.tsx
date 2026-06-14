"use client";

import { useEffect, useState } from "react";
import { topicsApi, type GeneratedTopic, type TopicListItem } from "@/lib/api";
import { topics } from "@/lib/data";
import { Card, PageHeader } from "@/components/ui";

type TopicLike = {
  id: string;
  title: string;
  category: string;
  summary: string;
  insight: string;
  sourceCount: number;
  updatedAt: string;
  history: { date: string; event: string; source: string }[];
};

// 카테고리별 색상 — 주제 카드를 한눈에 구분할 수 있게 한다.
type CatStyle = { bar: string; badge: string; insight: string; insightText: string; dot: string; line: string };
const CATEGORY_STYLE: Record<string, CatStyle> = {
  "수요/시황": {
    bar: "bg-sky-500", badge: "border-sky-800 bg-sky-950/50 text-sky-300",
    insight: "border-sky-900/40 bg-sky-950/30", insightText: "text-sky-400",
    dot: "bg-sky-500", line: "border-sky-900/50",
  },
  "반도체 제조": {
    bar: "bg-amber-500", badge: "border-amber-800 bg-amber-950/50 text-amber-300",
    insight: "border-amber-900/40 bg-amber-950/30", insightText: "text-amber-400",
    dot: "bg-amber-500", line: "border-amber-900/50",
  },
  "반도체 설계": {
    bar: "bg-emerald-500", badge: "border-emerald-800 bg-emerald-950/50 text-emerald-300",
    insight: "border-emerald-900/40 bg-emerald-950/30", insightText: "text-emerald-400",
    dot: "bg-emerald-500", line: "border-emerald-900/50",
  },
  SET: {
    bar: "bg-violet-500", badge: "border-violet-800 bg-violet-950/50 text-violet-300",
    insight: "border-violet-900/40 bg-violet-950/30", insightText: "text-violet-400",
    dot: "bg-violet-500", line: "border-violet-900/50",
  },
};
const DEFAULT_STYLE: CatStyle = {
  bar: "bg-zinc-500", badge: "border-zinc-700 bg-zinc-800 text-zinc-300",
  insight: "border-zinc-700 bg-zinc-800/40", insightText: "text-zinc-400",
  dot: "bg-zinc-500", line: "border-zinc-800",
};

function TopicCard({ topic, generated }: { topic: TopicLike; generated?: boolean }) {
  const st = CATEGORY_STYLE[topic.category] ?? DEFAULT_STYLE;
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
      {/* 카테고리 색상 상단 바 */}
      <div className={`h-1 ${st.bar}`} />
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${st.badge}`}>
                {topic.category}
              </span>
              <span className="rounded-md bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300">
                소스 {topic.sourceCount}건
              </span>
              <span className="rounded-md bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300">
                사건 {topic.history.length}개
              </span>
              <span className="text-[11px] text-zinc-500">· 업데이트 {topic.updatedAt}</span>
            </div>
            <h2 className="mt-2 text-base font-semibold text-zinc-50">{topic.title}</h2>
          </div>
          {generated && (
            <span className="shrink-0 rounded-full border border-sky-900/60 bg-sky-950/40 px-3 py-1 text-xs text-sky-400">
              AI 생성
            </span>
          )}
        </div>

        <p className="mt-3 text-sm leading-relaxed text-zinc-300">{topic.summary}</p>

        <div className={`mt-4 rounded-lg border px-4 py-3 ${st.insight}`}>
          <p className={`text-[11px] font-medium uppercase tracking-wide ${st.insightText}`}>
            Insight — SET/반도체 시황 연계
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-zinc-200">{topic.insight}</p>
        </div>

        <div className="mt-4">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
            History · {topic.history.length}개
          </p>
          {topic.history.length === 0 ? (
            <p className="text-sm text-zinc-500">이력 항목 없음</p>
          ) : (
            <ol className={`flex flex-col gap-3 border-l-2 pl-4 ${st.line}`}>
              {topic.history.map((h) => (
                <li key={h.date + h.event} className="relative">
                  <span
                    className={`absolute -left-[22px] top-1 h-2.5 w-2.5 rounded-full ring-2 ring-zinc-900 ${st.dot}`}
                  />
                  <span className="inline-block rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
                    {h.date}
                  </span>
                  <p className="mt-1 text-sm text-zinc-300">
                    {h.event} <span className="text-xs text-zinc-500">({h.source})</span>
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TopicsPage() {
  const [available, setAvailable] = useState<TopicListItem[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [generated, setGenerated] = useState<GeneratedTopic | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    topicsApi
      .list()
      .then((list) => {
        if (!alive) return;
        setAvailable(list);
        if (list.length > 0) setSelected(list[0].topic);
      })
      .catch(() => {
        /* 백엔드 미연동 시 주제 선택은 비활성 — 목업은 그대로 노출 */
      });
    return () => {
      alive = false;
    };
  }, []);

  async function handleGenerate() {
    if (!selected) return;
    setLoading(true);
    setError(null);
    try {
      setGenerated(await topicsApi.summarize({ topic: selected }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "주제 요약 생성 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="주제별 History"
        description="조사기관·증권사 자료와 뉴스 센싱 누적 정보 기반 주제별 이력 및 인사이트"
      />

      {/* AI 주제 요약 생성 패널 */}
      <Card className="mb-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">AI 주제 요약 생성</h2>
            <p className="mt-1 text-xs text-zinc-500">
              수집 문서에 부여된 주제를 선택해 누적 이력·인사이트를 생성합니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              disabled={available.length === 0}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 disabled:opacity-50"
            >
              {available.length === 0 ? (
                <option value="">주제 없음 (문서에 주제 부여 필요)</option>
              ) : (
                available.map((t) => (
                  <option key={t.topic} value={t.topic}>
                    {t.topic} ({t.count})
                  </option>
                ))
              )}
            </select>
            <button
              onClick={handleGenerate}
              disabled={loading || !selected}
              className="shrink-0 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "생성 중…" : "AI 요약 생성"}
            </button>
          </div>
        </div>
        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </Card>

      <div className="flex flex-col gap-5">
        {generated && <TopicCard topic={generated} generated />}
        {topics.map((topic) => (
          <TopicCard key={topic.id} topic={topic} />
        ))}
      </div>
    </>
  );
}
