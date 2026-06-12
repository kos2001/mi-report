import { topics } from "@/lib/data";
import { Card, PageHeader, Tag } from "@/components/ui";

export default function TopicsPage() {
  return (
    <>
      <PageHeader
        title="주제별 History"
        description="조사기관·증권사 자료와 뉴스 센싱 누적 정보 기반 주제별 이력 및 인사이트"
      />
      <div className="flex flex-col gap-5">
        {topics.map((topic) => (
          <Card key={topic.id}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Tag>{topic.category}</Tag>
                  <span className="text-[11px] text-zinc-500">
                    소스 {topic.sourceCount}건 · 업데이트 {topic.updatedAt}
                  </span>
                </div>
                <h2 className="mt-2 text-base font-semibold text-zinc-50">
                  {topic.title}
                </h2>
              </div>
            </div>

            <p className="mt-3 text-sm leading-relaxed text-zinc-300">
              {topic.summary}
            </p>

            <div className="mt-4 rounded-lg border border-sky-900/40 bg-sky-950/30 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
                Insight — SET/반도체 시황 연계
              </p>
              <p className="mt-1.5 text-sm leading-relaxed text-zinc-200">
                {topic.insight}
              </p>
            </div>

            <div className="mt-4">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                History
              </p>
              <ol className="flex flex-col gap-2 border-l border-zinc-800 pl-4">
                {topic.history.map((h) => (
                  <li key={h.date + h.event} className="relative">
                    <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-zinc-600" />
                    <span className="font-mono text-xs text-zinc-500">
                      {h.date}
                    </span>
                    <p className="text-sm text-zinc-300">
                      {h.event}{" "}
                      <span className="text-xs text-zinc-500">({h.source})</span>
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
