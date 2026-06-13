"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type CollectedDoc,
  type Source,
  type SourceType,
  SOURCE_TYPE_LABEL,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

type Tab = "sources" | "status" | "upload" | "documents";

const TABS: { key: Tab; label: string }[] = [
  { key: "sources", label: "소스" },
  { key: "status", label: "상태·수집" },
  { key: "upload", label: "업로드" },
  { key: "documents", label: "문서" },
];

const CONNECTOR_TYPES: SourceType[] = ["edm", "confluence", "news", "broker", "consensus"];

function statusColor(status: string) {
  if (status === "정상") return "text-emerald-400";
  if (status === "지연") return "text-amber-400";
  if (status === "오류") return "text-red-400";
  return "text-zinc-400";
}

export default function CollectionPage() {
  const [tab, setTab] = useState<Tab>("sources");
  const [sources, setSources] = useState<Source[]>([]);
  const [docs, setDocs] = useState<CollectedDoc[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [reloadKey, setReloadKey] = useState(0);
  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [s, d] = await Promise.all([api.listSources(), api.listDocuments()]);
        if (!alive) return;
        setSources(s);
        setDocs(d);
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
  }, [reloadKey]);

  return (
    <>
      <PageHeader
        title="데이터 수집"
        description="소스 연동 관리, 수집 상태·트리거, 수동 업로드, 수집 문서 조회"
      />

      {error && (
        <div className="mb-5 rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="mb-6 flex gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm transition-colors ${
              tab === t.key
                ? "border-sky-400 font-medium text-zinc-50"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">불러오는 중…</p>
      ) : tab === "sources" ? (
        <SourcesTab sources={sources} onChange={refresh} />
      ) : tab === "status" ? (
        <StatusTab sources={sources} onChange={refresh} />
      ) : tab === "upload" ? (
        <UploadTab onChange={refresh} />
      ) : (
        <DocumentsTab docs={docs} onChange={refresh} />
      )}
    </>
  );
}

// ── 소스 탭 ──────────────────────────────────────────────────────────
function SourcesTab({ sources, onChange }: { sources: Source[]; onChange: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<SourceType>("news");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createSource({ name: name.trim(), type });
      setName("");
      onChange();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <p className="mb-3 text-sm font-medium text-zinc-200">소스 추가</p>
        <div className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="소스 이름"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
          />
          <select
            value={type}
            onChange={(e) => setType(e.target.value as SourceType)}
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
          >
            {Object.entries(SOURCE_TYPE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <button
            onClick={add}
            disabled={busy || !name.trim()}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
          >
            추가
          </button>
        </div>
      </Card>

      <div className="flex flex-col gap-3">
        {sources.map((s) => (
          <Card key={s.id} className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Tag>{SOURCE_TYPE_LABEL[s.type]}</Tag>
              <div>
                <p className="text-sm font-medium text-zinc-100">{s.name}</p>
                <p className="text-xs text-zinc-500">
                  <span className={statusColor(s.status)}>● {s.status}</span>
                  {" · "}최근 {s.lastRun ?? "—"} · 누적 {s.count}건
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => api.updateSource(s.id, { enabled: !s.enabled }).then(onChange)}
                className={`rounded-md px-2.5 py-1 text-xs ${
                  s.enabled
                    ? "bg-emerald-950/60 text-emerald-400"
                    : "bg-zinc-800 text-zinc-500"
                }`}
              >
                {s.enabled ? "활성" : "비활성"}
              </button>
              <button
                onClick={() => api.deleteSource(s.id).then(onChange)}
                className="rounded-md px-2.5 py-1 text-xs text-zinc-500 hover:text-red-400"
              >
                삭제
              </button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ── 상태·수집 탭 ─────────────────────────────────────────────────────
function StatusTab({ sources, onChange }: { sources: Source[]; onChange: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null);

  const collect = async (s: Source) => {
    setBusyId(s.id);
    try {
      await api.collect(s.id);
      onChange();
    } catch {
      /* 무시: 상위에서 새로고침 */
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
            <th className="px-5 py-3 font-medium">소스</th>
            <th className="px-5 py-3 font-medium">상태</th>
            <th className="px-5 py-3 font-medium">최근 실행</th>
            <th className="px-5 py-3 text-right font-medium">누적</th>
            <th className="px-5 py-3 text-right font-medium">작업</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => {
            const connector = CONNECTOR_TYPES.includes(s.type);
            return (
              <tr key={s.id} className="border-b border-zinc-800/60 last:border-0">
                <td className="px-5 py-3 text-zinc-200">
                  {s.name}{" "}
                  <span className="ml-1 text-xs text-zinc-500">
                    {SOURCE_TYPE_LABEL[s.type]}
                  </span>
                </td>
                <td className="px-5 py-3">
                  <span className={statusColor(s.status)}>● {s.status}</span>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-zinc-400">
                  {s.lastRun ?? "—"}
                </td>
                <td className="px-5 py-3 text-right font-mono text-xs text-zinc-300">
                  {s.count}
                </td>
                <td className="px-5 py-3 text-right">
                  {connector ? (
                    <button
                      onClick={() => collect(s)}
                      disabled={!s.enabled || busyId === s.id}
                      title={!s.enabled ? "비활성 소스" : "수집 트리거(스텁)"}
                      className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-40"
                    >
                      {busyId === s.id ? "수집 중…" : "지금 수집"}
                    </button>
                  ) : (
                    <span className="text-xs text-zinc-600">업로드 전용</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-zinc-800 px-5 py-2.5 text-[11px] text-amber-400/70">
        ⚠️ 커넥터 수집은 현재 스텁입니다(실행 기록만 갱신). 실제 크롤링 연동은 이후 단계.
      </p>
    </Card>
  );
}

// ── 업로드 탭 ────────────────────────────────────────────────────────
function UploadTab({ onChange }: { onChange: () => void }) {
  const [topic, setTopic] = useState("");
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        await api.upload(f, topic || undefined);
        setRecent((r) => [f.name, ...r].slice(0, 8));
      }
      onChange();
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <label className="mb-2 block text-xs text-zinc-500">주제 태그 (선택)</label>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="예: HBM, 파운드리"
          className="mb-4 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
        />
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            handleFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
            drag
              ? "border-sky-500 bg-sky-950/30"
              : "border-zinc-700 hover:border-zinc-600"
          }`}
        >
          <p className="text-sm text-zinc-300">
            {uploading ? "업로드 중…" : "파일을 드래그하거나 클릭해서 선택"}
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            컨설팅 자료·로컬 문서 (PDF, 엑셀, 텍스트 등)
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>
      </Card>

      {recent.length > 0 && (
        <Card>
          <p className="mb-2 text-xs text-zinc-500">방금 업로드</p>
          <ul className="flex flex-col gap-1">
            {recent.map((n, i) => (
              <li key={n + i} className="text-sm text-zinc-300">
                ✓ {n}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

// ── 문서 탭 ──────────────────────────────────────────────────────────
function DocumentsTab({ docs, onChange }: { docs: CollectedDoc[]; onChange: () => void }) {
  const [q, setQ] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const filtered = q
    ? docs.filter(
        (d) =>
          d.title.toLowerCase().includes(q.toLowerCase()) ||
          (d.topic ?? "").toLowerCase().includes(q.toLowerCase()),
      )
    : docs;

  const untaggedCount = docs.filter((d) => !d.topic).length;

  const classifyOne = async (id: string) => {
    setBusyId(id);
    try {
      await api.classifyDocument(id);
      onChange();
    } catch {
      /* 상위 새로고침 */
    } finally {
      setBusyId(null);
    }
  };

  const classifyAll = async () => {
    setBatchBusy(true);
    try {
      await api.classifyUntagged();
      onChange();
    } catch {
      /* 상위 새로고침 */
    } finally {
      setBatchBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="제목·주제로 검색"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
        />
        <button
          onClick={classifyAll}
          disabled={batchBusy || untaggedCount === 0}
          title="주제가 비어 있는 문서를 AI 로 일괄 분류"
          className="shrink-0 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {batchBusy ? "분류 중…" : `미분류 자동 분류${untaggedCount ? ` (${untaggedCount})` : ""}`}
        </button>
      </div>
      <Card className="p-0">
        {filtered.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-zinc-500">
            수집된 문서가 없습니다. 업로드 탭에서 파일을 추가하세요.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                <th className="px-5 py-3 font-medium">제목</th>
                <th className="px-5 py-3 font-medium">출처</th>
                <th className="px-5 py-3 font-medium">주제</th>
                <th className="px-5 py-3 font-medium">수집일</th>
                <th className="px-5 py-3 text-right font-medium" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id} className="border-b border-zinc-800/60 last:border-0">
                  <td className="px-5 py-3 text-zinc-200">{d.title}</td>
                  <td className="px-5 py-3 text-xs text-zinc-400">{d.sourceName}</td>
                  <td className="px-5 py-3">
                    {d.topic ? <Tag>{d.topic}</Tag> : <span className="text-xs text-zinc-600">—</span>}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-zinc-400">
                    {d.createdAt}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {!d.topic && (
                        <button
                          onClick={() => classifyOne(d.id)}
                          disabled={busyId === d.id}
                          className="text-xs text-sky-400 hover:text-sky-300 disabled:opacity-50"
                        >
                          {busyId === d.id ? "분류 중…" : "분류"}
                        </button>
                      )}
                      <button
                        onClick={() => api.deleteDocument(d.id).then(onChange)}
                        className="text-xs text-zinc-500 hover:text-red-400"
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
