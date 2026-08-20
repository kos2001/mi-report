"use client";

import Link from "next/link";
import { useState } from "react";
import { api, type AgentSource, type CollectedDoc } from "@/lib/api";
import { Markdown } from "@/components/markdown";
import { Tag } from "@/components/ui";

interface DocumentPreview {
  document: CollectedDoc;
  content: string | null;
}

function numericHighlights(text: string): string[] {
  const matches = text.match(/(?:₩|\$)?\d[\d,.]*(?:%|배|원|달러|억원|조원|년|월|일|분기|주)?/g) ?? [];
  return [...new Set(matches.filter((value) => {
    const digits = value.replace(/\D/g, "");
    const hasBusinessUnit = /[%배원달러년월일분기주]$/.test(value);
    return hasBusinessUnit || digits.length >= 2;
  }))].slice(0, 8);
}

export function QaAnswerCard({
  content,
  numbersGrounded,
  ungroundedNumbers = [],
  sources = [],
  createdAt,
  turn,
}: {
  content: string;
  numbersGrounded?: boolean;
  ungroundedNumbers?: string[];
  sources?: AgentSource[];
  createdAt?: string;
  turn?: number;
}) {
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const highlights = numericHighlights(content);
  const verified = numbersGrounded !== false;

  async function openSource(source: AgentSource) {
    if (!source.id) return;
    setPreviewLoading(source.id);
    setPreviewError(null);
    try {
      setPreview(await api.getDocument(source.id));
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "원문을 불러오지 못했습니다.");
    } finally {
      setPreviewLoading(null);
    }
  }

  return (
    <article className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-950/70 shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200/80 dark:border-zinc-800 bg-zinc-50/80 dark:bg-zinc-900/70 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-sky-600 text-xs font-bold text-white">✓</span>
          <div>
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">완료된 응답</p>
            <p className="text-[11px] text-zinc-500">
              {turn ? `${turn}번째 답변` : "에이전트 답변"}{createdAt ? ` · ${createdAt}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className={`rounded-full border px-2.5 py-1 font-medium ${
            verified
              ? "border-emerald-300/70 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
              : "border-amber-300/70 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
          }`}>
            {verified ? "✓ 수치 검증 완료" : `⚠ 미확인 수치 ${ungroundedNumbers.length}개`}
          </span>
          <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 font-medium text-sky-700 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300">
            근거 문서 {sources.length}건
          </span>
        </div>
      </header>

      {!verified && ungroundedNumbers.length > 0 && (
        <div className="mx-4 mt-4 rounded-lg border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          <strong>확인 필요:</strong> 수집 문서에서 찾지 못한 수치 · {ungroundedNumbers.join(", ")}
        </div>
      )}

      {highlights.length > 0 && (
        <section className="mx-4 mt-4 rounded-lg border border-sky-200/70 bg-sky-50/60 px-3 py-2.5 dark:border-sky-900/70 dark:bg-sky-950/30">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-sky-600 dark:text-sky-400">핵심 수치 · 시점</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {highlights.map((value) => (
              <span key={value} className="rounded-md bg-white px-2 py-1 font-mono text-xs font-semibold text-sky-800 shadow-sm dark:bg-zinc-900 dark:text-sky-200">
                {value}
              </span>
            ))}
          </div>
        </section>
      )}

      <div className="px-4 py-4">
        <Markdown
          text={content}
          className="text-sm leading-7 text-zinc-800 dark:text-zinc-200 [&_strong]:rounded [&_strong]:bg-sky-100 [&_strong]:px-1 [&_strong]:text-sky-950 dark:[&_strong]:bg-sky-950 dark:[&_strong]:text-sky-100 [&_ul]:space-y-2 [&_ol]:space-y-2"
        />
      </div>

      {sources.length > 0 && (
        <section className="border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/40 px-4 py-4">
          <div className="mb-2.5 flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">관련 수집 문서</p>
              <p className="mt-0.5 text-[11px] text-zinc-500">문서를 열어 답변 근거와 원문을 직접 대조할 수 있습니다.</p>
            </div>
            <span className="text-[11px] font-medium text-zinc-500">{sources.length}건</span>
          </div>
          <div className="grid gap-2 xl:grid-cols-2">
            {sources.map((source, index) => (
              <div key={`${source.id ?? source.title}-${index}`} className="rounded-lg border border-zinc-200 bg-white px-3 py-3 dark:border-zinc-800 dark:bg-zinc-950">
                <div className="flex items-start gap-2.5">
                  <span className="flex h-6 min-w-6 items-center justify-center rounded bg-zinc-900 font-mono text-[10px] font-bold text-white dark:bg-zinc-100 dark:text-zinc-900">
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium leading-5 text-zinc-900 dark:text-zinc-100">{source.title}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-zinc-500">
                      <Tag>{source.source}</Tag>
                      {source.publishedAt && <span>발행 {source.publishedAt}</span>}
                    </div>
                  </div>
                </div>
                <div className="mt-2.5 flex items-center gap-2 border-t border-zinc-100 pt-2 dark:border-zinc-900">
                  {source.id ? (
                    <button
                      type="button"
                      onClick={() => openSource(source)}
                      disabled={previewLoading === source.id}
                      className="text-[11px] font-medium text-sky-700 hover:text-sky-900 disabled:opacity-50 dark:text-sky-400 dark:hover:text-sky-200"
                    >
                      {previewLoading === source.id ? "원문 불러오는 중…" : "추출 원문 확인 →"}
                    </button>
                  ) : (
                    <Link
                      href={`/collection/documents?q=${encodeURIComponent(source.title)}`}
                      className="text-[11px] font-medium text-sky-700 hover:text-sky-900 dark:text-sky-400 dark:hover:text-sky-200"
                    >
                      문서 목록에서 찾기 →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
          {previewError && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{previewError}</p>}
        </section>
      )}

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/70 p-4" role="dialog" aria-modal="true" aria-label="수집 문서 원문">
          <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-zinc-300 bg-white shadow-2xl dark:border-zinc-700 dark:bg-zinc-950">
            <header className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-sky-600 dark:text-sky-400">수집 문서 원문</p>
                <h2 className="mt-1 text-base font-semibold text-zinc-950 dark:text-zinc-50">{preview.document.title}</h2>
                <p className="mt-1 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                  <span>{preview.document.sourceName}</span>
                  {preview.document.topic && <Tag>{preview.document.topic}</Tag>}
                  {preview.document.publishedAt && <span>· 발행 {preview.document.publishedAt}</span>}
                  {preview.content && <span>· {preview.content.length.toLocaleString()}자</span>}
                </p>
              </div>
              <button type="button" onClick={() => setPreview(null)} className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900">
                닫기
              </button>
            </header>
            {preview.document.filename && /^https?:\/\//.test(preview.document.filename) && (
              <div className="border-b border-zinc-200 bg-sky-50/60 px-5 py-2 dark:border-zinc-800 dark:bg-sky-950/30">
                <a href={preview.document.filename} target="_blank" rel="noopener noreferrer" className="text-xs font-medium text-sky-700 hover:underline dark:text-sky-300">
                  외부 원본 페이지 열기 ↗
                </a>
              </div>
            )}
            <div className="overflow-y-auto px-5 py-4">
              {preview.content ? (
                <Markdown text={preview.content} className="text-sm leading-7 text-zinc-700 dark:text-zinc-300" />
              ) : (
                <p className="text-sm text-zinc-500">추출된 텍스트 원문이 없습니다.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
