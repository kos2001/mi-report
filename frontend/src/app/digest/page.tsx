"use client";

import { useEffect, useState } from "react";
import { digestApi, feedbackApi, type GeneratedDigest } from "@/lib/api";
import { applyProgress, streamAgent, type ProgressStep } from "@/lib/agent-stream";
import { startJob } from "@/lib/generation-jobs";
import { useJob } from "@/lib/use-job";
import { AgentChatCard, AgentProgressView } from "@/components/agent-chat";
import { Card, ImpactBadge, PageHeader, Tag } from "@/components/ui";
import { Markdown } from "@/components/markdown";
import { ArtifactHistoryPanel } from "@/components/artifact-history";

// hermes 에이전트가 초안을 검토한 코멘트(관련 문서 포함). 수치 검증은 생성 시점
// digest_audit 과 중복이라 여기서는 하지 않는다(백엔드가 아예 필드를 안 붙인다).
interface AgentComment {
  week: string;
  answer: string;
  sources?: { title: string; source: string; publishedAt: string | null }[];
}

function digestContext(d: GeneratedDigest): string {
  const items = d.items
    .map((it) => `- [영향도 ${it.impact}] ${it.title}: ${it.summary}`)
    .join("\n");
  return `다음은 뉴스 다이제스트 ${d.week}(${d.period}) 초안이다. 이 초안과 수집 문서·웹 근거를 참고해 질문에 답하라.\n${items}`;
}

// 에이전트에게 "### 제목" 형식의 고정 섹션(항목별 타당성 검토/놓친 리스크·시사점/수정
// 제안)으로 답하도록 프롬프트했다(agentchat.digest_comment_prompt) — 여기서 그 섹션을
// 파싱해 각각 별도 블록으로 보여준다. 옛 형식(섹션 헤더 없는 답변)은 통짜로 폴백 표시.
interface CommentSection {
  title: string;
  body: string;
}

function parseCommentSections(answer: string): CommentSection[] | null {
  const lines = answer.split("\n");
  const sections: CommentSection[] = [];
  let current: CommentSection | null = null;
  for (const line of lines) {
    const m = /^#{2,3}\s+(.+)$/.exec(line.trim());
    if (m) {
      if (current) sections.push({ ...current, body: current.body.trim() });
      current = { title: m[1].trim(), body: "" };
    } else if (current) {
      current.body += (current.body ? "\n" : "") + line;
    }
  }
  if (current) sections.push({ ...current, body: current.body.trim() });
  return sections.length > 0 ? sections : null;
}

const SECTION_ICON: Record<string, string> = {
  "항목별 타당성 검토": "🔍",
  "놓친 리스크·시사점": "⚠️",
  "수정 제안": "💡",
};

function AgentCommentCard({
  comment, source,
}: {
  comment: AgentComment;
  source?: "auto" | "manual";
}) {
  const sections = parseCommentSections(comment.answer);
  return (
    <Card className="mb-4 border-violet-100/40 dark:border-violet-900/40 bg-violet-50/15 dark:bg-violet-950/15">
      <p className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-violet-700 dark:text-violet-300">
        <span>🤖 에이전트 코멘트 — 초안 검토</span>
        {source && (
          <span className="rounded-full bg-violet-100/60 dark:bg-violet-900/40 px-2 py-0.5 text-[10px] normal-case text-violet-600 dark:text-violet-300">
            {source === "auto" ? "생성 시 자동 검토" : "수동 재검토"}
          </span>
        )}
      </p>
      {sections ? (
        <div className="mt-3 flex flex-col gap-2.5">
          {sections.map((s) => (
            <div
              key={s.title}
              className="rounded-lg border border-violet-100/50 dark:border-violet-900/50 bg-white/50 dark:bg-zinc-950/40 px-3 py-2.5"
            >
              <p className="flex items-center gap-1.5 text-xs font-semibold text-zinc-800 dark:text-zinc-200">
                <span>{SECTION_ICON[s.title] ?? "📝"}</span>
                {s.title}
              </p>
              <Markdown
                text={s.body || "해당 없음"}
                className="mt-1.5 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300"
              />
            </div>
          ))}
        </div>
      ) : (
        <Markdown text={comment.answer} className="mt-2 text-sm text-zinc-800 dark:text-zinc-200" />
      )}
      {comment.sources && comment.sources.length > 0 && (
        <div className="mt-3 border-t border-zinc-200 dark:border-zinc-800 pt-2">
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
            관련 수집 문서
          </p>
          <ul className="flex flex-col gap-1">
            {comment.sources.map((s, i) => (
              <li key={i} className="flex items-center gap-2 text-xs text-zinc-700 dark:text-zinc-300">
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
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{item.title}</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {item.source} · {item.publishedAt}
            {sourceUnverified && (
              <span className="ml-1 text-amber-600 dark:text-amber-400">· ⚠ 출처 미검증</span>
            )}
          </p>
        </div>
        <ImpactBadge level={item.impact} />
      </div>

      {(ungrounded.length > 0 || sourceUnverified) && (
        <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
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

      <p className="mt-3 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">{item.summary}</p>

      <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
        <div className="rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 px-3 py-2.5">
          <dt className="font-medium text-zinc-500">S.LSI 연관성</dt>
          <dd className="mt-1 leading-relaxed text-zinc-700 dark:text-zinc-300">{item.slsiRelevance}</dd>
        </div>
        <div className="rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 px-3 py-2.5">
          <dt className="font-medium text-zinc-500">수요 변동</dt>
          <dd className="mt-1 leading-relaxed text-zinc-700 dark:text-zinc-300">{item.demandImpact}</dd>
        </div>
        <div className="rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 px-3 py-2.5">
          <dt className="font-medium text-zinc-500">리스크</dt>
          <dd className="mt-1 leading-relaxed text-zinc-700 dark:text-zinc-300">{item.risk}</dd>
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
  const job = useJob<GeneratedDigest>("digest");
  // 이력 패널에서 과거 생성물을 선택하면 그걸 우선 보여준다 — 없으면 이번 세션의
  // 작업 결과(페이지를 나갔다 와도 유지됨)를 보여준다.
  const [historyPick, setHistoryPick] = useState<GeneratedDigest | null>(null);
  const generated = historyPick ?? job.result;
  const [latest, setLatest] = useState<GeneratedDigest | null>(null);
  const loading = job.status === "running";
  const genSteps = job.steps;
  const error = job.status === "error" ? job.error : null;
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [fb, setFb] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState<AgentComment | null>(null);
  const [commentLoading, setCommentLoading] = useState(false);
  const [commentError, setCommentError] = useState<string | null>(null);
  const [commentSteps, setCommentSteps] = useState<ProgressStep[]>([]);
  const [commentPartial, setCommentPartial] = useState("");
  const [commentFor, setCommentFor] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(true);

  async function handleAgentComment(d: GeneratedDigest) {
    if (commentLoading || d.items.length === 0) return;
    setCommentFor(d.week);
    setCommentLoading(true);
    setCommentError(null);
    setCommentSteps([]);
    setCommentPartial("");
    try {
      // SSE 스트리밍 — 도구 진행사항·답변 델타를 실시간 표시
      const r = await streamAgent(
        "/digest/agent-comment/stream",
        {
          week: d.week,
          period: d.period,
          items: d.items.map((it) => ({
            title: it.title, summary: it.summary, impact: it.impact,
          })),
        },
        {
          progress: (p) => setCommentSteps((prev) => applyProgress(prev, p)),
          delta: (t) => setCommentPartial((prev) => prev + t),
        },
      );
      setComment({ week: d.week, ...r });
    } catch (e) {
      setCommentError(e instanceof Error ? e.message : "에이전트 코멘트 실패");
    } finally {
      setCommentLoading(false);
      setCommentSteps([]);
      setCommentPartial("");
    }
  }

  // 생성 시점에 자동으로 붙은 코멘트(agentComment)를 우선 보여준다 — 사용자가 이
  // 다이제스트에 대해 수동으로 재검토를 요청했다면(comment) 그 결과가 최신이므로 우선.
  // source 는 카드에 "자동/수동" 배지로 표시해 코멘트의 출처를 직관적으로 알 수 있게 한다.
  function displayedComment(
    d: GeneratedDigest,
  ): (AgentComment & { source: "auto" | "manual" }) | null {
    if (comment && comment.week === d.week) return { ...comment, source: "manual" };
    if (d.agentComment) return { week: d.week, ...d.agentComment, source: "auto" };
    return null;
  }

  async function handleFeedback(d: GeneratedDigest, rating: "up" | "down") {
    setFb(rating);
    try {
      await feedbackApi.send({ kind: "digest", ref: d.week, rating });
    } catch {
      /* 피드백 실패는 조용히 무시 */
    }
  }

  async function handleSend(d: GeneratedDigest) {
    setSending(true);
    setSendMsg(null);
    try {
      const r = await digestApi.send({ week: d.week, period: d.period, items: d.items });
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

  // 스케줄 파이프라인(cron)이 마지막으로 저장한 다이제스트를 표시.
  // 수동 실행분도 이제 같은 생성물 저장소(artifacts)를 쓰므로, 생성 이력에서
  // 그 항목을 삭제하면 이 표시도 갱신되어야 한다(refreshLatest 를 이력 패널에 연결).
  function refreshLatest() {
    digestApi
      .latest()
      .then(setLatest)
      .catch(() => {
        /* 백엔드 구버전/미저장 시 무시 */
      });
  }

  useEffect(() => {
    refreshLatest();
  }, []);

  function handleGenerate() {
    setHistoryPick(null);
    // await 하지 않는다 — 컴포넌트 생명주기와 분리된 전역 작업으로 던지고,
    // 페이지를 이동해도 계속 진행되며 useJob 이 어디서든 그 상태를 따라간다.
    void startJob<GeneratedDigest>("digest", "다이제스트 생성 중…", "/digest/generate/stream", {
      period: "최근 수집 문서",
      limit: 20,
    });
  }

  return (
    <>
      <PageHeader
        title="뉴스 다이제스트"
        description="주 2회 반도체·IT 기술 뉴스 종합 — S.LSI 연관성·수요 변동·리스크 영향도 평가 후 메일링"
      />

      {/* 왜 필요한가 · 사용법 (의도 안내) */}
      <Card className="mb-6 border-violet-100/40 dark:border-violet-900/40 bg-violet-50/20 dark:bg-violet-950/20">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-violet-800 dark:text-violet-200">
            ⓘ 왜 필요한가 · 사용법
          </h2>
          <button
            onClick={() => setShowHelp((v) => !v)}
            className="text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            {showHelp ? "접기" : "펼치기"}
          </button>
        </div>
        {showHelp && (
          <div className="mt-3 grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-violet-600 dark:text-violet-400">
                왜 필요한가
              </p>
              <p className="mt-1.5 leading-relaxed text-zinc-700 dark:text-zinc-300">
                매일 쏟아지는 반도체·IT 뉴스를 전부 읽고
                <strong className="text-zinc-900 dark:text-zinc-100"> S.LSI 관점(연관성·수요영향·리스크)</strong>으로
                직접 정리하기는 어렵습니다. 수집된 뉴스를 자동으로 평가·요약하고, hermes 에이전트가
                발송 전 마지막으로 초안을 재검토해 검토 시간을 줄여줍니다.
              </p>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-violet-600 dark:text-violet-400">
                무엇을 산출
              </p>
              <ul className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-700 dark:text-zinc-300">
                <li>· 항목별 S.LSI 연관성 · 수요 변동 · 리스크 평가</li>
                <li>· 영향도(상/중/하) 및 근거 수치 검증</li>
                <li>· hermes 에이전트의 초안 검토(타당성·놓친 리스크·수정 제안)</li>
                <li>· 메일 발송(또는 미리보기)</li>
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-violet-600 dark:text-violet-400">
                사용법
              </p>
              <ol className="mt-1.5 flex flex-col gap-1 leading-relaxed text-zinc-700 dark:text-zinc-300">
                <li>① 데이터 수집에 뉴스 소스를 등록(주기적 자동 수집)</li>
                <li>② ‘AI 초안 생성’ 클릭 — 이번 주차 초안이 생성됨</li>
                <li>③ 에이전트 코멘트·수치 검증을 확인 후 메일 발송</li>
              </ol>
              <p className="mt-2 text-[11px] text-zinc-500">
                문서에 없는 수치는 미근거로 표시됩니다(환각 방지). 단일 출처는 교차검증 필요로 표시됩니다.
              </p>
            </div>
          </div>
        )}
      </Card>

      {/* AI 초안 생성 패널 */}
      <Card className="mb-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">AI 다이제스트 초안 생성</h2>
            <p className="mt-1 text-xs text-zinc-500">
              수집된 문서를 분석해 이번 주차 초안을 생성합니다. (게이트웨이 연동)
            </p>
          </div>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="shrink-0 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-900 dark:text-zinc-100 transition hover:bg-zinc-300 dark:hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "생성 중…" : "AI 초안 생성"}
          </button>
        </div>
        {loading && genSteps.length > 0 && (
          <div className="mt-3">
            <AgentProgressView steps={genSteps} partial="" title="다이제스트 생성 중…" />
          </div>
        )}
        {error && (
          <p className="mt-3 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-3 py-2 text-xs text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
      </Card>

      <div className="mb-8">
        <ArtifactHistoryPanel
          kind="digest"
          onSelect={(a) => setHistoryPick(a.payload as unknown as GeneratedDigest)}
          onDeleted={refreshLatest}
          emptyLabel="아직 생성된 다이제스트가 없습니다."
        />
      </div>

      {/* 다이제스트 자유 질문 — 표시 중인 초안(생성본 우선)을 컨텍스트로 */}
      <div className="mb-8">
        <AgentChatCard
          title="💬 다이제스트에 질문하기"
          description={
            (generated ?? latest)
              ? `${(generated ?? latest)!.week} 초안을 컨텍스트로 에이전트가 답합니다 — 이어지는 질문은 맥락 유지`
              : "에이전트가 수집 문서·웹 근거로 답합니다 — 이어지는 질문은 맥락 유지"
          }
          context={(generated ?? latest) ? digestContext((generated ?? latest)!) : null}
          placeholder="예: 이번 호에서 S.LSI에 가장 중요한 항목은? 최신 뉴스로 보강해줘."
        />
      </div>

      <div className="flex flex-col gap-8">
        {/* 스케줄(cron) 자동 생성 — 마지막 저장본 */}
        {latest && (
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">
                {latest.week}{" "}
                <span className="ml-1 text-sm font-normal text-zinc-600 dark:text-zinc-400">{latest.period}</span>
              </h2>
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-emerald-100/60 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/40 px-3 py-1 text-xs text-emerald-600 dark:text-emerald-400">
                  자동 생성{latest.generatedAt ? ` · ${latest.generatedAt}` : ""} · 문서{" "}
                  {latest.sourceDocCount}건
                </span>
                <button
                  onClick={() => handleAgentComment(latest)}
                  disabled={commentLoading || latest.items.length === 0}
                  title="hermes 에이전트가 코퍼스·웹 근거로 초안을 재검토합니다"
                  className="rounded-lg border border-violet-200/70 dark:border-violet-800/70 bg-violet-50/40 dark:bg-violet-950/40 px-3 py-1 text-xs font-medium text-violet-800 dark:text-violet-200 transition hover:bg-violet-100/40 dark:hover:bg-violet-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {commentLoading
                    ? "검토 중…"
                    : displayedComment(latest)
                      ? "🔄 재검토"
                      : "🤖 에이전트 코멘트"}
                </button>
              </div>
            </div>
            {commentLoading && commentFor === latest.week && (
              <div className="mb-4">
                <AgentProgressView steps={commentSteps} partial={commentPartial} />
              </div>
            )}
            {displayedComment(latest) && (
              <AgentCommentCard
                comment={displayedComment(latest)!}
                source={displayedComment(latest)!.source}
              />
            )}
            {latest.unsupportedClaims && latest.unsupportedClaims.length > 0 && (
              <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                ⚠ 검토 필요 — 다음 서술은 근거가 확인되지 않았습니다: {latest.unsupportedClaims.join(" / ")}
              </p>
            )}
            {latest.items.length === 0 ? (
              <Card>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">생성된 항목이 없습니다.</p>
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
              <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">
                {generated.week}{" "}
                <span className="ml-1 text-sm font-normal text-zinc-600 dark:text-zinc-400">
                  {generated.period}
                </span>
              </h2>
              <div className="flex items-center gap-2">
                <span className="rounded-full border border-sky-100/60 dark:border-sky-900/60 bg-sky-50/40 dark:bg-sky-950/40 px-3 py-1 text-xs text-sky-600 dark:text-sky-400">
                  AI 생성 초안 · 문서 {generated.sourceDocCount}건 기반
                </span>
                <button
                  onClick={() => handleAgentComment(generated)}
                  disabled={commentLoading || generated.items.length === 0}
                  title="hermes 에이전트가 코퍼스·웹 근거로 초안을 재검토합니다"
                  className="rounded-lg border border-violet-200/70 dark:border-violet-800/70 bg-violet-50/40 dark:bg-violet-950/40 px-3 py-1 text-xs font-medium text-violet-800 dark:text-violet-200 transition hover:bg-violet-100/40 dark:hover:bg-violet-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {commentLoading
                    ? "검토 중…"
                    : displayedComment(generated)
                      ? "🔄 재검토"
                      : "🤖 에이전트 코멘트"}
                </button>
                <button
                  onClick={() => handleSend(generated)}
                  disabled={sending || generated.items.length === 0}
                  title="다이제스트를 메일로 발송 (SMTP 미설정 시 미리보기만)"
                  className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-800 px-3 py-1 text-xs font-medium text-zinc-900 dark:text-zinc-100 transition hover:bg-zinc-300 dark:hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sending ? "발송 중…" : "메일 발송"}
                </button>
                {/* 자기 개선 피드백 */}
                <div className="flex items-center gap-1" title="이 생성물 품질 피드백">
                  <button
                    onClick={() => handleFeedback(generated, "up")}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      fb === "up"
                        ? "border-emerald-300 dark:border-emerald-700 bg-emerald-50/50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300"
                        : "border-zinc-300 dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-zinc-700"
                    }`}
                  >
                    👍
                  </button>
                  <button
                    onClick={() => handleFeedback(generated, "down")}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      fb === "down"
                        ? "border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-950/50 text-red-700 dark:text-red-300"
                        : "border-zinc-300 dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-zinc-700"
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
                    ? "border-emerald-100/60 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400"
                    : "border-amber-100/60 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300"
                }`}
              >
                {sendMsg.text}
              </p>
            )}
            {commentError && (
              <p className="mb-3 rounded-lg border border-red-100/60 dark:border-red-900/60 bg-red-50/40 dark:bg-red-950/40 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                {commentError}
              </p>
            )}
            {commentLoading && commentFor === generated.week && (
              <div className="mb-4">
                <AgentProgressView steps={commentSteps} partial={commentPartial} />
              </div>
            )}
            {displayedComment(generated) && (
              <AgentCommentCard
                comment={displayedComment(generated)!}
                source={displayedComment(generated)!.source}
              />
            )}
            {generated.unsupportedClaims && generated.unsupportedClaims.length > 0 && (
              <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                ⚠ 검토 필요 — 다음 서술은 근거가 확인되지 않았습니다: {generated.unsupportedClaims.join(" / ")}
              </p>
            )}
            {generated.items.length === 0 ? (
              <Card>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">생성된 항목이 없습니다.</p>
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
      </div>
    </>
  );
}
