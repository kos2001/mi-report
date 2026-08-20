"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  topicsApi,
  SOURCE_TYPE_LABEL,
  type CollectedDoc,
  type SearchInfrastructureStatus,
  type Source,
  type TopicListItem,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";
import { SourceOperationalStatus } from "@/components/source-operational-status";

function Kpi({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
      {hint && <p className="mt-1 text-[11px] text-zinc-500">{hint}</p>}
    </Card>
  );
}

function CoverageBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="mt-3">
      <div className="mb-1 flex items-center justify-between text-[10px] text-zinc-500">
        <span>문서 커버리지</span>
        <span className="font-mono font-semibold">{value}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default function CollectionResultsPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [docCount, setDocCount] = useState(0);
  const [docs, setDocs] = useState<CollectedDoc[]>([]);
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const [infrastructure, setInfrastructure] = useState<SearchInfrastructureStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [overview, documents, topicList, searchInfrastructure] = await Promise.all([
          api.collectionOverview(),
          api.listDocuments(),
          topicsApi.list().catch(() => [] as TopicListItem[]),
          api.searchInfrastructure(),
        ]);
        if (!alive) return;
        setSources(overview.sources);
        setDocCount(overview.documentCount);
        setDocs(documents);
        setTopics(topicList);
        setInfrastructure(searchInfrastructure);
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
  const activeCount = sources.filter((s) => s.operational.effectiveActive).length;
  const attentionCount = sources.filter((s) =>
    ["setup", "error", "stale", "warning"].includes(s.operational.state),
  ).length;
  const taggedCount = topics.reduce((n, t) => n + t.count, 0);
  const untagged = Math.max(0, docCount - taggedCount);
  const maxTopic = topics.reduce((m, t) => Math.max(m, t.count), 0);
  const recent = docs.slice(0, 10);
  const coverage = (count: number) =>
    infrastructure?.totalDocuments
      ? Math.min(100, Math.round((count / infrastructure.totalDocuments) * 100))
      : 0;
  const bm25Coverage = coverage(infrastructure?.bm25.indexedDocuments ?? 0);
  const embeddingCoverage = coverage(infrastructure?.embeddings.vectors ?? 0);
  const storedEmbedding = infrastructure?.embeddings.storedModels[0];

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
            <Kpi label="소스" value={sources.length} hint={`실제 활성 ${activeCount} · 커넥터 ${connectorCount}`} />
            <Kpi label="추적 주제" value={topics.length} hint={untagged > 0 ? `미분류 ${untagged}건` : "모두 분류됨"} />
            <Kpi label="점검 필요" value={attentionCount} hint={attentionCount ? "설정·실행 상태 확인 필요" : "운영 판정 정상"} />
          </section>

          {/* 검색·지식 인프라 */}
          {infrastructure && (
            <section>
              <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">검색 · 지식 인프라</h2>
                  <p className="mt-1 text-xs text-zinc-500">수집 문서가 검색 색인과 주차별 지식으로 변환된 실제 상태</p>
                </div>
                <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                  ● 실시간 DB 기준
                </span>
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Card className="overflow-hidden border-blue-200/80 bg-gradient-to-br from-blue-50 to-white dark:border-blue-900/70 dark:from-blue-950/40 dark:to-zinc-950">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 font-mono text-sm font-bold text-white shadow-sm">BM</span>
                      <div>
                        <p className="text-sm font-semibold text-blue-950 dark:text-blue-100">BM25 키워드 색인</p>
                        <p className="mt-0.5 text-[11px] text-blue-600 dark:text-blue-400">정확한 용어 · 약어 · 숫자 검색</p>
                      </div>
                    </div>
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-900 dark:text-blue-300">LEXICAL</span>
                  </div>
                  <div className="mt-5 flex items-end justify-between">
                    <div>
                      <p className="text-3xl font-bold text-blue-950 dark:text-blue-50">{infrastructure.bm25.indexedDocuments.toLocaleString()}</p>
                      <p className="text-[11px] text-blue-600 dark:text-blue-400">색인 문서 / 전체 {infrastructure.totalDocuments.toLocaleString()}건</p>
                    </div>
                    <code className="rounded bg-white/80 px-2 py-1 text-[10px] text-blue-700 dark:bg-zinc-900/80 dark:text-blue-300">FTS5</code>
                  </div>
                  <CoverageBar value={bm25Coverage} color="bg-blue-500" />
                  <ul className="mt-4 space-y-1 text-[11px] leading-5 text-zinc-600 dark:text-zinc-400">
                    <li>• 제목·주제·본문 전체 색인</li>
                    <li>• 반도체 동의어 확장 후 정밀/확장 검색 결합</li>
                    <li>• 임베딩과 RRF로 최종 후보 통합</li>
                  </ul>
                </Card>

                <Card className="overflow-hidden border-violet-200/80 bg-gradient-to-br from-violet-50 to-white dark:border-violet-900/70 dark:from-violet-950/40 dark:to-zinc-950">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-600 text-xl font-bold text-white shadow-sm">◇</span>
                      <div>
                        <p className="text-sm font-semibold text-violet-950 dark:text-violet-100">Embedding DB</p>
                        <p className="mt-0.5 text-[11px] text-violet-600 dark:text-violet-400">표현이 달라도 의미가 가까운 문서 검색</p>
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${infrastructure.embeddings.configured ? "bg-violet-100 text-violet-700 dark:bg-violet-900 dark:text-violet-300" : "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"}`}>
                      {infrastructure.embeddings.configured ? "SEMANTIC" : "DISABLED"}
                    </span>
                  </div>
                  <div className="mt-5 flex items-end justify-between">
                    <div>
                      <p className="text-3xl font-bold text-violet-950 dark:text-violet-50">{infrastructure.embeddings.vectors.toLocaleString()}</p>
                      <p className="text-[11px] text-violet-600 dark:text-violet-400">저장 벡터 / 전체 {infrastructure.totalDocuments.toLocaleString()}건</p>
                    </div>
                    {storedEmbedding && (
                      <span className="rounded bg-white/80 px-2 py-1 font-mono text-[10px] text-violet-700 dark:bg-zinc-900/80 dark:text-violet-300">{storedEmbedding.dimensions}D</span>
                    )}
                  </div>
                  <CoverageBar value={embeddingCoverage} color="bg-violet-500" />
                  <div className="mt-4 rounded-lg bg-white/70 px-3 py-2 dark:bg-zinc-900/70">
                    <p className="text-[10px] uppercase tracking-wide text-zinc-500">현재 설정</p>
                    <p className="mt-1 break-all font-mono text-[11px] font-medium text-violet-800 dark:text-violet-200">{infrastructure.embeddings.model}</p>
                    <p className="mt-1 text-[10px] text-zinc-500">backend · {infrastructure.embeddings.backend}</p>
                  </div>
                </Card>

                <Card className="overflow-hidden border-amber-200/80 bg-gradient-to-br from-amber-50 to-white dark:border-amber-900/70 dark:from-amber-950/40 dark:to-zinc-950">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-500 text-xl font-bold text-white shadow-sm">W</span>
                      <div>
                        <p className="text-sm font-semibold text-amber-950 dark:text-amber-100">LLM Wiki</p>
                        <p className="mt-0.5 text-[11px] text-amber-700 dark:text-amber-400">주차별 MI 지식과 개념 연결</p>
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${infrastructure.wiki.enabled ? "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300" : "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"}`}>
                      {infrastructure.wiki.enabled ? "KNOWLEDGE" : "DISABLED"}
                    </span>
                  </div>
                  <div className="mt-5 grid grid-cols-2 gap-2">
                    <div className="rounded-lg bg-white/75 px-3 py-2 dark:bg-zinc-900/70">
                      <p className="text-2xl font-bold text-amber-950 dark:text-amber-50">{infrastructure.wiki.weekCount}</p>
                      <p className="text-[10px] text-amber-700 dark:text-amber-400">누적 주차</p>
                    </div>
                    <div className="rounded-lg bg-white/75 px-3 py-2 dark:bg-zinc-900/70">
                      <p className="text-2xl font-bold text-amber-950 dark:text-amber-50">{infrastructure.wiki.conceptCount}</p>
                      <p className="text-[10px] text-amber-700 dark:text-amber-400">연결 개념</p>
                    </div>
                  </div>
                  <div className="mt-3 rounded-lg bg-amber-100/60 px-3 py-2 dark:bg-amber-950/60">
                    <p className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">최신 지식</p>
                    <p className="mt-1 text-xs font-semibold text-amber-950 dark:text-amber-100">{infrastructure.wiki.latestWeek ?? "아직 생성 없음"}</p>
                    <p className="mt-0.5 text-[10px] text-amber-700/80 dark:text-amber-400/80">다음 생성 시 최근 {infrastructure.wiki.contextMaxWeeks}주 맥락 사용</p>
                  </div>
                  <p className="mt-3 truncate font-mono text-[10px] text-zinc-500" title={infrastructure.wiki.path}>{infrastructure.wiki.path}</p>
                </Card>
              </div>

              <Card className="mt-4 border-zinc-200 bg-zinc-50/70 dark:border-zinc-800 dark:bg-zinc-900/50">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">데이터 활용 흐름</p>
                <div className="mt-3 grid items-center gap-2 text-center text-xs md:grid-cols-[1fr_auto_1fr_auto_1fr]">
                  <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-sky-800 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200">수집 원문</div>
                  <span className="text-zinc-400">→</span>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-blue-200 bg-blue-50 px-2 py-3 font-semibold text-blue-800 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200">BM25<br /><span className="text-[10px] font-normal">키워드</span></div>
                    <div className="rounded-lg border border-violet-200 bg-violet-50 px-2 py-3 font-semibold text-violet-800 dark:border-violet-900 dark:bg-violet-950/40 dark:text-violet-200">Embedding<br /><span className="text-[10px] font-normal">의미</span></div>
                  </div>
                  <span className="text-zinc-400">→</span>
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 font-semibold text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">Hybrid RRF 검색<br /><span className="text-[10px] font-normal">Q&A · 근거 조회</span></div>
                </div>
                <div className="mt-2 flex items-center justify-center gap-2 text-[11px] text-zinc-500">
                  <span className="rounded bg-amber-100 px-2 py-1 font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">생성된 다이제스트</span>
                  <span>→</span>
                  <span className="rounded bg-amber-100 px-2 py-1 font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">LLM Wiki 누적</span>
                  <span>→ 다음 주차 다이제스트 맥락</span>
                </div>
              </Card>
            </section>
          )}

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
                      <th className="px-5 py-3 font-medium">실제 운영 상태</th>
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
                          <SourceOperationalStatus source={s} showReason />
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
