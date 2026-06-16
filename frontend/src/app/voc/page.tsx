"use client";

import { useCallback, useEffect, useState } from "react";
import {
  vocApi,
  VOC_CHANNELS,
  VOC_SENTIMENTS,
  VOC_PRIORITIES,
  VOC_STATUSES,
  type VocItem,
  type VocSummary,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

const SENTIMENT_COLOR: Record<string, string> = {
  긍정: "text-emerald-400",
  중립: "text-zinc-400",
  부정: "text-red-400",
};
const PRIORITY_COLOR: Record<string, string> = {
  상: "border-red-800/60 bg-red-950/40 text-red-300",
  중: "border-amber-800/60 bg-amber-950/40 text-amber-300",
  하: "border-zinc-700 bg-zinc-800 text-zinc-400",
};

export default function VocPage() {
  const [items, setItems] = useState<VocItem[]>([]);
  const [summary, setSummary] = useState<VocSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 입력 폼
  const [customer, setCustomer] = useState("");
  const [content, setContent] = useState("");
  const [channel, setChannel] = useState<string>("영업");
  const [sentiment, setSentiment] = useState<string>("중립");
  const [priority, setPriority] = useState<string>("중");
  const [busy, setBusy] = useState(false);

  const [reloadKey, setReloadKey] = useState(0);
  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await vocApi.list(statusFilter ? { status: statusFilter } : undefined);
        if (!alive) return;
        setItems(d.voc);
        setSummary(d.summary);
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "백엔드 연결 실패 (http://localhost:8000)");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [reloadKey, statusFilter]);

  async function add() {
    if (!customer.trim() || !content.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await vocApi.create({ customer: customer.trim(), content: content.trim(), channel, sentiment, priority });
      setCustomer("");
      setContent("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "VOC 등록 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="VOC"
        description="고객의 목소리(요청·불만·문의·피드백)를 채널·감정·우선순위로 기록하고 처리 상태를 추적"
      />

      {error && (
        <div className="mb-5 rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* 요약 */}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card>
            <p className="text-xs text-zinc-500">전체</p>
            <p className="mt-1 text-2xl font-semibold text-zinc-50">{summary.total}</p>
          </Card>
          {VOC_STATUSES.map((s) => (
            <Card key={s}>
              <p className="text-xs text-zinc-500">{s}</p>
              <p className="mt-1 text-2xl font-semibold text-zinc-50">{summary.byStatus[s] ?? 0}</p>
            </Card>
          ))}
        </div>
      )}

      {/* 입력 폼 */}
      <Card className="mb-6">
        <p className="mb-3 text-sm font-medium text-zinc-200">VOC 등록</p>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <input
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
              placeholder="고객/현장 (예: A고객사, 영업팀)"
              className="w-56 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
            />
            <select value={channel} onChange={(e) => setChannel(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500">
              {VOC_CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select value={sentiment} onChange={(e) => setSentiment(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500">
              {VOC_SENTIMENTS.map((s) => <option key={s} value={s}>{`감정: ${s}`}</option>)}
            </select>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500">
              {VOC_PRIORITIES.map((p) => <option key={p} value={p}>{`우선순위: ${p}`}</option>)}
            </select>
          </div>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="VOC 내용 (요청·불만·문의·피드백)"
            rows={3}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
          />
          <div className="flex justify-end">
            <button
              onClick={add}
              disabled={busy || !customer.trim() || !content.trim()}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
            >
              {busy ? "등록 중…" : "등록"}
            </button>
          </div>
        </div>
      </Card>

      {/* 상태 필터 */}
      <div className="mb-3 flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/40 p-1 text-sm">
        <button
          onClick={() => setStatusFilter("")}
          className={`rounded-md px-3 py-1.5 transition-colors ${statusFilter === "" ? "bg-zinc-800 font-medium text-zinc-50" : "text-zinc-400 hover:text-zinc-200"}`}
        >
          전체
        </button>
        {VOC_STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-md px-3 py-1.5 transition-colors ${statusFilter === s ? "bg-zinc-800 font-medium text-zinc-50" : "text-zinc-400 hover:text-zinc-200"}`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* 목록 */}
      {loading ? (
        <p className="text-sm text-zinc-500">불러오는 중…</p>
      ) : items.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-400">등록된 VOC 가 없습니다.</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((v) => (
            <Card key={v.id} className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-zinc-100">{v.customer}</span>
                  <Tag>{v.channel}</Tag>
                  <span className={`text-xs ${SENTIMENT_COLOR[v.sentiment] ?? "text-zinc-400"}`}>● {v.sentiment}</span>
                  <span className={`rounded-md border px-1.5 py-0.5 text-[11px] ${PRIORITY_COLOR[v.priority] ?? ""}`}>
                    {v.priority}
                  </span>
                  <span className="text-[11px] text-zinc-500">{v.createdAt}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">{v.content}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <select
                  value={v.status}
                  onChange={(e) => vocApi.updateStatus(v.id, e.target.value).then(refresh)}
                  title="처리 상태 변경"
                  className="rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-sky-500"
                >
                  {VOC_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <button
                  onClick={() => vocApi.remove(v.id).then(refresh)}
                  className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:text-red-400"
                >
                  삭제
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
