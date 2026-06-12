"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Source } from "@/lib/api";
import { Card } from "@/components/ui";

function statusColor(status: string) {
  if (status === "정상") return "text-emerald-400";
  if (status === "지연") return "text-amber-400";
  if (status === "오류") return "text-red-400";
  return "text-zinc-400";
}

export function PipelineStatus() {
  const [sources, setSources] = useState<Source[]>([]);
  const [docCount, setDocCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [s, d] = await Promise.all([api.listSources(), api.listDocuments()]);
        if (!alive) return;
        setSources(s);
        setDocCount(d.length);
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
        <p className="px-5 py-6 text-sm text-amber-400/80">
          {error} — 백엔드를 실행하면 실시간 소스 상태가 표시됩니다.
        </p>
      ) : loading ? (
        <p className="px-5 py-6 text-sm text-zinc-500">불러오는 중…</p>
      ) : (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                <th className="px-5 py-3 font-medium">소스</th>
                <th className="px-5 py-3 font-medium">상태</th>
                <th className="px-5 py-3 font-medium">최근 실행</th>
                <th className="px-5 py-3 text-right font-medium">누적 문서</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b border-zinc-800/60 last:border-0">
                  <td className="px-5 py-3 text-zinc-200">{s.name}</td>
                  <td className="px-5 py-3">
                    <span className={statusColor(s.status)}>● {s.status}</span>
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-zinc-400">
                    {s.lastRun ?? "—"}
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-xs text-zinc-300">
                    {s.count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-zinc-800 px-5 py-2.5 text-[11px] text-zinc-500">
            <span>
              소스 {sources.length}개 · 수집 문서 {docCount ?? "—"}건 (실시간)
            </span>
            <Link href="/collection" className="text-sky-400 hover:underline">
              데이터 수집 관리 →
            </Link>
          </div>
        </>
      )}
    </Card>
  );
}
