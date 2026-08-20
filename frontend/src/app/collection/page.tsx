"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  type Source,
  type SourceType,
  SOURCE_TYPE_LABEL,
} from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";
import { SourceOperationalStatus } from "@/components/source-operational-status";

type Tab = "manage" | "upload";

const CONNECTOR_TYPES: SourceType[] = [
  "confluence", "sec", "dart", "hankyung", "news", "broker", "consensus",
];

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
  const [tab, setTab] = useState<Tab>("manage");
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [reloadKey, setReloadKey] = useState(0);
  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await api.listSources();
        if (!alive) return;
        setSources(s);
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
        <div className="mb-5 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="mb-6 grid gap-2 sm:grid-cols-4">
        <button onClick={() => setTab("manage")} className={`rounded-xl border px-4 py-3 text-left transition ${tab === "manage" ? "border-sky-300 bg-sky-50 ring-1 ring-sky-200 dark:border-sky-800 dark:bg-sky-950/40 dark:ring-sky-900" : "border-zinc-200 bg-white hover:border-sky-200 dark:border-zinc-800 dark:bg-zinc-950"}`}>
          <span className="text-[10px] font-semibold text-sky-600 dark:text-sky-400">STEP 1</span>
          <span className="mt-1 block text-sm font-semibold text-zinc-900 dark:text-zinc-100">소스·수집</span>
          <span className="mt-0.5 block text-[11px] text-zinc-500">연결 설정 · 상태 · 실행</span>
        </button>
        <button onClick={() => setTab("upload")} className={`rounded-xl border px-4 py-3 text-left transition ${tab === "upload" ? "border-violet-300 bg-violet-50 ring-1 ring-violet-200 dark:border-violet-800 dark:bg-violet-950/40 dark:ring-violet-900" : "border-zinc-200 bg-white hover:border-violet-200 dark:border-zinc-800 dark:bg-zinc-950"}`}>
          <span className="text-[10px] font-semibold text-violet-600 dark:text-violet-400">STEP 2</span>
          <span className="mt-1 block text-sm font-semibold text-zinc-900 dark:text-zinc-100">파일 업로드</span>
          <span className="mt-0.5 block text-[11px] text-zinc-500">로컬 자료 직접 투입</span>
        </button>
        <Link href="/collection/documents" className="rounded-xl border border-zinc-200 bg-white px-4 py-3 text-left transition hover:border-emerald-300 hover:bg-emerald-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-emerald-800 dark:hover:bg-emerald-950/30">
          <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">STEP 3 ↗</span>
          <span className="mt-1 block text-sm font-semibold text-zinc-900 dark:text-zinc-100">수집 문서</span>
          <span className="mt-0.5 block text-[11px] text-zinc-500">검색 · 분류 · 원문 확인</span>
        </Link>
        <Link href="/collection/results" className="rounded-xl border border-zinc-200 bg-white px-4 py-3 text-left transition hover:border-amber-300 hover:bg-amber-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-amber-800 dark:hover:bg-amber-950/30">
          <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400">STEP 4 ↗</span>
          <span className="mt-1 block text-sm font-semibold text-zinc-900 dark:text-zinc-100">수집 결과</span>
          <span className="mt-0.5 block text-[11px] text-zinc-500">현황 · 검색 인프라</span>
        </Link>
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">불러오는 중…</p>
      ) : tab === "manage" ? (
        <div className="flex flex-col gap-5">
          <SourcesTab onChange={refresh} />
          <StatusTab sources={sources} onChange={refresh} />
        </div>
      ) : (
        <UploadTab onChange={refresh} />
      )}
    </>
  );
}

// ── 소스 탭 ──────────────────────────────────────────────────────────
// 소스 타입마다 필요한 입력(config)이 다르므로 타입별 필드 정의로 폼을 동적 구성한다.
type FieldKind = "text" | "csv";
type FieldDef = { key: string; label: string; placeholder: string; kind: FieldKind };

// 폼에서 생성 가능한 타입(업로드는 ‘업로드’ 탭에서 파일로 생성되므로 제외).
const CREATE_TYPES: SourceType[] = ["news", "broker", "consensus", "confluence", "sec", "dart", "hankyung", "edm"];

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
    { key: "ticker", label: "티커 (선택)", placeholder: "QCOM", kind: "text" },
  ],
  dart: [
    { key: "corp_code", label: "DART corp_code", placeholder: "00126380 (8자리 고유번호)", kind: "text" },
    { key: "name", label: "회사명 (선택)", placeholder: "삼성전자", kind: "text" },
    { key: "ticker", label: "티커 (선택)", placeholder: "005930", kind: "text" },
  ],
  hankyung: [
    { key: "limit", label: "수집 건수", placeholder: "10 (기본, 최대 30)", kind: "text" },
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
  hankyung: "한경 컨센서스 증권사 리포트 PDF 본문을 추출해 수집. (리포트 저작권은 각 증권사 — 약관 준수, 소량 권장)",
  edm: "사내 EDM 루트 경로(인제스트 워커가 사용).",
  upload: "",
};

function SourcesTab({ onChange }: { onChange: () => void }) {
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
        <p className="mb-3 text-sm font-medium text-zinc-800 dark:text-zinc-200">소스 추가</p>
        <div className="flex flex-col gap-3">
          {/* 1행: 이름 + 타입 — 타입에 따라 아래 입력 폼이 바뀐다 */}
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="소스 이름"
              className="w-52 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
            />
            <select
              value={type}
              onChange={(e) => changeType(e.target.value as SourceType)}
              className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
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
                    className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
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
          <p className="mt-3 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-3 py-2 text-xs text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
      </Card>
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

  const toggleExpand = (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
  };

  const collect = async (s: Source) => {
    setBusyId(s.id);
    try {
      const r = await api.collect(s.id);
      const msg = r.stub
        ? "URL 미설정 — 실행 기록만 갱신(스텁)"
        : `${r.ingested}건 수집됨${r.errors && r.errors.length ? ` · 실패 ${r.errors.length}` : ""}`;
      setResult((prev) => ({ ...prev, [s.id]: { ok: true, msg } }));
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

  return (
    <Card className="p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800 text-left text-xs text-zinc-500">
            <th className="px-5 py-3 font-medium">소스</th>
            <th className="px-5 py-3 font-medium">실제 운영 상태</th>
            <th className="px-5 py-3 font-medium">최근 실행 · 마지막 결과</th>
            <th className="px-5 py-3 text-right font-medium">누적</th>
            <th className="px-5 py-3 text-right font-medium">작업</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => {
            const connector = CONNECTOR_TYPES.includes(s.type);
            const open = expandedId === s.id;
            const configEntries = Object.entries(s.config ?? {});
            return (
              <Fragment key={s.id}>
                <tr className="border-b border-zinc-200/60 dark:border-zinc-800/60 last:border-0">
                  <td className="px-5 py-3 text-zinc-800 dark:text-zinc-200">
                    <button
                      onClick={() => toggleExpand(s.id)}
                      title="출처 상세 보기"
                      className="flex items-center gap-2 text-left hover:text-sky-700 dark:hover:text-sky-300"
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
                    <SourceOperationalStatus source={s} showReason />
                  </td>
                  <td className="px-5 py-3 text-xs text-zinc-600 dark:text-zinc-400">
                    <p className="font-mono">{s.lastRun ?? "실행 없음"}</p>
                    <p className="mt-1 text-[11px] text-zinc-500">저장된 실행 결과: {s.status}</p>
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-xs text-zinc-700 dark:text-zinc-300">
                    {s.count}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {connector ? (
                      <div className="flex flex-col items-end gap-1">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => collect(s)}
                            disabled={!s.operational.effectiveActive || busyId === s.id}
                            title={!s.operational.effectiveActive ? s.operational.reason : "실제 커넥터 수집 실행"}
                            className="rounded-md bg-zinc-200 dark:bg-zinc-800 px-2.5 py-1 text-xs text-zinc-800 dark:text-zinc-200 hover:bg-zinc-300 dark:hover:bg-zinc-700 disabled:opacity-40"
                          >
                            {busyId === s.id ? "수집 중…" : "지금 수집"}
                          </button>
                          <button
                            onClick={() => api.updateSource(s.id, { enabled: !s.enabled }).then(onChange)}
                            className={`rounded-md border px-2 py-1 text-[11px] ${s.enabled ? "border-emerald-200 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300" : "border-zinc-300 text-zinc-500 dark:border-zinc-700"}`}
                          >
                            {s.enabled ? "활성" : "비활성"}
                          </button>
                        </div>
                        {result[s.id] && (
                          <span
                            className={`text-[11px] ${result[s.id].ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
                          >
                            {result[s.id].msg.slice(0, 60)}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-zinc-400 dark:text-zinc-600">{s.type === "edm" ? "외부 인제스트 워커" : "업로드 전용"}</span>
                    )}
                  </td>
                </tr>
                {open && (
                  <tr className="border-b border-zinc-200/60 dark:border-zinc-800/60 bg-zinc-100/40 dark:bg-zinc-900/40">
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
                              <dd className="text-zinc-700 dark:text-zinc-300">{SOURCE_TYPE_LABEL[s.type]}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">활성</dt>
                              <dd className="text-zinc-700 dark:text-zinc-300">{s.enabled ? "예" : "아니오"}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">운영 판정</dt>
                              <dd className="text-zinc-700 dark:text-zinc-300">{s.operational.label} — {s.operational.reason}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">설정 확인</dt>
                              <dd className="text-zinc-700 dark:text-zinc-300">{s.operational.configuration}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="w-20 shrink-0 text-zinc-500">생성일</dt>
                              <dd className="font-mono text-zinc-600 dark:text-zinc-400">{s.createdAt}</dd>
                            </div>
                            {configEntries.length === 0 ? (
                              <p className="mt-1 text-zinc-400 dark:text-zinc-600">추가 설정 없음</p>
                            ) : (
                              configEntries.map(([k, v]) => (
                                <div key={k} className="flex gap-2">
                                  <dt className="w-20 shrink-0 text-zinc-500">
                                    {CONFIG_LABEL[k] ?? k}
                                  </dt>
                                  <dd className="break-all text-zinc-700 dark:text-zinc-300">
                                    {k === "url" ? (
                                      <a
                                        href={String(v)}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-sky-600 dark:text-sky-400 hover:underline"
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
                        <div>
                          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-zinc-500">관리 작업</p>
                          <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
                            <p className="text-xs text-zinc-600 dark:text-zinc-400">이 소스에서 누적된 문서 <strong className="text-zinc-900 dark:text-zinc-100">{s.count}건</strong></p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Link href={`/collection/documents?source=${encodeURIComponent(s.id)}`} className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500">
                                수집 문서 보기 ↗
                              </Link>
                              <button onClick={() => api.updateSource(s.id, { enabled: !s.enabled }).then(onChange)} className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900">
                                {s.enabled ? "소스 비활성화" : "소스 활성화"}
                              </button>
                              <button onClick={() => deleteSourceWithConfirm(s, onChange)} className="rounded-md px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40">
                                소스 삭제
                              </button>
                            </div>
                          </div>
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
      <p className="border-t border-zinc-200 px-5 py-2.5 text-[11px] text-zinc-500 dark:border-zinc-800">
        ‘지금 수집’은 설정이 확인된 실제 커넥터에서만 활성화됩니다. EDM은 Windows 인제스트 워커가 담당합니다.
      </p>
    </Card>
  );
}

// ── 업로드 탭 ────────────────────────────────────────────────────────
// 동시 업로드 수. 브라우저 연결 수와 백엔드 쓰기 잠금을 함께 고려한 보수적 값.
const UPLOAD_CONCURRENCY = 4;

function UploadTab({ onChange }: { onChange: () => void }) {
  const [topic, setTopic] = useState("");
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // 여러 파일을 한 건씩 순차 업로드하면 총 시간이 파일 수만큼 늘어난다.
  // 동시 UPLOAD_CONCURRENCY 건씩 올린다(백엔드 업로드는 스트리밍 저장 + 워커 스레드
  // 등록이라 동시 요청에 안전). 개별 실패는 나머지를 막지 않는다.
  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const queue = Array.from(files);
    setUploading(true);
    try {
      let next = 0;
      const worker = async () => {
        while (next < queue.length) {
          const f = queue[next++];
          try {
            await api.upload(f, topic || undefined);
            setRecent((r) => [f.name, ...r].slice(0, 8));
          } catch {
            /* 개별 파일 실패는 건너뛴다 — 목록 새로고침으로 결과 확인 */
          }
        }
      };
      await Promise.all(
        Array.from({ length: Math.min(UPLOAD_CONCURRENCY, queue.length) }, worker),
      );
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
          className="mb-4 w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
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
              ? "border-sky-500 bg-sky-50/30 dark:bg-sky-950/30"
              : "border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600"
          }`}
        >
          <p className="text-sm text-zinc-700 dark:text-zinc-300">
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
              <li key={n + i} className="text-sm text-zinc-700 dark:text-zinc-300">
                ✓ {n}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
