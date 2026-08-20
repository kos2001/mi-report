"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Source } from "@/lib/api";
import { Card } from "@/components/ui";
import { SourceOperationalStatus } from "@/components/source-operational-status";

export function PipelineStatus() {
  const [sources, setSources] = useState<Source[]>([]);
  const [docCount, setDocCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const activeCount = sources.filter((source) => source.operational.effectiveActive).length;
  const attentionCount = sources.filter((source) =>
    ["setup", "error", "stale", "warning"].includes(source.operational.state),
  ).length;

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { sources, documentCount } = await api.collectionOverview();
        if (!alive) return;
        setSources(sources);
        setDocCount(documentCount);
        setError(null);
      } catch {
        if (alive) setError("백엔드 미연결 (http://localhost:8000)");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <Card className="p-0">
      {error ? (
        <p className="px-5 py-6 text-sm text-amber-600/80 dark:text-amber-400/80">
          {error} — 백엔드를 실행하면 실시간 소스 상태가 표시됩니다.
        </p>
      ) : loading ? (
        <p className="px-5 py-6 text-sm text-zinc-500">불러오는 중…</p>
      ) : (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200 dark:border-zinc-800 text-left text-xs text-zinc-500">
                <th className="px-5 py-3 font-medium">소스</th>
                <th className="px-5 py-3 font-medium">실제 운영 상태</th>
                <th className="px-5 py-3 font-medium">최근 실행</th>
                <th className="px-5 py-3 text-right font-medium">누적 문서</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b border-zinc-200/60 dark:border-zinc-800/60 last:border-0">
                  <td className="px-5 py-3 text-zinc-800 dark:text-zinc-200">{s.name}</td>
                  <td className="px-5 py-3">
                    <SourceOperationalStatus source={s} showReason />
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-zinc-600 dark:text-zinc-400">
                    {s.lastRun ?? "—"}
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-xs text-zinc-700 dark:text-zinc-300">
                    {s.count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-zinc-200 dark:border-zinc-800 px-5 py-2.5 text-[11px] text-zinc-500">
            <span>
              소스 {sources.length}개 · 실제 활성 {activeCount}개 · 점검 필요 {attentionCount}개 · 수집 문서 {docCount ?? "—"}건
            </span>
            <Link href="/collection" className="text-sky-600 dark:text-sky-400 hover:underline">
              데이터 수집 관리 →
            </Link>
          </div>
        </>
      )}
    </Card>
  );
}
