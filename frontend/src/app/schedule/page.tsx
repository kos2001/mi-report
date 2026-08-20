"use client";

import { useEffect, useState } from "react";
import { scheduleApi, type ScheduleView } from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";

const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"];

export default function SchedulePage() {
  const [view, setView] = useState<ScheduleView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // 편집 상태
  const [enabled, setEnabled] = useState(false);
  const [frequency, setFrequency] = useState<"daily" | "weekly">("daily");
  const [hour, setHour] = useState(7);
  const [minute, setMinute] = useState(0);
  const [weekday, setWeekday] = useState(0);
  const [digestLimit, setDigestLimit] = useState(20);
  const [retryEnabled, setRetryEnabled] = useState(false);
  const [retryMinutes, setRetryMinutes] = useState(10);

  function apply(v: ScheduleView) {
    setView(v);
    const s = v.schedule;
    setEnabled(s.enabled);
    setFrequency(s.frequency);
    setHour(s.hour);
    setMinute(s.minute);
    setWeekday(s.weekday);
    setDigestLimit(s.digestLimit);
    setRetryEnabled(s.retryEnabled);
    setRetryMinutes(s.retryMinutes);
  }

  useEffect(() => {
    scheduleApi.get().then(apply).catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"));
  }, []);

  async function save() {
    setSaving(true);
    setError(null);
    setMsg(null);
    try {
      apply(
        await scheduleApi.put({
          enabled, frequency, hour, minute, weekday, digestLimit, retryEnabled, retryMinutes,
        }),
      );
      setMsg("저장됨");
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function runNow() {
    setRunning(true);
    setError(null);
    setMsg(null);
    try {
      const r = await scheduleApi.runNow();
      setMsg(`실행 완료 — 수집 ${r.ingested ?? 0}건`);
      scheduleApi.get().then(apply).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "실행 실패 (LLM 키/게이트웨이 확인)");
    } finally {
      setRunning(false);
    }
  }

  const timeStr = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

  return (
    <>
      <PageHeader
        title="스케줄"
        description="수집 → 다이제스트 생성 파이프라인의 자동 실행 주기를 시각적으로 설정"
      />

      {error && (
        <div className="mb-5 rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">{error}</div>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
        {/* 설정 폼 */}
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">자동 실행 설정</h2>
            <button
              onClick={() => setEnabled((v) => !v)}
              aria-pressed={enabled}
              className={`rounded-md border px-3 py-1 text-xs transition-colors ${
                enabled
                  ? "border-emerald-800/60 bg-emerald-950/60 text-emerald-400"
                  : "border-zinc-700 bg-zinc-800 text-zinc-500"
              }`}
            >
              {enabled ? "● 활성" : "○ 비활성"}
            </button>
          </div>

          <div className="mt-4 flex flex-col gap-4">
            <div className="flex items-center gap-2">
              <span className="w-16 text-xs text-zinc-500">주기</span>
              <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/40 p-1 text-sm">
                {(["daily", "weekly"] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFrequency(f)}
                    className={`rounded-md px-3 py-1 transition-colors ${
                      frequency === f ? "bg-zinc-800 font-medium text-zinc-50" : "text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {f === "daily" ? "매일" : "매주"}
                  </button>
                ))}
              </div>
            </div>

            {frequency === "weekly" && (
              <div className="flex items-center gap-2">
                <span className="w-16 text-xs text-zinc-500">요일</span>
                <div className="flex flex-wrap gap-1">
                  {WEEKDAYS.map((d, i) => (
                    <button
                      key={d}
                      onClick={() => setWeekday(i)}
                      className={`h-8 w-8 rounded-md border text-xs transition-colors ${
                        weekday === i
                          ? "border-sky-700 bg-sky-950/50 text-sky-300"
                          : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-2">
              <span className="w-16 text-xs text-zinc-500">시각</span>
              <input
                type="time"
                value={timeStr}
                onChange={(e) => {
                  const [h, m] = e.target.value.split(":").map(Number);
                  if (!Number.isNaN(h)) setHour(h);
                  if (!Number.isNaN(m)) setMinute(m);
                }}
                className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="w-16 text-xs text-zinc-500">문서 수</span>
              <input
                type="number"
                min={1}
                max={100}
                value={digestLimit}
                onChange={(e) => setDigestLimit(Number(e.target.value) || 20)}
                className="w-24 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
              />
              <span className="text-xs text-zinc-500">다이제스트 입력 문서 최대</span>
            </div>

            <div className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-xs text-zinc-500">자동 재시도</span>
              <button
                onClick={() => setRetryEnabled((v) => !v)}
                aria-pressed={retryEnabled}
                className={`rounded-md border px-3 py-1 text-xs transition-colors ${
                  retryEnabled
                    ? "border-emerald-800/60 bg-emerald-950/60 text-emerald-400"
                    : "border-zinc-700 bg-zinc-800 text-zinc-500"
                }`}
              >
                {retryEnabled ? "● 켜짐" : "○ 꺼짐"}
              </button>
              {retryEnabled && (
                <>
                  <input
                    type="number"
                    min={1}
                    max={120}
                    value={retryMinutes}
                    onChange={(e) => setRetryMinutes(Number(e.target.value) || 10)}
                    className="w-20 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
                  />
                  <span className="text-xs text-zinc-500">분 후 재시도 (실패 시 최대 3회)</span>
                </>
              )}
            </div>

            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={save}
                disabled={saving}
                className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
              >
                {saving ? "저장 중…" : "저장"}
              </button>
              <button
                onClick={runNow}
                disabled={running}
                className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition-colors hover:bg-zinc-700 disabled:opacity-40"
              >
                {running ? "실행 중…" : "지금 실행"}
              </button>
              {msg && <span className="text-xs text-emerald-400">{msg}</span>}
            </div>
          </div>
        </Card>

        {/* 요약 / crontab */}
        <Card>
          <h2 className="text-sm font-semibold text-zinc-100">현황</h2>
          {view && (
            <dl className="mt-3 flex flex-col gap-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-zinc-500">설정</dt>
                <dd className="text-zinc-200">{view.describe}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-zinc-500">다음 실행</dt>
                <dd className="font-mono text-zinc-300">{view.nextRun ?? "—(비활성)"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-zinc-500">마지막 실행</dt>
                <dd className="flex items-center gap-1.5 font-mono text-zinc-400">
                  {view.schedule.lastRunAt ?? "—"}
                  {view.lastStatus === "success" && <span className="text-emerald-400">✓</span>}
                  {view.lastStatus === "failure" && <span className="text-red-400">⚠️ 실패</span>}
                </dd>
              </div>
              {view.lastStatus === "failure" && view.lastError && (
                <div className="rounded-md border border-red-900/60 bg-red-950/30 px-2.5 py-1.5 text-xs text-red-300">
                  {view.lastError}
                </div>
              )}
              <div className="flex justify-between gap-2">
                <dt className="text-zinc-500">앱 내 스케줄러</dt>
                <dd className={view.inAppScheduler ? "text-emerald-400" : "text-zinc-400"}>
                  {view.inAppScheduler ? "동작 중" : "꺼짐 (MI_SCHEDULER=1 필요)"}
                </dd>
              </div>
            </dl>
          )}
          <div className="mt-4 border-t border-zinc-800 pt-3">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-zinc-500">crontab (외부 cron 용)</p>
            <code className="block break-all rounded-lg bg-zinc-900 px-3 py-2 font-mono text-xs text-sky-300">
              {view ? `${view.crontab}  cd backend && .venv/bin/python -m tools.run_pipeline` : "—"}
            </code>
            <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
              앱 내 스케줄러가 꺼져 있으면, 위 라인을 crontab/launchd 에 등록해 외부에서 실행하세요.
            </p>
          </div>
        </Card>
      </div>

      <Card className="mt-5">
        <h2 className="text-sm font-semibold text-zinc-100">실행 이력</h2>
        {view && view.runs.length === 0 && (
          <p className="mt-3 text-xs text-zinc-500">아직 실행 이력이 없습니다.</p>
        )}
        {view && view.runs.length > 0 && (
          <table className="mt-3 w-full text-left text-xs">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-500">
                <th className="pb-2 font-medium">시각</th>
                <th className="pb-2 font-medium">트리거</th>
                <th className="pb-2 font-medium">상태</th>
                <th className="pb-2 font-medium">결과</th>
              </tr>
            </thead>
            <tbody>
              {view.runs.map((r, i) => (
                <tr key={i} className="border-b border-zinc-900 last:border-0">
                  <td className="py-2 font-mono text-zinc-400">{r.ranAt}</td>
                  <td className="py-2 text-zinc-400">{r.trigger === "auto" ? "자동" : "수동"}</td>
                  <td className="py-2">
                    {r.status === "success" ? (
                      <span className="text-emerald-400">✓ 성공</span>
                    ) : (
                      <span className="text-red-400">⚠️ 실패</span>
                    )}
                  </td>
                  <td className="py-2 text-zinc-400">
                    {r.status === "success" ? `수집 ${r.ingested ?? 0}건` : (r.error ?? "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
