"use client";

import { useEffect, useState } from "react";
import { digestApi, feedbackApi, type GeneratedDigest } from "@/lib/api";
import { digests } from "@/lib/data";
import { Card, ImpactBadge, PageHeader, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";

// hermes 에이전트가 초안을 검토한 코멘트(수치 검증·관련 문서 포함)
interface AgentComment {
  issueNo: number;
  answer: string;
  numbersGrounded?: boolean;
  ungroundedNumbers?: string[];
  sources?: { title: string; source: string; publishedAt: string | null }[];
}

function AgentCommentCard({ comment }: { comment: AgentComment }) {
  return (
    <Card className="mb-4 border-violet-900/40 bg-violet-950/15">
      <p className="text-[11px] font-medium uppercase tracking-wide text-violet-300">
        🤖 에이전트 코멘트 — 초안 검토
      </p>
      {comment.numbersGrounded === false &&
        comment.ungroundedNumbers &&
        comment.ungroundedNumbers.length > 0 && (
          <p className="mt-2 rounded-lg border border-amber-900/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
            ⚠ 다음 수치는 수집 문서에서 확인되지 않았습니다(웹 출처이거나 오류일 수 있음 — 검토 필요):{" "}
            <span className="font-mono">{comment.ungroundedNumbers.join(", ")}</span>
          </p>
        )}
      <Markdown text={comment.answer} className="mt-2 text-sm text-zinc-200" />
      {comment.sources && comment.sources.length > 0 && (
        <div className="mt-3 border-t border-zinc-800 pt-2">
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
            관련 수집 문서
          </p>
          <ul className="flex flex-col gap-1">
            {comment.sources.map((s, i) => (
              <li key={i} className="flex items-center gap-2 text-xs text-zinc-300">
                <Tag>{s.source}</Tag>
                <span>{s.title}</span>
                {s.publishedAt && <span className="text-zinc-500">· {s.publishedAt}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

// 다음 호수: 목업 최신호 + 1 (백엔드가 호수를 관리하기 전 임시 규칙)
const NEXT_ISSUE_NO = Math.max(...digests.map((d) => d.issueNo)) + 1;

type DigestItemLike = {
  id: string;
  title: string;
  source: string;
  publishedAt: string;
  summary: string;
  slsiRelevance: string;
  demandImpact: string;
  risk: string;
  impact: "high" | "medium" | "low";
  tags: string[];
  numbersGrounded?: boolean;
  ungroundedNumbers?: string[];
  sourceVerified?: boolean;
};

function DigestItemCard({ item }: { item: DigestItemLike }) {
  const ungrounded = item.ungroundedNumbers ?? [];
  const sourceUnverified = item.sourceVerified === false;
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">{item.title}</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {item.source} · {item.publishedAt}
            {sourceUnverified && (
              <span className="ml-1 text-amber-400">· ⚠ 출처 미검증</span>
            )}
          </p>
        </div>
        <ImpactBadge level={item.impact} />
      </div>

      {(ungrounded.length > 0 || sourceUnverified) && (
        <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          {ungrounded.length > 0 && (
            <>
              ⚠ 환각 주의 — 제공 문서에서 확인되지 않은 수치:{" "}
              <span className="font-mono">{ungrounded.join(", ")}</span>
            </>
          )}
          {sourceUnverified && (
            <span className="block">⚠ 출처를 입력 문서에서 추적할 수 없습니다 — 귀속 확인 필요</span>
          )}
        </p>
      )}

      <p className="mt-3 text-sm leading-relaxed text-zinc-300">{item.summary}</p>

      <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
        <div className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
          <dt className="font-medium text-zinc-500">S.LSI 연관성</dt>
          <dd className="mt-1 leading-relaxed text-zinc-300">{item.slsiRelevance}</dd>
        </div>
        <div className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
          <dt className="font-medium text-zinc-500">수요 변동</dt>
          <dd className="mt-1 leading-relaxed text-zinc-300">{item.demandImpact}</dd>
        </div>
        <div className="rounded-lg bg-zinc-800/50 px-3 py-2.5">
          <dt className="font-medium text-zinc-500">리스크</dt>
          <dd className="mt-1 leading-relaxed text-zinc-300">{item.risk}</dd>
        </div>
      </dl>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.tags.map((t) => (
          <Tag key={t}>{t}</Tag>
        ))}
      </div>
    </Card>
  );
}

export default function DigestPage() {
  const [generated, setGenerated] = useState<GeneratedDigest | null>(null);
  const [latest, setLatest] = useState<GeneratedDigest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [fb, setFb] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState<AgentComment | null>(null);
  const [commentLoading, setCommentLoading] = useState(false);
  const [commentError, setCommentError] = useState<string | null>(null);

  async function handleAgentComment(d: GeneratedDigest) {
    if (commentLoading || d.items.length === 0) return;
    setCommentLoading(true);
    setCommentError(null);
    try {
      const r = await digestApi.agentComment({
        issueNo: d.issueNo,
        period: d.period,
        items: d.items.map((it) => ({
          title: it.title, summary: it.summary, impact: it.impact,
        })),
      });
      setComment({ issueNo: d.issueNo, ...r });
    } catch (e) {
      setCommentError(e instanceof Error ? e.message : "에이전트 코멘트 실패");
    } finally {
      setCommentLoading(false);
    }
  }

  async function handleFeedback(d: GeneratedDigest, rating: "up" | "down") {
    setFb(rating);
    try {
      await feedbackApi.send({ kind: "digest", ref: String(d.issueNo), rating });
    } catch {
      /* 피드백 실패는 조용히 무시 */
    }
  }

  async function handleSend(d: GeneratedDigest) {
    setSending(true);
    setSendMsg(null);
    try {
      const r = await digestApi.send({ issueNo: d.issueNo, period: d.period, items: d.items });
      if (r.status === "sent") {
        setSendMsg({ ok: true, text: `발송 완료 → ${(r.to ?? []).join(", ")}` });
      } else if (r.status === "not_sent") {
        setSendMsg({ ok: false, text: `발송 안 됨 (${r.reason}) — 미리보기는 생성됨` });
      } else {
        setSendMsg({ ok: false, text: `발송 실패: ${r.detail ?? "오류"}` });
      }
    } catch (e) {
      setSendMsg({ ok: false, text: e instanceof Error ? e.message : "발송 요청 실패" });
    } finally {
      setSending(false);
    }
  }

  // 스케줄 파이프라인(cron)이 마지막으로 저장한 다이제스트를 표시
  useEffect(() => {
    let alive = true;
    digestApi
      .latest()
      .then((d) => {
        if (alive) setLatest(d);
      })
      .catch(() => {
        /* 백엔드 구버전/미저장 시 무시 */
      });
    return () => {
      alive = false;
    };
  }, []);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const result = await digestApi.generate({
        issueNo: NEXT_ISSUE_NO,
        period: "최근 수집 문서",
        limit: 20,
      });
      setGenerated(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "다이제스트 생성 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="뉴스 다이제스트"
        description="주 2회 반도체·IT 기술 뉴스 종합 — S.LSI 연관성·수요 변동·리스크 영향도 평가 후 메일링"
      />

      {/* AI 초안 생성 패널 */}
      <Card className="mb-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">AI 다이제스트 초안 생성</h2>
            <p className="mt-1 text-xs text-zinc-500">
              수집된 문서를 분석해 제{NEXT_ISSUE_NO}호 초안을 생성합니다. (게이트웨이 연동)
            </p>
          </div>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="shrink-0 rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "생성 중…" : "AI 초안 생성"}
          </button>
        </div>
        {error && (
          <p className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
      </Card>

      <div className="flex flex-col gap-8">
        {/* 스케줄(cron) 자동 생성 — 마지막 저장본 */}
        {latest && (
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-50">
                제{latest.issueNo}호{" "}
                <span className="ml-1 text-sm font-normal text-zinc-400">{latest.period}</span>
              </h2>
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-emerald-900/60 bg-emerald-950/40 px-3 py-1 text-xs text-emerald-400">
                  자동 생성{latest.generatedAt ? ` · ${latest.generatedAt}` : ""} · 문서{" "}
                  {latest.sourceDocCount}건
                </span>
                <button
                  onClick={() => handleAgentComment(latest)}
                  disabled={commentLoading || latest.items.length === 0}
                  title="hermes 에이전트가 코퍼스·웹 근거로 초안을 검토합니다"
                  className="rounded-lg border border-violet-800/70 bg-violet-950/40 px-3 py-1 text-xs font-medium text-violet-200 transition hover:bg-violet-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {commentLoading ? "검토 중…" : "🤖 에이전트 코멘트"}
                </button>
              </div>
            </div>
            {comment && comment.issueNo === latest.issueNo && (
              <AgentCommentCard comment={comment} />
            )}
            {latest.items.length === 0 ? (
              <Card>
                <p className="text-sm text-zinc-400">생성된 항목이 없습니다.</p>
              </Card>
            ) : (
              <div className="flex flex-col gap-4">
                {latest.items.map((item) => (
                  <DigestItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </section>
        )}

        {/* AI 생성 초안 (있을 때 최상단) */}
        {generated && (
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-50">
                제{generated.issueNo}호{" "}
                <span className="ml-1 text-sm font-normal text-zinc-400">
                  {generated.period}
                </span>
              </h2>
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-sky-900/60 bg-sky-950/40 px-3 py-1 text-xs text-sky-400">
                  AI 생성 초안 · 문서 {generated.sourceDocCount}건 기반
                </span>
                <button
                  onClick={() => handleAgentComment(generated)}
                  disabled={commentLoading || generated.items.length === 0}
                  title="hermes 에이전트가 코퍼스·웹 근거로 초안을 검토합니다"
                  className="rounded-lg border border-violet-800/70 bg-violet-950/40 px-3 py-1 text-xs font-medium text-violet-200 transition hover:bg-violet-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {commentLoading ? "검토 중…" : "🤖 에이전트 코멘트"}
                </button>
                <button
                  onClick={() => handleSend(generated)}
                  disabled={sending || generated.items.length === 0}
                  title="다이제스트를 메일로 발송 (SMTP 미설정 시 미리보기만)"
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs font-medium text-zinc-100 transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sending ? "발송 중…" : "메일 발송"}
                </button>
                {/* 자기 개선 피드백 */}
                <div className="flex items-center gap-1" title="이 생성물 품질 피드백">
                  <button
                    onClick={() => handleFeedback(generated, "up")}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      fb === "up"
                        ? "border-emerald-700 bg-emerald-950/50 text-emerald-300"
                        : "border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                    }`}
                  >
                    👍
                  </button>
                  <button
                    onClick={() => handleFeedback(generated, "down")}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      fb === "down"
                        ? "border-red-800 bg-red-950/50 text-red-300"
                        : "border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                    }`}
                  >
                    👎
                  </button>
                </div>
              </div>
            </div>
            {fb && (
              <p className="mb-3 text-[11px] text-zinc-500">피드백 감사합니다 — 품질 개선에 반영됩니다.</p>
            )}
            {sendMsg && (
              <p
                className={`mb-3 rounded-lg border px-3 py-2 text-xs ${
                  sendMsg.ok
                    ? "border-emerald-900/60 bg-emerald-950/40 text-emerald-400"
                    : "border-amber-900/60 bg-amber-950/40 text-amber-300"
                }`}
              >
                {sendMsg.text}
              </p>
            )}
            {commentError && (
              <p className="mb-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-400">
                {commentError}
              </p>
            )}
            {comment && comment.issueNo === generated.issueNo && (
              <AgentCommentCard comment={comment} />
            )}
            {generated.items.length === 0 ? (
              <Card>
                <p className="text-sm text-zinc-400">생성된 항목이 없습니다.</p>
              </Card>
            ) : (
              <div className="flex flex-col gap-4">
                {generated.items.map((item) => (
                  <DigestItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </section>
        )}

        {/* 과거 다이제스트 (예시) */}
        {digests.map((digest) => (
          <section key={digest.id}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-50">
                제{digest.issueNo}호{" "}
                <span className="ml-1 text-sm font-normal text-zinc-400">
                  {digest.period}
                </span>
              </h2>
              {digest.mailedAt ? (
                <span className="rounded-full border border-emerald-900/60 bg-emerald-950/40 px-3 py-1 text-xs text-emerald-400">
                  발송 완료 · {digest.mailedAt}
                </span>
              ) : (
                <span className="rounded-full border border-amber-900/60 bg-amber-950/40 px-3 py-1 text-xs text-amber-400">
                  초안 — 발송 전 검토 필요
                </span>
              )}
            </div>

            <div className="flex flex-col gap-4">
              {digest.items.map((item) => (
                <DigestItemCard key={item.id} item={item} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
