"use client";

import { useEffect, useState } from "react";
import { topicsApi, type GeneratedTopic, type TopicListItem } from "@/lib/api";
import { topics } from "@/lib/data";
import { Card, PageHeader, Tag } from "@/components/ui";

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

function TopicCard({ topic, generated }: { topic: TopicLike; generated?: boolean }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Tag>{topic.category}</Tag>
            <span className="text-[11px] text-zinc-500">
              소스 {topic.sourceCount}건 · 업데이트 {topic.updatedAt}
            </span>
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

      <div className="mt-4 rounded-lg border border-sky-900/40 bg-sky-950/30 px-4 py-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
          Insight — SET/반도체 시황 연계
        </p>
        <p className="mt-1.5 text-sm leading-relaxed text-zinc-200">{topic.insight}</p>
      </div>

      <div className="mt-4">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
          History
        </p>
        {topic.history.length === 0 ? (
          <p className="text-sm text-zinc-500">이력 항목 없음</p>
        ) : (
          <ol className="flex flex-col gap-2 border-l border-zinc-800 pl-4">
            {topic.history.map((h) => (
              <li key={h.date + h.event} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-zinc-600" />
                <span className="font-mono text-xs text-zinc-500">{h.date}</span>
                <p className="text-sm text-zinc-300">
                  {h.event} <span className="text-xs text-zinc-500">({h.source})</span>
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
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
