"use client";

import { useEffect, useState } from "react";
import { qualityApi, type QualitySummary } from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

const KIND_LABEL: Record<string, string> = {
  digest: "뉴스 다이제스트",
  topic: "주제 요약",
  competitor: "경쟁사 분석",
  report: "주간 리포트",
};
const KIND_ORDER = ["digest", "topic", "competitor", "report"];

function KindCard({ kind, stats }: { kind: string; stats: QualitySummary["byKind"][string] }) {
  const flagRate = stats.count > 0 ? Math.round((stats.flaggedCount / stats.count) * 100) : 0;
  return (
    <Card
      className={
        stats.flaggedCount > 0
          ? "border-amber-200/70 bg-amber-50/40 dark:border-zinc-800 dark:bg-zinc-900/60"
          : ""
      }
    >
      <p className="text-xs text-zinc-500">{KIND_LABEL[kind] ?? kind}</p>
      <p className="mt-1 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">{stats.count}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-emerald-600 dark:text-emerald-400">👍 {stats.up}</span>
        <span className="text-red-600 dark:text-red-400">👎 {stats.down}</span>
        {stats.flaggedCount > 0 && (
          <span className="text-amber-600 dark:text-amber-400">⚠ 검토 필요 {stats.flaggedCount}건 ({flagRate}%)</span>
        )}
      </div>
    </Card>
  );
}

export default function QualityPage() {
  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    qualityApi
      .summary()
      .then(setSummary)
      .catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"));
  }, []);

  return (
    <>
      <PageHeader
        title="품질"
        description="자기개선 loop — 종류별 피드백(👍/👎)과 근거 검증 실패를 추적하고, 최근 부정 피드백은 다음 생성 프롬프트에 자동 반영됩니다"
      />

      {error && (
        <div className="mb-5 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {summary && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {KIND_ORDER.map((k) => (
              <KindCard key={k} kind={k} stats={summary.byKind[k]} />
            ))}
          </div>

          <Card>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              최근 근거 검증 실패 ({summary.recentFlagged.length})
            </h2>
            {summary.recentFlagged.length === 0 ? (
              <p className="mt-3 text-xs text-zinc-500">
                최근 생성물 중 미근거 수치·근거 없는 서술이 잡힌 것이 없습니다.
              </p>
            ) : (
              <table className="mt-3 w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-zinc-200 dark:border-zinc-800 text-zinc-500">
                    <th className="pb-2 font-medium">종류</th>
                    <th className="pb-2 font-medium">제목</th>
                    <th className="pb-2 font-medium">미근거 수치</th>
                    <th className="pb-2 font-medium">근거 없는 서술</th>
                    <th className="pb-2 font-medium">생성일</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.recentFlagged.map((f) => (
                    <tr key={f.id} className="border-b border-zinc-100 dark:border-zinc-900 last:border-0">
                      <td className="py-2"><Tag>{KIND_LABEL[f.kind] ?? f.kind}</Tag></td>
                      <td className="py-2 text-zinc-900 dark:text-zinc-100">{f.title}</td>
                      <td className="py-2 text-amber-600 dark:text-amber-400">{f.ungroundedCount || "—"}</td>
                      <td className="py-2 text-amber-600 dark:text-amber-400">{f.unsupportedCount || "—"}</td>
                      <td className="py-2 font-mono text-zinc-500">{f.createdAt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </>
  );
}
