"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  topicsApi,
  SOURCE_TYPE_LABEL,
  type CollectedDoc,
  type Source,
  type TopicListItem,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

function statusColor(status: string) {
  if (status === "정상") return "text-emerald-600 dark:text-emerald-400";
  if (status === "지연") return "text-amber-600 dark:text-amber-400";
  if (status === "오류") return "text-red-600 dark:text-red-400";
  return "text-zinc-600 dark:text-zinc-400";
}

function Kpi({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
      {hint && <p className="mt-1 text-[11px] text-zinc-500">{hint}</p>}
    </Card>
  );
}

export default function CollectionResultsPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [docCount, setDocCount] = useState(0);
  const [docs, setDocs] = useState<CollectedDoc[]>([]);
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [overview, documents, topicList] = await Promise.all([
          api.collectionOverview(),
          api.listDocuments(),
          topicsApi.list().catch(() => [] as TopicListItem[]),
        ]);
        if (!alive) return;
        setSources(overview.sources);
        setDocCount(overview.documentCount);
        setDocs(documents);
        setTopics(topicList);
        setError(null);
      } catch (e) {
        if (alive)
          setError(
            e instanceof Error ? e.message : "백엔드 연결 실패 (http://localhost:8000)",
          );
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const connectorCount = sources.filter((s) => s.type !== "upload").length;
  const errorCount = sources.filter((s) => s.status === "오류").length;
  const taggedCount = topics.reduce((n, t) => n + t.count, 0);
  const untagged = Math.max(0, docCount - taggedCount);
  const maxTopic = topics.reduce((m, t) => Math.max(m, t.count), 0);
  const recent = docs.slice(0, 10);

  return (
    <>
      <PageHeader
        title="수집 결과"
        description="수집 파이프라인의 산출물 요약 — 소스별 건수·상태, 주제 분포, 최근 수집 문서"
      />

      {error && (
        <div className="mb-6 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">불러오는 중…</p>
      ) : (
        <div className="flex flex-col gap-8">
          {/* KPI */}
          <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Kpi label="수집 문서" value={docCount} hint={`최근 ${recent.length}건 표시`} />
            <Kpi label="소스" value={sources.length} hint={`커넥터 ${connectorCount}`} />
            <Kpi label="추적 주제" value={topics.length} hint={untagged > 0 ? `미분류 ${untagged}건` : "모두 분류됨"} />
            <Kpi label="오류 소스" value={errorCount} hint={errorCount ? "상태 확인 필요" : "정상"} />
          </section>

          {/* 소스별 수집 현황 */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">소스별 수집 현황</h2>
              <Link href="/collection" className="text-xs text-sky-600 dark:text-sky-400 hover:underline">
                소스 관리 →
              </Link>
            </div>
            <Card className="p-0">
              {sources.length === 0 ? (
                <p className="px-5 py-8 text-center text-sm text-zinc-500">등록된 소스가 없습니다.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 dark:border-zinc-800 text-left text-xs text-zinc-500">
                      <th className="px-5 py-3 font-medium">소스</th>
                      <th className="px-5 py-3 font-medium">타입</th>
                      <th className="px-5 py-3 font-medium">상태</th>
                      <th className="px-5 py-3 font-medium">최근 실행</th>
                      <th className="px-5 py-3 text-right font-medium">누적</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s) => (
                      <tr key={s.id} className="border-b border-zinc-200/60 dark:border-zinc-800/60 last:border-0">
                        <td className="px-5 py-3 text-zinc-800 dark:text-zinc-200">{s.name}</td>
                        <td className="px-5 py-3 text-xs text-zinc-600 dark:text-zinc-400">
                          {SOURCE_TYPE_LABEL[s.type]}
                        </td>
                        <td className="px-5 py-3">
                          <span className={statusColor(s.status)}>● {s.status}</span>
                        </td>
                        <td className="px-5 py-3 font-mono text-xs text-zinc-600 dark:text-zinc-400">
                          {s.lastRun ?? "—"}
                        </td>
                        <td className="px-5 py-3 text-right font-mono text-xs text-zinc-700 dark:text-zinc-300">
                          {s.count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </section>

          {/* 주제 분포 */}
          <section>
            <h2 className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">주제 분포</h2>
            {topics.length === 0 ? (
              <Card>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  분류된 주제가 없습니다. 데이터 수집의 문서 탭에서 자동 분류를 실행하세요.
                </p>
              </Card>
            ) : (
              <Card>
                <ul className="flex flex-col gap-2.5">
                  {topics.map((t) => (
                    <li key={t.topic} className="flex items-center gap-3">
                      <Link
                        href={`/collection/documents?topic=${encodeURIComponent(t.topic)}`}
                        className="w-40 shrink-0 truncate text-sm text-zinc-700 dark:text-zinc-300 hover:text-sky-700 dark:hover:text-sky-300"
                      >
                        {t.topic}
                      </Link>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                        <div
                          className="h-full rounded-full bg-sky-600"
                          style={{ width: `${maxTopic ? (t.count / maxTopic) * 100 : 0}%` }}
                        />
                      </div>
                      <span className="w-10 shrink-0 text-right font-mono text-xs text-zinc-600 dark:text-zinc-400">
                        {t.count}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </section>

          {/* 최근 수집 문서 */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">최근 수집 문서</h2>
              <Link href="/collection/documents" className="text-xs text-sky-600 dark:text-sky-400 hover:underline">
                전체 문서 보기 →
              </Link>
            </div>
            <Card className="p-0">
              {recent.length === 0 ? (
                <p className="px-5 py-8 text-center text-sm text-zinc-500">
                  수집된 문서가 없습니다.
                </p>
              ) : (
                <ul className="divide-y divide-zinc-200/60 dark:divide-zinc-800/60">
                  {recent.map((d) => (
                    <li key={d.id}>
                      <Link
                        href={`/collection/documents?doc=${d.id}`}
                        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-900"
                      >
                        <span className="min-w-0 flex-1 truncate text-sm text-zinc-800 dark:text-zinc-200">
                          {d.title}
                        </span>
                        {d.topic ? (
                          <Tag>{d.topic}</Tag>
                        ) : (
                          <span className="text-[11px] text-zinc-400 dark:text-zinc-600">미분류</span>
                        )}
                        <span className="shrink-0 text-xs text-zinc-500">{d.sourceName}</span>
                        <span className="shrink-0 font-mono text-xs text-zinc-500">
                          {d.createdAt}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </section>
        </div>
      )}
    </>
  );
}
