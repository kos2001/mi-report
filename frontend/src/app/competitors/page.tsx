import { competitors } from "@/lib/data";
import { Card, Delta, PageHeader } from "@/components/ui";

const directionIcon = { up: "▲", down: "▼", flat: "—" } as const;
const directionColor = {
  up: "text-emerald-400",
  down: "text-red-400",
  flat: "text-zinc-400",
} as const;

export default function CompetitorsPage() {
  return (
    <>
      <PageHeader
        title="경쟁사 IR 트래킹"
        description="분기 IR 발표 기반 재무 요약 자동 생성, 컨퍼런스 콜 요약, 전분기 대비 변화, 증권사 컨센서스 갱신 추적"
      />
      <div className="flex flex-col gap-8">
        {competitors.map((c) => (
          <Card key={c.id}>
            <div className="flex items-baseline justify-between">
              <h2 className="text-base font-semibold text-zinc-50">
                {c.name}{" "}
                <span className="ml-1 font-mono text-xs text-zinc-500">
                  {c.ticker}
                </span>
              </h2>
              <p className="text-xs text-zinc-500">
                {c.fiscalQuarter} · 발표일 {c.reportedAt}
              </p>
            </div>

            <div className="mt-4">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                재무 요약 (자동 생성)
              </p>
              <div className="grid grid-cols-4 gap-3">
                {c.financials.map((f) => (
                  <div
                    key={f.metric}
                    className="rounded-lg bg-zinc-800/50 px-3 py-2.5"
                  >
                    <p className="text-[11px] text-zinc-500">{f.metric}</p>
                    <p className="mt-1 text-base font-semibold text-zinc-100">
                      {f.value}
                    </p>
                    <p className="mt-1 flex gap-2 text-[11px] text-zinc-500">
                      QoQ <Delta value={f.qoq} suffix="%p" />
                      YoY <Delta value={f.yoy} suffix="%p" />
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <div>
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                  컨퍼런스 콜 요약
                </p>
                <ul className="flex flex-col gap-2">
                  {c.callSummary.map((s) => (
                    <li
                      key={s}
                      className="text-sm leading-relaxed text-zinc-300"
                    >
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
                      <td className="py-2.5 pr-4 font-mono text-xs text-zinc-500">
                        {cs.previous}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-zinc-400">
                        {cs.revisedAt}
                      </td>
                      <td className="py-2.5 text-xs text-zinc-400">{cs.broker}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
