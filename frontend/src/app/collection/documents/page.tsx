"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  topicsApi,
  SOURCE_TYPE_LABEL,
  type CollectedDoc,
  type Source,
  type SourceType,
  type TopicListItem,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";

const SOURCE_VISUAL: Record<SourceType, {
  icon: string;
  label: string;
  accent: string;
  soft: string;
  text: string;
}> = {
  edm: { icon: "✉", label: "EDM", accent: "bg-violet-500", soft: "bg-violet-50 dark:bg-violet-950/40", text: "text-violet-700 dark:text-violet-300" },
  confluence: { icon: "◆", label: "Confluence", accent: "bg-blue-500", soft: "bg-blue-50 dark:bg-blue-950/40", text: "text-blue-700 dark:text-blue-300" },
  sec: { icon: "▣", label: "SEC 공시", accent: "bg-emerald-500", soft: "bg-emerald-50 dark:bg-emerald-950/40", text: "text-emerald-700 dark:text-emerald-300" },
  dart: { icon: "▤", label: "DART 공시", accent: "bg-rose-500", soft: "bg-rose-50 dark:bg-rose-950/40", text: "text-rose-700 dark:text-rose-300" },
  hankyung: { icon: "₩", label: "한경 리포트", accent: "bg-amber-500", soft: "bg-amber-50 dark:bg-amber-950/40", text: "text-amber-700 dark:text-amber-300" },
  news: { icon: "●", label: "뉴스", accent: "bg-cyan-500", soft: "bg-cyan-50 dark:bg-cyan-950/40", text: "text-cyan-700 dark:text-cyan-300" },
  broker: { icon: "▥", label: "증권사", accent: "bg-orange-500", soft: "bg-orange-50 dark:bg-orange-950/40", text: "text-orange-700 dark:text-orange-300" },
  consensus: { icon: "↗", label: "컨센서스", accent: "bg-fuchsia-500", soft: "bg-fuchsia-50 dark:bg-fuchsia-950/40", text: "text-fuchsia-700 dark:text-fuchsia-300" },
  upload: { icon: "↑", label: "업로드", accent: "bg-sky-500", soft: "bg-sky-50 dark:bg-sky-950/40", text: "text-sky-700 dark:text-sky-300" },
};

export default function CollectionDocumentsPage() {
  const [docs, setDocs] = useState<CollectedDoc[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 필터
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [topic, setTopic] = useState("");

  // 선택 문서 + 본문
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [contentDoc, setContentDoc] = useState<CollectedDoc | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [classifyingId, setClassifyingId] = useState<string | null>(null);
  const [batchClassifying, setBatchClassifying] = useState(false);

  const openDoc = useCallback(async (id: string) => {
    setSelectedId(id);
    setContentLoading(true);
    setContentError(null);
    setContent(null);
    setContentDoc(null);
    try {
      const r = await api.getDocument(id);
      setContent(r.content);
      setContentDoc(r.document);
    } catch (e) {
      setContentError(e instanceof Error ? e.message : "본문을 불러오지 못했습니다.");
    } finally {
      setContentLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [d, s, t] = await Promise.all([
          api.listDocuments(),
          api.listSources(),
          topicsApi.list().catch(() => [] as TopicListItem[]),
        ]);
        if (!alive) return;
        setDocs(d);
        setSources(s);
        setTopics(t);
        setError(null);
        // 링크로 들어온 초기 필터/선택(?topic=, ?doc=)을 클라이언트에서 반영
        const params = new URLSearchParams(window.location.search);
        const initTopic = params.get("topic");
        const initDoc = params.get("doc");
        const initQuery = params.get("q");
        const initSource = params.get("source");
        if (initTopic) setTopic(initTopic);
        if (initQuery) setQ(initQuery);
        if (initSource) setSource(initSource);
        if (initDoc && d.some((x) => x.id === initDoc)) openDoc(initDoc);
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
  }, [openDoc]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return docs.filter((d) => {
      if (source && d.sourceId !== source) return false;
      if (topic && (d.topic ?? "") !== topic) return false;
      if (needle) {
        const hay = `${d.title} ${d.topic ?? ""} ${d.sourceName}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [docs, q, source, topic]);
  const untaggedCount = docs.filter((doc) => !doc.topic).length;

  const classifyOne = async (id: string) => {
    setClassifyingId(id);
    try {
      const result = await api.classifyDocument(id);
      setDocs((current) => current.map((doc) => (doc.id === id ? result.document : doc)));
      if (contentDoc?.id === id) setContentDoc(result.document);
    } finally {
      setClassifyingId(null);
    }
  };

  const classifyAll = async () => {
    setBatchClassifying(true);
    try {
      await api.classifyUntagged(Math.max(20, untaggedCount));
      setDocs(await api.listDocuments());
    } finally {
      setBatchClassifying(false);
    }
  };

  const contentSource = useMemo(
    () => sources.find((item) => item.id === contentDoc?.sourceId) ?? null,
    [contentDoc?.sourceId, sources],
  );
  const sourceVisual = SOURCE_VISUAL[contentSource?.type ?? "upload"];
  const contentStats = useMemo(() => {
    if (!content) return null;
    const lines = content.split(/\r?\n/).filter((line) => line.trim()).length;
    const numbers = content.match(/\d[\d,.]*%?/g)?.length ?? 0;
    const sections = content.match(/^#{1,3}\s+/gm)?.length ?? 0;
    return { chars: content.length, lines, numbers, sections };
  }, [content]);

  return (
    <>
      <PageHeader
        title="수집 문서"
        description="수집된 문서를 검색·필터하고, 추출된 본문을 열람합니다"
      />

      {error && (
        <div className="mb-6 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 필터 */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="제목·주제·출처 검색"
          className="min-w-52 flex-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
        >
          <option value="">모든 소스</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({SOURCE_TYPE_LABEL[s.type]})
            </option>
          ))}
        </select>
        <select
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
        >
          <option value="">모든 주제</option>
          {topics.map((t) => (
            <option key={t.topic} value={t.topic}>
              {t.topic} ({t.count})
            </option>
          ))}
        </select>
        <button
          onClick={classifyAll}
          disabled={batchClassifying || untaggedCount === 0}
          className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {batchClassifying ? "분류 중…" : `미분류 AI 분류${untaggedCount ? ` (${untaggedCount})` : ""}`}
        </button>
        {(q || source || topic) && (
          <button
            onClick={() => {
              setQ("");
              setSource("");
              setTopic("");
            }}
            className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-800 px-3 py-2 text-xs text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            필터 해제
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">불러오는 중…</p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {/* 목록 */}
          <Card className="p-0">
            <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 px-5 py-2.5">
              <span className="text-xs text-zinc-500">문서 {filtered.length}건</span>
            </div>
            {filtered.length === 0 ? (
              <p className="px-5 py-8 text-center text-sm text-zinc-500">
                조건에 맞는 문서가 없습니다.
              </p>
            ) : (
              <ul className="max-h-[70vh] divide-y divide-zinc-200/60 dark:divide-zinc-800/60 overflow-y-auto">
                {filtered.map((d) => (
                  <li key={d.id}>
                    <button
                      onClick={() => openDoc(d.id)}
                      className={`flex w-full flex-col gap-1 px-5 py-3 text-left transition-colors ${
                        selectedId === d.id ? "bg-zinc-200/80 dark:bg-zinc-800/80" : "hover:bg-zinc-100 dark:hover:bg-zinc-900"
                      }`}
                    >
                      <span className="truncate text-sm text-zinc-800 dark:text-zinc-200">{d.title}</span>
                      <span className="flex items-center gap-2 text-[11px] text-zinc-500">
                        {d.topic ? <Tag>{d.topic}</Tag> : <span className="text-zinc-400 dark:text-zinc-600">미분류</span>}
                        <span className="truncate">{d.sourceName}</span>
                        <span className="ml-auto shrink-0 font-mono">{d.createdAt}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* 본문 뷰어 */}
          <Card className="overflow-hidden p-0 lg:sticky lg:top-5 lg:h-fit">
            {!selectedId ? (
              <div className="flex min-h-72 flex-col items-center justify-center bg-gradient-to-br from-sky-50 via-white to-violet-50 px-8 text-center dark:from-sky-950/30 dark:via-zinc-950 dark:to-violet-950/30">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-2xl text-sky-600 shadow-sm ring-1 ring-sky-100 dark:bg-zinc-900 dark:text-sky-400 dark:ring-sky-900">▤</span>
                <p className="mt-4 text-sm font-semibold text-zinc-900 dark:text-zinc-100">문서 상세 정보</p>
                <p className="mt-1.5 max-w-xs text-xs leading-5 text-zinc-500">
                  왼쪽 목록에서 문서를 선택하면 수집 경로, 분류, 주요 통계와 추출 원문을 확인할 수 있습니다.
                </p>
              </div>
            ) : contentLoading ? (
              <div className="flex min-h-72 items-center justify-center bg-sky-50/40 dark:bg-sky-950/20">
                <p className="animate-pulse text-sm font-medium text-sky-600 dark:text-sky-400">문서 정보 불러오는 중…</p>
              </div>
            ) : contentError ? (
              <p className="px-5 py-8 text-center text-sm text-red-600 dark:text-red-400">{contentError}</p>
            ) : (
              <div className="flex max-h-[74vh] flex-col">
                <div className={`h-1.5 shrink-0 ${sourceVisual.accent}`} />
                <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
                  <div className="flex items-start gap-3">
                    <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg font-bold ${sourceVisual.soft} ${sourceVisual.text}`}>
                      {sourceVisual.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${sourceVisual.soft} ${sourceVisual.text}`}>
                          {sourceVisual.label}
                        </span>
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                          ● {contentDoc?.status}
                        </span>
                      </div>
                      <h2 className="mt-2 text-base font-semibold leading-6 text-zinc-950 dark:text-zinc-50">{contentDoc?.title}</h2>
                      {contentDoc?.filename && !/^https?:\/\//.test(contentDoc.filename) && (
                        <p className="mt-1 truncate font-mono text-[10px] text-zinc-400">{contentDoc.filename}</p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col gap-1.5">
                      {contentDoc && !contentDoc.topic && (
                        <button
                          onClick={() => classifyOne(contentDoc.id)}
                          disabled={classifyingId === contentDoc.id}
                          className="rounded-lg bg-violet-600 px-3 py-2 text-[11px] font-medium text-white hover:bg-violet-500 disabled:opacity-40"
                        >
                          {classifyingId === contentDoc.id ? "분류 중…" : "AI 주제 분류"}
                        </button>
                      )}
                      {contentDoc?.filename && /^https?:\/\//.test(contentDoc.filename) && (
                        <a
                          href={contentDoc.filename}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rounded-lg bg-sky-600 px-3 py-2 text-center text-[11px] font-medium text-white shadow-sm hover:bg-sky-500"
                        >
                          원본 열기 ↗
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-blue-100 bg-blue-50/70 px-3 py-2.5 dark:border-blue-900/60 dark:bg-blue-950/30">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-blue-500">수집 소스</p>
                      <p className="mt-1 truncate text-xs font-semibold text-blue-900 dark:text-blue-100">{contentDoc?.sourceName}</p>
                    </div>
                    <div className="rounded-lg border border-violet-100 bg-violet-50/70 px-3 py-2.5 dark:border-violet-900/60 dark:bg-violet-950/30">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-violet-500">분류 주제</p>
                      <p className="mt-1 text-xs font-semibold text-violet-900 dark:text-violet-100">{contentDoc?.topic ?? "미분류"}</p>
                    </div>
                    <div className="rounded-lg border border-emerald-100 bg-emerald-50/70 px-3 py-2.5 dark:border-emerald-900/60 dark:bg-emerald-950/30">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-emerald-500">발행일</p>
                      <p className="mt-1 font-mono text-xs font-semibold text-emerald-900 dark:text-emerald-100">{contentDoc?.publishedAt ?? "미상"}</p>
                    </div>
                    <div className="rounded-lg border border-amber-100 bg-amber-50/70 px-3 py-2.5 dark:border-amber-900/60 dark:bg-amber-950/30">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-amber-500">수집 시각</p>
                      <p className="mt-1 font-mono text-xs font-semibold text-amber-900 dark:text-amber-100">{contentDoc?.createdAt}</p>
                    </div>
                  </div>

                  {contentStats && (
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg bg-zinc-100 px-3 py-2 text-[11px] text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
                      <span><strong className="text-zinc-900 dark:text-zinc-100">{contentStats.chars.toLocaleString()}</strong>자</span>
                      <span><strong className="text-zinc-900 dark:text-zinc-100">{contentStats.lines.toLocaleString()}</strong>개 문단</span>
                      <span><strong className="text-zinc-900 dark:text-zinc-100">{contentStats.numbers.toLocaleString()}</strong>개 수치</span>
                      {contentStats.sections > 0 && <span><strong className="text-zinc-900 dark:text-zinc-100">{contentStats.sections}</strong>개 섹션</span>}
                    </div>
                  )}
                </div>
                {content === null ? (
                  <p className="px-5 py-8 text-sm text-zinc-500">
                    본문을 읽을 수 없는 문서입니다(바이너리 또는 텍스트 없음).
                  </p>
                ) : (
                  <div className="overflow-y-auto bg-white px-5 py-4 dark:bg-zinc-950">
                    <div className="sticky top-0 z-10 -mx-5 -mt-4 mb-3 flex items-center justify-between border-b border-zinc-200 bg-white/95 px-5 py-2.5 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/95">
                      <div>
                        <p className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">추출 본문</p>
                        <p className="text-[10px] text-zinc-500">검색·Q&A에 사용되는 실제 텍스트</p>
                      </div>
                      {contentDoc?.topic && <Tag>{contentDoc.topic}</Tag>}
                    </div>
                    <Markdown text={content} className="text-sm leading-7 text-zinc-700 dark:text-zinc-300 [&_strong]:rounded [&_strong]:bg-amber-100 [&_strong]:px-1 dark:[&_strong]:bg-amber-950/60" />
                    {content.length >= 50000 && (
                      <p className="mt-3 text-[11px] text-amber-600/70 dark:text-amber-400/70">
                        ⚠️ 본문이 길어 최대 5만자까지만 표시했습니다.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
