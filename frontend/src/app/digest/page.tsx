import { digests } from "@/lib/data";
import { Card, ImpactBadge, PageHeader, Tag } from "@/components/ui";

export default function DigestPage() {
  return (
    <>
      <PageHeader
        title="뉴스 다이제스트"
        description="주 2회 반도체·IT 기술 뉴스 종합 — S.LSI 연관성·수요 변동·리스크 영향도 평가 후 메일링"
      />
      <div className="flex flex-col gap-8">
        {digests.map((digest) => (
          <section key={digest.id}>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-zinc-50">
                  제{digest.issueNo}호{" "}
                  <span className="ml-1 text-sm font-normal text-zinc-400">
                    {digest.period}
                  </span>
                </h2>
              </div>
              {digest.mailedAt ? (
                <span className="rounded-full border border-emerald-900/60 bg-emerald-950/40 px-3 py-1 text-xs text-emerald-400">
                  발송 완료 · {digest.mailedAt}
                </span>
              ) : (
                <span className="rounded-full border border-amber-900/60 bg-amber-950/40 px-3 py-1 text-xs text-amber-400">
                  초안 — 발송 전 검토 필요
                </span>
              )}
            </div>

            <div className="flex flex-col gap-4">
              {digest.items.map((item) => (
                <Card key={item.id}>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-100">
                        {item.title}
                      </h3>
                      <p className="mt-1 text-xs text-zinc-500">
                        {item.source} · {item.publishedAt}
                      </p>
                    </div>
                    <ImpactBadge level={item.impact} />
                  </div>

                  <p className="mt-3 text-sm leading-relaxed text-zinc-300">
                    {item.summary}
                  </p>

                  <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
                    <div className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
                      <dt className="font-medium text-zinc-500">S.LSI 연관성</dt>
                      <dd className="mt-1 leading-relaxed text-zinc-300">
                        {item.slsiRelevance}
                      </dd>
                    </div>
                    <div className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
                      <dt className="font-medium text-zinc-500">수요 변동</dt>
                      <dd className="mt-1 leading-relaxed text-zinc-300">
                        {item.demandImpact}
                      </dd>
                    </div>
                    <div className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
                      <dt className="font-medium text-zinc-500">리스크</dt>
                      <dd className="mt-1 leading-relaxed text-zinc-300">
                        {item.risk}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-3 flex gap-1.5">
                    {item.tags.map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
