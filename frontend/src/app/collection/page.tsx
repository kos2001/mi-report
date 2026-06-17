"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type CollectedDoc,
  type Source,
  type SourceType,
  SOURCE_TYPE_LABEL,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

type Tab = "sources" | "status" | "upload" | "documents";

// 4개 탭을 두 엔티티 그룹으로 묶어 시각적으로 구분한다.
// 소스(어디서) = 소스 정의 + 상태·수집 / 문서(무엇을) = 업로드 + 조회.
const TAB_GROUPS: {
  group: string;
  hint: string;
  tabs: { key: Tab; label: string }[];
}[] = [
  {
    group: "소스",
    hint: "어디서 들어오나",
    tabs: [
      { key: "sources", label: "소스" },
      { key: "status", label: "상태·수집" },
    ],
  },
  {
    group: "문서",
    hint: "무엇이 들어왔나",
    tabs: [
      { key: "upload", label: "업로드" },
      { key: "documents", label: "문서" },
    ],
  },
];

const CONNECTOR_TYPES: SourceType[] = ["edm", "confluence", "news", "broker", "consensus"];

function statusColor(status: string) {
  if (status === "정상") return "text-emerald-400";
  if (status === "지연") return "text-amber-400";
  if (status === "오류") return "text-red-400";
  return "text-zinc-400";
}

// 소스 삭제(확인창 포함). 소스와 그 소스로 수집된 문서까지 함께 제거된다.
async function deleteSourceWithConfirm(s: Source, onChange: () => void) {
  const msg =
    s.count > 0
      ? `'${s.name}' 소스와 수집된 문서 ${s.count}건을 모두 삭제할까요?`
      : `'${s.name}' 소스를 삭제할까요?`;
  if (!window.confirm(msg)) return;
  try {
    await api.deleteSource(s.id);
  } finally {
    onChange();
  }
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

      <div className="mb-6">
        <div className="flex flex-wrap items-end gap-3">
          {TAB_GROUPS.map((g, gi) => (
            <Fragment key={g.group}>
              {gi > 0 && (
                <span className="mb-2 select-none px-1 text-lg text-zinc-600" aria-hidden>
                  →
                </span>
              )}
              <div>
                <p className="mb-1 px-1 text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                  {g.group} <span className="text-zinc-600">· {g.hint}</span>
                </p>
                <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/40 p-1">
                  {g.tabs.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      className={`rounded-md px-3.5 py-1.5 text-sm transition-colors ${
                        tab === t.key
                          ? "bg-zinc-800 font-medium text-zinc-50"
                          : "text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
            </Fragment>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-zinc-500">
          <span className="text-zinc-400">소스</span>(어디서) →{" "}
          <span className="text-zinc-400">문서</span>(무엇을). ‘상태·수집’의 ‘지금 수집’(자동)과
          ‘업로드’(수동)가 각각 문서를 만들고, 모든 문서는 소스에 귀속됩니다.
        </p>
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
// 소스 타입마다 필요한 입력(config)이 다르므로 타입별 필드 정의로 폼을 동적 구성한다.
type FieldKind = "text" | "csv";
type FieldDef = { key: string; label: string; placeholder: string; kind: FieldKind };

// 폼에서 생성 가능한 타입(업로드는 ‘업로드’ 탭에서 파일로 생성되므로 제외).
const CREATE_TYPES: SourceType[] = ["news", "broker", "consensus", "confluence", "sec", "dart", "edm"];

const TYPE_FIELDS: Record<SourceType, FieldDef[]> = {
  news: [
    { key: "url", label: "수집 URL", placeholder: "https://news.naver.com/section/105", kind: "text" },
    { key: "keywords", label: "키워드 (쉼표 구분)", placeholder: "반도체, HBM, 파운드리", kind: "csv" },
  ],
  broker: [
    { key: "url", label: "수집 URL", placeholder: "https://consensus.hankyung.com/", kind: "text" },
  ],
  consensus: [
    { key: "tickers", label: "티커 (쉼표 구분)", placeholder: "QCOM, MTK, 005930", kind: "csv" },
  ],
  confluence: [
    { key: "base_url", label: "Confluence 기본 URL", placeholder: "https://<site>.atlassian.net/wiki", kind: "text" },
  ],
  sec: [
    { key: "cik", label: "SEC CIK", placeholder: "0000804328 (Qualcomm)", kind: "text" },
    { key: "name", label: "회사명 (선택)", placeholder: "Qualcomm", kind: "text" },
  ],
  dart: [
    { key: "corp_code", label: "DART corp_code", placeholder: "00126380 (8자리 고유번호)", kind: "text" },
    { key: "name", label: "회사명 (선택)", placeholder: "삼성전자", kind: "text" },
  ],
  edm: [
    { key: "path", label: "EDM 경로", placeholder: "EDM 루트 경로", kind: "text" },
  ],
  upload: [],
};

const TYPE_HINT: Record<SourceType, string> = {
  news: "기사/섹션 URL 의 본문을 가져와 문서로 저장합니다. 동적 포털 홈보다 기사 URL 을 권장.",
  broker: "증권사 리포트 집계 페이지 URL. ‘지금 수집’이 실제로 페이지를 가져옵니다.",
  consensus: "추적할 종목 티커 목록(쉼표 구분). 목표주가·투자의견 변동 감지용.",
  confluence: "Atlassian Cloud wiki 기본 URL. 자격증명은 백엔드 .env(CONFLUENCE_EMAIL/API_TOKEN).",
  sec: "SEC EDGAR(미국 공시)에서 경쟁사 실 IR·재무를 수집. CIK 는 SEC 기업 고유번호(예: 퀄컴 0000804328).",
  dart: "DART(한국 전자공시)에서 경쟁사 실 개황·공시·재무를 수집. 백엔드 .env 에 DART_API_KEY 필요.",
  edm: "사내 EDM 루트 경로(인제스트 워커가 사용).",
  upload: "",
};

function SourcesTab({ sources, onChange }: { sources: Source[]; onChange: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<SourceType>("news");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changeType = (t: SourceType) => {
    setType(t);
    setFields({}); // 타입이 바뀌면 이전 타입의 입력값은 초기화
  };
  const setField = (k: string, v: string) =>
    setFields((prev) => ({ ...prev, [k]: v }));

  const add = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      // 타입별 필드를 config 로 변환(csv 는 배열로, 빈 값은 생략).
      const config: Record<string, unknown> = {};
      for (const f of TYPE_FIELDS[type]) {
        const raw = (fields[f.key] ?? "").trim();
        if (!raw) continue;
        config[f.key] =
          f.kind === "csv"
            ? raw.split(",").map((s) => s.trim()).filter(Boolean)
            : raw;
      }
      await api.createSource({
        name: name.trim(),
        type,
        config: Object.keys(config).length ? config : undefined,
      });
      setName("");
      setFields({});
      onChange();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "소스 추가 실패 — 백엔드 연결을 확인하세요 (http://localhost:8000)",
      );
    } finally {
      setBusy(false);
    }
  };

  const defs = TYPE_FIELDS[type];

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <p className="mb-3 text-sm font-medium text-zinc-200">소스 추가</p>
        <div className="flex flex-col gap-3">
          {/* 1행: 이름 + 타입 — 타입에 따라 아래 입력 폼이 바뀐다 */}
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="소스 이름"
              className="w-52 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
            />
            <select
              value={type}
              onChange={(e) => changeType(e.target.value as SourceType)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
            >
              {CREATE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {SOURCE_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>

          {/* 2행: 타입별 동적 입력 필드 */}
          {defs.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {defs.map((f) => (
                <label key={f.key} className="flex flex-col gap-1">
                  <span className="text-[11px] text-zinc-500">{f.label}</span>
                  <input
                    value={fields[f.key] ?? ""}
                    onChange={(e) => setField(f.key, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !busy) add();
                    }}
                    placeholder={f.placeholder}
                    className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
                  />
                </label>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] text-zinc-500">{TYPE_HINT[type]}</p>
            <button
              onClick={add}
              disabled={busy || !name.trim()}
              className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
            >
              {busy ? "추가 중…" : "추가"}
            </button>
          </div>
        </div>
        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
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
              {/* 활성 ↔ 비활성 토글: 현재 상태를 보여주고 클릭하면 전환된다 */}
              <button
                onClick={() => api.updateSource(s.id, { enabled: !s.enabled }).then(onChange)}
                title={s.enabled ? "클릭하면 비활성화" : "클릭하면 활성화"}
                aria-pressed={s.enabled}
                className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                  s.enabled
                    ? "border-emerald-800/60 bg-emerald-950/60 text-emerald-400 hover:bg-emerald-900/40"
                    : "border-zinc-700 bg-zinc-800 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {s.enabled ? "● 활성" : "○ 비활성"}
              </button>
              <button
                onClick={() => deleteSourceWithConfirm(s, onChange)}
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

// 소스 출처 설정(config)을 사람이 읽기 쉬운 문자열로.
function formatConfigValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const CONFIG_LABEL: Record<string, string> = {
  url: "URL",
  urls: "URL 목록",
  keywords: "키워드",
  path: "경로",
  space: "스페이스",
  base_url: "기본 URL",
  tickers: "티커",
  sources: "하위 소스",
  house: "리서치하우스",
};

// ── 상태·수집 탭 ─────────────────────────────────────────────────────
function StatusTab({ sources, onChange }: { sources: Source[]; onChange: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, { ok: boolean; msg: string }>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [docsBySource, setDocsBySource] = useState<Record<string, CollectedDoc[]>>({});
  const [docsLoading, setDocsLoading] = useState<string | null>(null);

  const loadDocs = async (id: string) => {
    setDocsLoading(id);
    try {
      const docs = await api.listDocuments({ source: id });
      setDocsBySource((prev) => ({ ...prev, [id]: docs }));
    } catch {
      setDocsBySource((prev) => ({ ...prev, [id]: [] }));
    } finally {
      setDocsLoading(null);
    }
  };

  const toggleExpand = (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (!docsBySource[id]) loadDocs(id);
  };

  const collect = async (s: Source) => {
    setBusyId(s.id);
    try {
      const r = await api.collect(s.id);
      const msg = r.stub
        ? "URL 미설정 — 실행 기록만 갱신(스텁)"
        : `${r.ingested}건 수집됨${r.errors && r.errors.length ? ` · 실패 ${r.errors.length}` : ""}`;
      setResult((prev) => ({ ...prev, [s.id]: { ok: true, msg } }));
      // 수집 후 해당 소스의 문서 목록을 갱신(펼쳐져 있으면 즉시 반영)
      loadDocs(s.id);
      onChange();
    } catch (e) {
      // 수집 실패(예: 본문 추출 실패)를 사용자에게 노출한다.
      setResult((prev) => ({
        ...prev,
        [s.id]: { ok: false, msg: e instanceof Error ? e.message : "수집 실패" },
      }));
    } finally {
      setBusyId(null);
    }
  };

  // 하위 문서(subitem) 삭제 — 해당 소스의 문서 목록과 누적 카운트를 갱신한다.
  const deleteDoc = async (sourceId: string, docId: string) => {
    try {
      await api.deleteDocument(docId);
    } finally {
      loadDocs(sourceId);
      onChange();
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
            const open = expandedId === s.id;
            const configEntries = Object.entries(s.config ?? {});
            const docs = docsBySource[s.id];
            return (
              <Fragment key={s.id}>
                <tr className="border-b border-zinc-800/60 last:border-0">
                  <td className="px-5 py-3 text-zinc-200">
                    <button
                      onClick={() => toggleExpand(s.id)}
                      title="출처 상세 보기"
                      className="flex items-center gap-2 text-left hover:text-sky-300"
                    >
                      <span className="w-3 text-xs text-zinc-500">{open ? "▾" : "▸"}</span>
                      <span>
                        {s.name}{" "}
                        <span className="ml-1 text-xs text-zinc-500">
                          {SOURCE_TYPE_LABEL[s.type]}
                        </span>
                      </span>
                    </button>
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
                      <div className="flex flex-col items-end gap-1">
                        <button
                          onClick={() => collect(s)}
                          disabled={!s.enabled || busyId === s.id}
                          title={!s.enabled ? "비활성 소스" : "URL 이 있으면 실제 수집, 없으면 스텁"}
                          className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-40"
                        >
                          {busyId === s.id ? "수집 중…" : "지금 수집"}
                        </button>
                        {result[s.id] && (
                          <span
                            className={`text-[11px] ${result[s.id].ok ? "text-emerald-400" : "text-red-400"}`}
                          >
                            {result[s.id].msg.slice(0, 60)}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-zinc-600">업로드 전용</span>
                    )}
                  </td>
                </tr>
                {open && (
                  <tr className="border-b border-zinc-800/60 bg-zinc-900/40">
                    <td colSpan={5} className="px-5 py-4">
                      <div className="grid gap-5 sm:grid-cols-2">
                        {/* 출처 설정 */}
                        <div>
                          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                            출처 설정
                          </p>
                          <dl className="flex flex-col gap-1 text-xs">
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">타입</dt>
                              <dd className="text-zinc-300">{SOURCE_TYPE_LABEL[s.type]}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">활성</dt>
                              <dd className="text-zinc-300">{s.enabled ? "예" : "아니오"}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">생성일</dt>
                              <dd className="font-mono text-zinc-400">{s.createdAt}</dd>
                            </div>
                            {configEntries.length === 0 ? (
                              <p className="mt-1 text-zinc-600">추가 설정 없음</p>
                            ) : (
                              configEntries.map(([k, v]) => (
                                <div key={k} className="flex gap-2">
                                  <dt className="w-20 shrink-0 text-zinc-500">
                                    {CONFIG_LABEL[k] ?? k}
                                  </dt>
                                  <dd className="break-all text-zinc-300">
                                    {k === "url" ? (
                                      <a
                                        href={String(v)}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-sky-400 hover:underline"
                                      >
                                        {formatConfigValue(v)}
                                      </a>
                                    ) : (
                                      formatConfigValue(v)
                                    )}
                                  </dd>
                                </div>
                              ))
                            )}
                          </dl>
                        </div>
                        {/* 수집된 문서 */}
                        <div>
                          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
                            수집된 문서 {docs ? `(${docs.length})` : ""}
                          </p>
                          {docsLoading === s.id ? (
                            <p className="text-xs text-zinc-500">불러오는 중…</p>
                          ) : !docs || docs.length === 0 ? (
                            <p className="text-xs text-zinc-600">이 소스로 수집된 문서가 없습니다.</p>
                          ) : (
                            <ul className="flex flex-col gap-1.5">
                              {docs.map((d) => (
                                <li key={d.id} className="flex items-center gap-2 text-xs">
                                  <span className="truncate text-zinc-300">{d.title}</span>
                                  {d.topic && <Tag>{d.topic}</Tag>}
                                  <span className="ml-auto shrink-0 font-mono text-zinc-500">
                                    {d.createdAt}
                                  </span>
                                  <button
                                    onClick={() => deleteDoc(s.id, d.id)}
                                    title="이 문서 삭제"
                                    className="shrink-0 rounded px-1.5 py-0.5 text-zinc-500 hover:text-red-400"
                                  >
                                    삭제
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-zinc-800 px-5 py-2.5 text-[11px] text-amber-400/70">
        ⚠️ URL 이 설정된 소스는 실제로 페이지를 가져옵니다. URL 이 없는 소스는 스텁(실행 기록만 갱신)입니다.
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
