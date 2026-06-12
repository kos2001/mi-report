import Link from "next/link";
import { competitors, digests, pipelineStatus, topics } from "@/lib/data";
import { Card, ImpactBadge, PageHeader } from "@/components/ui";

export default function DashboardPage() {
  const draftDigest = digests.find((d) => d.mailedAt === null);
  const highImpact = digests
    .flatMap((d) => d.items)
    .filter((i) => i.impact === "high");

  return (
    <>
      <PageHeader
        title="대시보드"
        description="시장 센싱 파이프라인 현황과 이번 주 핵심 시그널 요약"
      />

      <section className="grid grid-cols-3 gap-4">
        <Card>
          <p className="text-xs text-zinc-500">추적 중인 주제</p>
          <p className="mt-2 text-3xl font-semibold text-zinc-50">
            {topics.length}
          </p>
          <Link
            href="/topics"
            className="mt-3 inline-block text-xs text-sky-400 hover:underline"
          >
            주제별 History 보기 →
          </Link>
        </Card>
        <Card>
          <p className="text-xs text-zinc-500">발송 대기 다이제스트</p>
          <p className="mt-2 text-3xl font-semibold text-zinc-50">
            {draftDigest ? `제${draftDigest.issueNo}호` : "없음"}
          </p>
          <Link
            href="/digest"
            className="mt-3 inline-block text-xs text-sky-400 hover:underline"
          >
            초안 검토 →
          </Link>
        </Card>
        <Card>
          <p className="text-xs text-zinc-500">경쟁사 IR 추적</p>
          <p className="mt-2 text-3xl font-semibold text-zinc-50">
            {competitors.length}개사
          </p>
          <Link
            href="/competitors"
            className="mt-3 inline-block text-xs text-sky-400 hover:underline"
          >
            분기 실적 비교 →
          </Link>
        </Card>
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">
          영향도 높은 시그널
        </h2>
        <div className="flex flex-col gap-3">
          {highImpact.map((item) => (
            <Card key={item.id} className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-zinc-100">{item.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-zinc-400">
                  {item.slsiRelevance}
                </p>
              </div>
              <ImpactBadge level={item.impact} />
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">
          수집 파이프라인 상태
        </h2>
        <Card className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                <th className="px-5 py-3 font-medium">소스</th>
                <th className="px-5 py-3 font-medium">상태</th>
                <th className="px-5 py-3 font-medium">최근 실행</th>
                <th className="px-5 py-3 text-right font-medium">신규 문서</th>
              </tr>
            </thead>
            <tbody>
              {pipelineStatus.map((p) => (
                <tr key={p.name} className="border-b border-zinc-800/60 last:border-0">
                  <td className="px-5 py-3 text-zinc-200">{p.name}</td>
                  <td className="px-5 py-3">
                    <span
                      className={
                        p.status === "정상"
                          ? "text-emerald-400"
                          : "text-amber-400"
                      }
                    >
                      ● {p.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-zinc-400">
                    {p.lastRun}
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-xs text-zinc-300">
                    {p.count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>
    </>
  );
}
