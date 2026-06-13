"use client";

import { useState } from "react";
import { competitorsApi, type GeneratedCompetitor } from "@/lib/api";
import { competitors } from "@/lib/data";
import { Card, Delta, PageHeader } from "@/components/ui";

const directionIcon = { up: "▲", down: "▼", flat: "—" } as const;
const directionColor = {
  up: "text-emerald-400",
  down: "text-red-400",
  flat: "text-zinc-400",
} as const;

type CompetitorLike = {
  id: string;
  name: string;
  ticker: string;
  fiscalQuarter: string;
  reportedAt: string;
  financials: { metric: string; value: string; qoq: number | null; yoy: number | null }[];
  callSummary: string[];
  qoqChanges: string[];
  consensus: {
    metric: string;
    current: string;
    previous: string;
    revisedAt: string;
    broker: string;
    direction: "up" | "down" | "flat";
  }[];
};

// qoq/yoy 가 null(문서에 수치 없음)이면 '—' 로 표기.
function MaybeDelta({ value }: { value: number | null }) {
  if (value === null || value === undefined)
    return <span className="font-mono text-xs text-zinc-600">—</span>;
  return <Delta value={value} suffix="%p" />;
}

function CompetitorCard({ c, generated }: { c: CompetitorLike; generated?: boolean }) {
  return (
    <Card>
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-zinc-50">
          {c.name} <span className="ml-1 font-mono text-xs text-zinc-500">{c.ticker}</span>
        </h2>
        <div className="flex items-center gap-3">
          {generated && (
            <span className="rounded-full border border-sky-900/60 bg-sky-950/40 px-3 py-1 text-xs text-sky-400">
              AI 생성
            </span>
          )}
          <p className="text-xs text-zinc-500">
            {c.fiscalQuarter} · 발표일 {c.reportedAt}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
          재무 요약 (자동 생성)
        </p>
        {c.financials.length === 0 ? (
          <p className="text-sm text-zinc-500">문서에서 추출된 재무 수치 없음</p>
        ) : (
          <div className="grid grid-cols-4 gap-3">
            {c.financials.map((f) => (
              <div key={f.metric} className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
                <p className="text-[11px] text-zinc-500">{f.metric}</p>
                <p className="mt-1 text-base font-semibold text-zinc-100">{f.value}</p>
                <p className="mt-1 flex gap-2 text-[11px] text-zinc-500">
                  QoQ <MaybeDelta value={f.qoq} />
                  YoY <MaybeDelta value={f.yoy} />
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-5 grid grid-cols-2 gap-4">
        <div>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
            컨퍼런스 콜 요약
          </p>
          <ul className="flex flex-col gap-2">
            {c.callSummary.map((s) => (
              <li key={s} className="text-sm leading-relaxed text-zinc-300">
                · {s}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
            전분기 대비 변화 포인트
          </p>
          <ul className="flex flex-col gap-2">
            {c.qoqChanges.map((s) => (
              <li
                key={s}
                className="rounded-lg border border-violet-900/40 bg-violet-950/30 px-3 py-2 text-sm leading-relaxed text-zinc-200"
              >
                {s}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-5">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
          증권사 컨센서스 갱신 감지
        </p>
        {c.consensus.length === 0 ? (
          <p className="text-sm text-zinc-500">문서에서 감지된 컨센서스 갱신 없음</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                <th className="py-2 pr-4 font-medium">지표</th>
                <th className="py-2 pr-4 font-medium">현재 전망</th>
                <th className="py-2 pr-4 font-medium">직전 전망</th>
                <th className="py-2 pr-4 font-medium">갱신일</th>
                <th className="py-2 font-medium">출처</th>
              </tr>
            </thead>
            <tbody>
              {c.consensus.map((cs) => (
                <tr
                  key={cs.metric + cs.broker}
                  className="border-b border-zinc-800/60 last:border-0"
                >
                  <td className="py-2.5 pr-4 text-zinc-200">{cs.metric}</td>
                  <td className="py-2.5 pr-4 font-mono text-xs">
                    <span className={directionColor[cs.direction]}>
                      {directionIcon[cs.direction]} {cs.current}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-xs text-zinc-500">{cs.previous}</td>
                  <td className="py-2.5 pr-4 font-mono text-xs text-zinc-400">{cs.revisedAt}</td>
                  <td className="py-2.5 text-xs text-zinc-400">{cs.broker}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}

export default function CompetitorsPage() {
  const [name, setName] = useState("");
  const [ticker, setTicker] = useState("");
  const [topic, setTopic] = useState("");
  const [generated, setGenerated] = useState<GeneratedCompetitor | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAnalyze() {
    if (!name.trim()) {
      setError("경쟁사 이름을 입력하세요.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setGenerated(
        await competitorsApi.analyze({
          name: name.trim(),
          ticker: ticker.trim() || undefined,
          topic: topic.trim() || undefined,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "경쟁사 분석 생성 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="경쟁사 IR 트래킹"
        description="분기 IR 발표 기반 재무 요약 자동 생성, 컨퍼런스 콜 요약, 전분기 대비 변화, 증권사 컨센서스 갱신 추적"
      />

      {/* AI 경쟁사 분석 생성 패널 */}
      <Card className="mb-8">
        <h2 className="text-sm font-semibold text-zinc-100">AI 경쟁사 분석 생성</h2>
        <p className="mt-1 text-xs text-zinc-500">
          수집된 IR·실적 문서를 분석합니다. 경쟁사 이름과 (선택) 문서 주제를 입력하세요.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="경쟁사 이름"
            className="w-40 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
          />
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="티커 (선택)"
            className="w-28 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
          />
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="문서 주제 (선택)"
            className="w-40 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
          />
          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="shrink-0 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "분석 중…" : "AI 분석 생성"}
          </button>
        </div>
        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </Card>

      <div className="flex flex-col gap-8">
        {generated && <CompetitorCard c={generated} generated />}
        {competitors.map((c) => (
          <CompetitorCard key={c.id} c={c} />
        ))}
      </div>
    </>
  );
}
