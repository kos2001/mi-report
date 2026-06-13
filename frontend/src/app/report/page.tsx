"use client";

import { useState } from "react";
import { reportApi, type GeneratedReport } from "@/lib/api";
import { Card, ImpactBadge, PageHeader, Tag } from "@/components/ui";

export default function ReportPage() {
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setReport(
        await reportApi.generate({
          period: "최근 수집 문서",
          maxTopics: 3,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "리포트 생성 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="주간 MI 리포트"
        description="다이제스트·주제 History·총평을 묶어 이번 주 리포트 초안을 한 번에 생성"
      />

      <Card className="mb-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">AI 주간 리포트 생성</h2>
            <p className="mt-1 text-xs text-zinc-500">
              수집 문서로 다이제스트와 주제 요약을 생성하고 총평까지 종합합니다. (다중 호출 — 시간이 걸릴 수 있음)
            </p>
          </div>
          <button
            onClick={generate}
            disabled={loading}
            className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
          >
            {loading ? "생성 중…" : "AI 리포트 생성"}
          </button>
        </div>
        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </Card>

      {report && (
        <div className="flex flex-col gap-6">
          {/* 총평 */}
          <Card className="border-sky-900/50 bg-sky-950/20">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-50">
                제{report.issueNo}호 총평
              </h2>
              <span className="text-xs text-zinc-500">
                {report.period} · 생성 {report.generatedAt}
              </span>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
              {report.overview}
            </p>
          </Card>

          {/* 다이제스트 */}
          {report.digest && report.digest.items.length > 0 && (
            <section>
              <h3 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                뉴스 다이제스트 ({report.digest.items.length})
              </h3>
              <div className="flex flex-col gap-3">
                {report.digest.items.map((item) => (
                  <Card key={item.id}>
                    <div className="flex items-start justify-between gap-4">
                      <h4 className="text-sm font-semibold text-zinc-100">{item.title}</h4>
                      <ImpactBadge level={item.impact} />
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-zinc-300">{item.summary}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.tags.map((t) => (
                        <Tag key={t}>{t}</Tag>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          )}

          {/* 주제 요약 */}
          {report.topics.length > 0 && (
            <section>
              <h3 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                주제별 요약 ({report.topics.length})
              </h3>
              <div className="flex flex-col gap-3">
                {report.topics.map((t) => (
                  <Card key={t.id}>
                    <div className="flex items-center gap-2">
                      <Tag>{t.category}</Tag>
                      <h4 className="text-sm font-semibold text-zinc-50">{t.title}</h4>
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-zinc-300">{t.summary}</p>
                    <p className="mt-2 rounded-lg border border-sky-900/40 bg-sky-950/30 px-3 py-2 text-sm leading-relaxed text-zinc-200">
                      {t.insight}
                    </p>
                  </Card>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </>
  );
}
