"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  artifactsApi,
  digestApi,
  topicsApi,
  type GeneratedDigest,
  type Source,
  type TopicListItem,
} from "@/lib/api";
import { Card, ImpactBadge, PageHeader } from "@/components/ui";
import { PipelineStatus } from "@/components/pipeline-status";

// 서비스 흐름 단계 색상 (Tailwind 가 스캔하도록 리터럴 클래스만 사용).
// bright 모드는 단계별 액센트 틴트 배경으로 구분하고(카드 자체가 흰색이면 4단계가
// 다 똑같아 보임), dark 모드는 기존 중립 zinc 표면을 유지한다.
const STAGE = {
  collect: {
    bar: "bg-sky-500",
    text: "text-sky-600 dark:text-sky-400",
    card: "border-sky-200/70 bg-sky-50/70 hover:border-sky-300 hover:bg-sky-100/70 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-600 dark:hover:bg-zinc-900",
  },
  classify: {
    bar: "bg-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    card: "border-amber-200/70 bg-amber-50/70 hover:border-amber-300 hover:bg-amber-100/70 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-600 dark:hover:bg-zinc-900",
  },
  ai: {
    bar: "bg-violet-500",
    text: "text-violet-600 dark:text-violet-400",
    card: "border-violet-200/70 bg-violet-50/70 hover:border-violet-300 hover:bg-violet-100/70 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-600 dark:hover:bg-zinc-900",
  },
  report: {
    bar: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    card: "border-emerald-200/70 bg-emerald-50/70 hover:border-emerald-300 hover:bg-emerald-100/70 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-600 dark:hover:bg-zinc-900",
  },
};

function FlowStage({
  href,
  step,
  title,
  metric,
  sub,
  accent,
}: {
  href: string;
  step: string;
  title: string;
  metric: string;
  sub: string;
  accent: { bar: string; text: string; card: string };
}) {
  return (
    <Link
      href={href}
      className={`group relative flex-1 overflow-hidden rounded-xl border transition ${accent.card}`}
    >
      <div className={`h-1 ${accent.bar}`} />
      <div className="p-4">
        <p className={`text-[11px] font-medium ${accent.text}`}>{step}</p>
        <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{title}</p>
        <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">{metric}</p>
        <p className="mt-0.5 text-[11px] text-zinc-500">{sub}</p>
      </div>
    </Link>
  );
}

function Arrow() {
  return (
    <div className="hidden shrink-0 items-center self-center text-lg text-zinc-400 dark:text-zinc-600 sm:flex" aria-hidden>
      →
    </div>
  );
}

export default function DashboardPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [docCount, setDocCount] = useState(0);
  const [topicList, setTopicList] = useState<TopicListItem[]>([]);
  const [latest, setLatest] = useState<GeneratedDigest | null>(null);
  const [assetCount, setAssetCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [overview, topics, digest, artifacts] = await Promise.all([
          api.collectionOverview(),
          topicsApi.list().catch(() => [] as TopicListItem[]),
          digestApi.latest().catch(() => null),
          artifactsApi.count().catch(() => 0),
        ]);
        if (!alive) return;
        setSources(overview.sources);
        setDocCount(overview.documentCount);
        setTopicList(topics);
        setLatest(digest);
        setAssetCount(artifacts);
        setError(null);
      } catch {
        if (alive) setError("백엔드 미연결 (http://localhost:8000)");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const connectorCount = sources.filter((s) => s.type !== "upload").length;
  const attentionCount = sources.filter((s) =>
    ["setup", "error", "stale", "warning"].includes(s.operational.state),
  ).length;
  const taggedCount = topicList.reduce((n, t) => n + t.count, 0);
  const untagged = Math.max(0, docCount - taggedCount);
  const highImpact = (latest?.items ?? []).filter((i) => i.impact === "high");

  return (
    <>
      <PageHeader
        title="대시보드"
        description="시장 센싱 파이프라인 현황과 이번 주 핵심 시그널 요약"
      />

      {error && (
        <div className="mb-6 rounded-lg border border-amber-100/60 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/40 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          {error} — 백엔드를 실행하면 실시간 현황이 표시됩니다.
        </div>
      )}

      {/* 서비스 흐름: 수집 → 분류 → AI 생성 → 리포트 */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">서비스 흐름</h2>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
          <FlowStage
            href="/collection"
            step="① 데이터 수집"
            title="소스 → 문서"
            metric={`${docCount}건`}
            sub={`소스 ${sources.length}개 (커넥터 ${connectorCount}${attentionCount ? ` · 점검 ${attentionCount}` : ""})`}
            accent={STAGE.collect}
          />
          <Arrow />
          <FlowStage
            href="/collection"
            step="② 자동 분류"
            title="주제 부여"
            metric={`${topicList.length}개`}
            sub={untagged > 0 ? `미분류 ${untagged}건` : "모두 분류됨"}
            accent={STAGE.classify}
          />
          <Arrow />
          <FlowStage
            href="/topics"
            step="③ AI 인텔리전스"
            title="생성물 누적"
            metric={`${assetCount}건`}
            sub="다이제스트·주제·경쟁사·리포트 (자산화)"
            accent={STAGE.ai}
          />
          <Arrow />
          <FlowStage
            href="/report"
            step="④ 주간 리포트"
            title="종합 생성"
            metric={latest ? latest.week : "—"}
            sub={latest?.generatedAt ? `자동 생성 ${latest.generatedAt}` : "생성 전"}
            accent={STAGE.report}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
          <p>소스 수집 → 주제 분류 → AI 분석 → 주간 리포트. 각 단계를 눌러 이동하세요.</p>
          <div className="flex gap-2">
            <Link href="/ask" className="rounded-full bg-violet-50 px-2.5 py-1 font-medium text-violet-700 hover:bg-violet-100 dark:bg-violet-950/50 dark:text-violet-300">문서 Q&A →</Link>
            <Link href="/collection/results" className="rounded-full bg-sky-50 px-2.5 py-1 font-medium text-sky-700 hover:bg-sky-100 dark:bg-sky-950/50 dark:text-sky-300">수집 결과 →</Link>
          </div>
        </div>
      </section>

      {/* 핵심 시그널 (최근 자동 다이제스트의 영향도 상 항목) */}
      <section className="mt-8">
        <h2 className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">영향도 높은 시그널</h2>
        {highImpact.length === 0 ? (
          <Card>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {latest
                ? "최근 다이제스트에 영향도 '상' 항목이 없습니다."
                : "아직 자동 생성된 다이제스트가 없습니다. "}
              {!latest && (
                <Link href="/digest" className="text-sky-600 dark:text-sky-400 hover:underline">
                  다이제스트 생성 →
                </Link>
              )}
            </p>
          </Card>
        ) : (
          <div className="flex flex-col gap-3">
            {highImpact.map((item) => (
              <Card key={item.id} className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{item.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{item.slsiRelevance}</p>
                </div>
                <ImpactBadge level={item.impact} />
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* 수집 파이프라인 상태 (실시간) */}
      <section className="mt-8">
        <h2 className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">수집 파이프라인 상태</h2>
        <PipelineStatus />
      </section>
    </>
  );
}
