"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  topicsApi,
  SOURCE_TYPE_LABEL,
  type CollectedDoc,
  type Source,
  type TopicListItem,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";

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
        if (initTopic) setTopic(initTopic);
        if (initQuery) setQ(initQuery);
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
          <Card className="p-0">
            {!selectedId ? (
              <p className="px-5 py-8 text-center text-sm text-zinc-500">
                왼쪽에서 문서를 선택하면 추출된 본문이 여기에 표시됩니다.
              </p>
            ) : contentLoading ? (
              <p className="px-5 py-8 text-center text-sm text-zinc-500">본문 불러오는 중…</p>
            ) : contentError ? (
              <p className="px-5 py-8 text-center text-sm text-red-600 dark:text-red-400">{contentError}</p>
            ) : (
              <div className="flex max-h-[74vh] flex-col">
                <div className="border-b border-zinc-200 dark:border-zinc-800 px-5 py-4">
                  <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{contentDoc?.title}</h2>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                    <span>{contentDoc?.sourceName}</span>
                    {contentDoc?.topic && <Tag>{contentDoc.topic}</Tag>}
                    <span>· 수집 {contentDoc?.createdAt}</span>
                    {contentDoc?.publishedAt && <span>· 발행 {contentDoc.publishedAt}</span>}
                    {content && <span>· {content.length.toLocaleString()}자</span>}
                  </p>
                  {contentDoc?.filename && /^https?:\/\//.test(contentDoc.filename) && (
                    <a
                      href={contentDoc.filename}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-sky-600 dark:text-sky-400 hover:underline"
                    >
                      원본 보기 ↗
                    </a>
                  )}
                </div>
                {content === null ? (
                  <p className="px-5 py-8 text-sm text-zinc-500">
                    본문을 읽을 수 없는 문서입니다(바이너리 또는 텍스트 없음).
                  </p>
                ) : (
                  <div className="overflow-y-auto px-5 py-4">
                    <Markdown text={content} className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300" />
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
