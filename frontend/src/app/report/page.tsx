"use client";

import { useState } from "react";
import { reportApi, type GeneratedReport } from "@/lib/api";
import { Card, ImpactBadge, PageHeader, Tag } from "@/components/ui";
import { ArtifactHistoryPanel } from "@/components/artifact-history";

// 기본 템플릿(서버와 동일 토큰). 비우면 서버 기본 템플릿이 적용된다.
const TEMPLATE_PLACEHOLDER = `# 주간 MI 리포트 제{{issue_no}}호

**기간**: {{period}}  |  **생성일**: {{generated_at}}

## 총평
{{overview}}

## Top Priority / Risk
{{priority_risk}}

## 치명적 관리포인트
{{critical_points}}

## 뉴스 다이제스트
{{digest}}

## 주제별 동향
{{topics}}`;

function downloadMarkdown(filename: string, markdown: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ReportPage() {
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [docBusy, setDocBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTemplate, setShowTemplate] = useState(false);
  const [template, setTemplate] = useState("");

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

  // 리포트를 생성하고 (선택) 템플릿을 적용한 Markdown 문서를 내려받는다.
  async function generateDocument() {
    setDocBusy(true);
    setError(null);
    try {
      const r = await reportApi.document({
        period: "최근 수집 문서",
        maxTopics: 3,
        template: template.trim() || undefined,
      });
      downloadMarkdown(r.filename, r.markdown);
      setReport(r.report);
    } catch (e) {
      setError(e instanceof Error ? e.message : "문서 생성 실패");
    } finally {
      setDocBusy(false);
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
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={generate}
              disabled={loading || docBusy}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition-colors hover:bg-zinc-700 disabled:opacity-40"
            >
              {loading ? "생성 중…" : "AI 리포트 생성"}
            </button>
            <button
              onClick={generateDocument}
              disabled={loading || docBusy}
              title="리포트를 생성하고 템플릿을 적용한 Markdown 문서(.md)로 내려받습니다"
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
            >
              {docBusy ? "문서 생성 중…" : "문서(.md) 생성·다운로드"}
            </button>
          </div>
        </div>

        {/* 템플릿 입력(선택) — {{토큰}} 으로 문서 형식을 정의 */}
        <div className="mt-3 border-t border-zinc-800 pt-3">
          <button
            onClick={() => setShowTemplate((v) => !v)}
            className="text-xs text-zinc-400 hover:text-zinc-200"
          >
            {showTemplate ? "▾" : "▸"} 문서 템플릿 입력 (선택) — 비우면 기본 템플릿
          </button>
          {showTemplate && (
            <div className="mt-2">
              <textarea
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                placeholder={TEMPLATE_PLACEHOLDER}
                rows={9}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-xs text-zinc-100 outline-none focus:border-sky-500"
              />
              <p className="mt-1 text-[11px] text-zinc-500">
                토큰: <code className="text-zinc-400">{"{{issue_no}} {{period}} {{generated_at}} {{overview}} {{priority_risk}} {{critical_points}} {{digest}} {{topics}}"}</code>
              </p>
            </div>
          )}
        </div>

        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </Card>

      <div className="mb-8">
        <ArtifactHistoryPanel
          kind="report"
          onSelect={(a) => setReport(a.payload as unknown as GeneratedReport)}
          emptyLabel="아직 생성된 리포트가 없습니다."
        />
      </div>

      {report && (
        <div className="flex flex-col gap-6">
          {/* 환각 방어: 미근거 수치 검토 경고 */}
          {report.ungroundedNumbers && report.ungroundedNumbers.length > 0 && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              ⚠ 검토 필요 — 다음 수치는 제공 문서에서 그대로 확인되지 않았습니다:{" "}
              <span className="font-mono">{report.ungroundedNumbers.join(", ")}</span>
            </p>
          )}

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
            {report.overviewUnsupportedClaims && report.overviewUnsupportedClaims.length > 0 && (
              <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                ⚠ 검토 필요 — 다음 총평 서술은 근거가 확인되지 않았습니다:{" "}
                {report.overviewUnsupportedClaims.join(" / ")}
              </p>
            )}
          </Card>

          {/* Top Priority / Risk (심층분석 agent) */}
          {((report.priorities && report.priorities.length > 0) ||
            (report.risks && report.risks.length > 0)) && (
            <section>
              <h3 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                Top Priority / Risk
              </h3>
              <div className="grid gap-3 md:grid-cols-2">
                {report.priorities && report.priorities.length > 0 && (
                  <Card>
                    <h4 className="text-sm font-semibold text-emerald-400">Priority</h4>
                    <ol className="mt-2 flex flex-col gap-2 text-sm text-zinc-300">
                      {report.priorities.map((p, i) => (
                        <li key={i}>
                          <span className="font-medium text-zinc-100">{p.rank}. {p.title}</span>
                          {!p.evidenceGrounded && <span className="ml-1 text-amber-400">⚠ 근거 미확인</span>}
                          <p className="text-xs text-zinc-400">{p.rationale}</p>
                        </li>
                      ))}
                    </ol>
                  </Card>
                )}
                {report.risks && report.risks.length > 0 && (
                  <Card>
                    <h4 className="text-sm font-semibold text-red-400">Risk</h4>
                    <ol className="mt-2 flex flex-col gap-2 text-sm text-zinc-300">
                      {report.risks.map((r, i) => (
                        <li key={i}>
                          <span className="font-medium text-zinc-100">{r.rank}. {r.title}</span>
                          {!r.evidenceGrounded && <span className="ml-1 text-amber-400">⚠ 근거 미확인</span>}
                          <p className="text-xs text-zinc-400">{r.rationale}</p>
                        </li>
                      ))}
                    </ol>
                  </Card>
                )}
              </div>
            </section>
          )}

          {/* 치명적 관리포인트 (심층분석 agent) */}
          {report.criticalPoints && report.criticalPoints.length > 0 && (
            <section>
              <h3 className="mb-3 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                치명적 관리포인트 ({report.criticalPoints.length})
              </h3>
              <div className="flex flex-col gap-3">
                {report.criticalPoints.map((c, i) => (
                  <Card key={i}>
                    <h4 className="text-sm font-semibold text-zinc-100">
                      {c.title}
                      {!c.evidenceGrounded && <span className="ml-1 text-amber-400">⚠ 근거 미확인</span>}
                    </h4>
                    <dl className="mt-2 flex flex-col gap-1 text-xs text-zinc-400">
                      {c.rootCause && <div><dt className="inline font-medium text-zinc-300">근본원인: </dt>{c.rootCause}</div>}
                      {c.chainEffect && <div><dt className="inline font-medium text-zinc-300">연쇄효과: </dt>{c.chainEffect}</div>}
                      {c.decisionNeeded && <div><dt className="inline font-medium text-zinc-300">필요한 결정: </dt>{c.decisionNeeded}</div>}
                    </dl>
                  </Card>
                ))}
              </div>
            </section>
          )}

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
                    {((t.ungroundedNumbers && t.ungroundedNumbers.length > 0) ||
                      (t.unverifiedHistoryCount ?? 0) > 0) && (
                      <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                        {t.ungroundedNumbers && t.ungroundedNumbers.length > 0 && (
                          <>⚠ 미근거 수치: <span className="font-mono">{t.ungroundedNumbers.join(", ")}</span></>
                        )}
                        {(t.unverifiedHistoryCount ?? 0) > 0 && (
                          <span className="block">⚠ 출처 미검증 이력 {t.unverifiedHistoryCount}건 — 귀속 확인 필요</span>
                        )}
                      </p>
                    )}
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
