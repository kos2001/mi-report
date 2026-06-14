"use client";

import { useCallback, useEffect, useState } from "react";
import {
  artifactsApi,
  type ArtifactFull,
  type ArtifactMeta,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

const KIND_LABEL: Record<string, string> = {
  digest: "다이제스트",
  topic: "주제 요약",
  competitor: "경쟁사 분석",
  report: "주간 리포트",
};
const KIND_BADGE: Record<string, string> = {
  digest: "border-sky-800 bg-sky-950/50 text-sky-300",
  topic: "border-amber-800 bg-amber-950/50 text-amber-300",
  competitor: "border-violet-800 bg-violet-950/50 text-violet-300",
  report: "border-emerald-800 bg-emerald-950/50 text-emerald-300",
};
const FILTERS: { key: string; label: string }[] = [
  { key: "", label: "전체" },
  { key: "digest", label: "다이제스트" },
  { key: "topic", label: "주제" },
  { key: "competitor", label: "경쟁사" },
  { key: "report", label: "리포트" },
];

function KindBadge({ kind }: { kind: string }) {
  return (
    <span
      className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${
        KIND_BADGE[kind] ?? "border-zinc-700 bg-zinc-800 text-zinc-300"
      }`}
    >
      {KIND_LABEL[kind] ?? kind}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">{title}</p>
      {children}
    </div>
  );
}

// 생성물 payload 를 종류별로 읽기 쉽게 렌더링.
function Detail({ artifact }: { artifact: ArtifactFull }) {
  const p = artifact.payload as Record<string, unknown>;
  const strArr = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
  const objArr = (v: unknown): Record<string, unknown>[] =>
    Array.isArray(v) ? (v as Record<string, unknown>[]) : [];

  return (
    <Card>
      <div className="flex items-center gap-2">
        <KindBadge kind={artifact.kind} />
        <h2 className="text-base font-semibold text-zinc-50">{artifact.title}</h2>
        <span className="ml-auto text-xs text-zinc-500">{artifact.createdAt}</span>
      </div>

      {(artifact.kind === "digest" || artifact.kind === "report") && (
        <>
          {typeof p.overview === "string" && (
            <Section title="총평">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
                {p.overview as string}
              </p>
            </Section>
          )}
          {objArr((p.digest as Record<string, unknown>)?.items ?? p.items).length > 0 && (
            <Section title="다이제스트 항목">
              <ul className="flex flex-col gap-2">
                {objArr((p.digest as Record<string, unknown>)?.items ?? p.items).map((it, i) => (
                  <li key={i} className="rounded-lg bg-zinc-800/40 px-3 py-2">
                    <p className="text-sm font-medium text-zinc-100">
                      [{String(it.impact ?? "")}] {String(it.title ?? "")}
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-400">
                      {String(it.summary ?? "")}
                    </p>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {objArr(p.topics).length > 0 && (
            <Section title="주제 요약">
              <ul className="flex flex-col gap-1.5">
                {objArr(p.topics).map((t, i) => (
                  <li key={i} className="text-sm text-zinc-300">
                    · <span className="font-medium text-zinc-100">{String(t.title ?? "")}</span> —{" "}
                    {String(t.summary ?? "").slice(0, 100)}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </>
      )}

      {artifact.kind === "topic" && (
        <>
          <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
            <Tag>{String(p.category ?? "")}</Tag>
            <span>소스 {String(p.sourceCount ?? "")}건</span>
          </div>
          <Section title="요약">
            <p className="text-sm leading-relaxed text-zinc-200">{String(p.summary ?? "")}</p>
          </Section>
          <Section title="인사이트">
            <p className="text-sm leading-relaxed text-zinc-200">{String(p.insight ?? "")}</p>
          </Section>
          {objArr(p.history).length > 0 && (
            <Section title="History">
              <ul className="flex flex-col gap-1 text-sm text-zinc-300">
                {objArr(p.history).map((h, i) => (
                  <li key={i}>
                    <span className="font-mono text-xs text-zinc-500">{String(h.date ?? "")}</span>{" "}
                    {String(h.event ?? "")}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </>
      )}

      {artifact.kind === "competitor" && (
        <>
          <Section title="컨퍼런스콜 요약">
            <ul className="flex flex-col gap-1 text-sm text-zinc-300">
              {strArr(p.callSummary).map((s, i) => (
                <li key={i}>· {s}</li>
              ))}
            </ul>
          </Section>
          <Section title="전분기 대비 변화">
            <ul className="flex flex-col gap-1 text-sm text-zinc-300">
              {strArr(p.qoqChanges).map((s, i) => (
                <li key={i}>· {s}</li>
              ))}
            </ul>
          </Section>
        </>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
          원본 JSON 보기
        </summary>
        <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-zinc-950 p-3 text-[11px] text-zinc-400">
          {JSON.stringify(artifact.payload, null, 2)}
        </pre>
      </details>
    </Card>
  );
}

export default function HistoryPage() {
  const [kind, setKind] = useState("");
  const [items, setItems] = useState<ArtifactMeta[]>([]);
  const [selected, setSelected] = useState<ArtifactFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((k: string) => {
    artifactsApi
      .list({ kind: k || undefined, limit: 100 })
      .then((d) => {
        setItems(d.artifacts);
        setError(null);
      })
      .catch(() => setError("백엔드 미연결 (http://localhost:8000)"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(kind);
  }, [kind, load]);

  async function open(id: string) {
    try {
      setSelected(await artifactsApi.get(id));
    } catch {
      /* 무시 */
    }
  }

  return (
    <>
      <PageHeader
        title="생성물 이력"
        description="AI 가 생성한 다이제스트·주제·경쟁사·리포트가 시점별로 누적됩니다 (지식 자산)"
      />

      <div className="mb-6 flex gap-1 border-b border-zinc-800">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => {
              setKind(f.key);
              setSelected(null);
            }}
            className={`-mb-px border-b-2 px-4 py-2 text-sm transition-colors ${
              kind === f.key
                ? "border-sky-400 font-medium text-zinc-50"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-5 rounded-lg border border-amber-900/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,360px)_1fr]">
        {/* 목록 */}
        <Card className="p-0">
          {loading ? (
            <p className="px-5 py-6 text-sm text-zinc-500">불러오는 중…</p>
          ) : items.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">
              아직 생성물이 없습니다. 다이제스트·주제·경쟁사·리포트를 생성하면 여기 쌓입니다.
            </p>
          ) : (
            <ul className="divide-y divide-zinc-800/60">
              {items.map((a) => (
                <li key={a.id}>
                  <button
                    onClick={() => open(a.id)}
                    className={`flex w-full items-center gap-2 px-4 py-3 text-left transition hover:bg-zinc-800/40 ${
                      selected?.id === a.id ? "bg-zinc-800/50" : ""
                    }`}
                  >
                    <KindBadge kind={a.kind} />
                    <span className="truncate text-sm text-zinc-200">{a.title}</span>
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-zinc-500">
                      {a.createdAt}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* 상세 */}
        {selected ? (
          <Detail artifact={selected} />
        ) : (
          <Card>
            <p className="text-sm text-zinc-500">왼쪽에서 생성물을 선택하면 내용이 표시됩니다.</p>
          </Card>
        )}
      </div>
    </>
  );
}
