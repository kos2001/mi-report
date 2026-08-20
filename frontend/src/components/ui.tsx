import type { ImpactLevel } from "@/lib/data";
import type { UnsupportedClaim } from "@/lib/api";

const PAGE_META: Record<string, { group: string; icon: string; tone: string; iconTone: string }> = {
  "대시보드": { group: "OVERVIEW", icon: "◧", tone: "text-zinc-500", iconTone: "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" },
  "데이터 수집": { group: "DATA PIPELINE", icon: "↓", tone: "text-sky-600", iconTone: "bg-sky-600 text-white" },
  "수집 결과": { group: "DATA PIPELINE", icon: "∑", tone: "text-sky-600", iconTone: "bg-sky-600 text-white" },
  "수집 문서": { group: "DATA PIPELINE", icon: "▤", tone: "text-sky-600", iconTone: "bg-sky-600 text-white" },
  "주제별 History": { group: "ANALYSIS", icon: "≡", tone: "text-emerald-600", iconTone: "bg-emerald-600 text-white" },
  "뉴스 다이제스트": { group: "ANALYSIS", icon: "✉", tone: "text-emerald-600", iconTone: "bg-emerald-600 text-white" },
  "경쟁사 IR 트래킹": { group: "ANALYSIS", icon: "▥", tone: "text-emerald-600", iconTone: "bg-emerald-600 text-white" },
  "주간 MI 리포트": { group: "ANALYSIS", icon: "▦", tone: "text-emerald-600", iconTone: "bg-emerald-600 text-white" },
  "문서 Q&A": { group: "COMMUNICATION", icon: "?", tone: "text-violet-600", iconTone: "bg-violet-600 text-white" },
  "VOC": { group: "COMMUNICATION", icon: "●", tone: "text-violet-600", iconTone: "bg-violet-600 text-white" },
  "스케줄": { group: "OPERATIONS", icon: "◷", tone: "text-amber-600", iconTone: "bg-amber-500 text-white" },
  "품질": { group: "OPERATIONS", icon: "✓", tone: "text-amber-600", iconTone: "bg-amber-500 text-white" },
  "설정": { group: "OPERATIONS", icon: "⚙", tone: "text-amber-600", iconTone: "bg-amber-500 text-white" },
  "사용 안내": { group: "GUIDE", icon: "ⓘ", tone: "text-cyan-600", iconTone: "bg-cyan-600 text-white" },
};

export function PageHeader({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const meta = PAGE_META[title] ?? PAGE_META["대시보드"];
  return (
    <header className="mb-7 flex items-start gap-3 border-b border-zinc-200 pb-5 dark:border-zinc-800">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-base font-bold shadow-sm ${meta.iconTone}`} aria-hidden>
        {meta.icon}
      </span>
      <div className="min-w-0">
        <p className={`text-[10px] font-bold uppercase tracking-[0.16em] ${meta.tone}`}>{meta.group}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">{title}</h1>
        <p className="mt-1.5 max-w-4xl text-sm leading-6 text-zinc-600 dark:text-zinc-400">{description}</p>
      </div>
    </header>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-zinc-200 bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.03)] dark:border-zinc-800 dark:bg-zinc-950 ${className}`}
    >
      {children}
    </div>
  );
}

// high/medium/low 를 신호등 톤(빨강/호박/초록)으로 또렷하게 구분한다 — low 를
// 중립 회색으로 두면 상/중만 눈에 띄고 하는 "색이 없다"로 읽혀 구분이 흐려졌다.
const impactStyle: Record<ImpactLevel, string> = {
  high: "bg-red-100/80 dark:bg-red-950/60 text-red-700 dark:text-red-400 border-red-300/70 dark:border-red-900/60",
  medium: "bg-amber-100/80 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border-amber-300/70 dark:border-amber-900/60",
  low: "bg-emerald-100/80 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border-emerald-300/70 dark:border-emerald-900/60",
};

const impactLabel: Record<ImpactLevel, string> = {
  high: "영향도 상",
  medium: "영향도 중",
  low: "영향도 하",
};

export function ImpactBadge({ level }: { level: ImpactLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${impactStyle[level]}`}
    >
      {impactLabel[level]}
    </span>
  );
}

const tagStyles = [
  "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
];

export function Tag({ children }: { children: React.ReactNode }) {
  const label = typeof children === "string" ? children : "tag";
  const index = [...label].reduce((sum, char) => sum + char.charCodeAt(0), 0) % tagStyles.length;
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${tagStyles[index]}`}>
      {children}
    </span>
  );
}

// 독립 검증 agent(audit_overview)가 잡아낸 "근거 없는 서술" 목록을 이유(why)와
// 함께 보여준다. 예전엔 claim 텍스트만 나열해 "왜 근거가 없는지"가 안 보였다 —
// 자기개선 loop이 실제로 이유·근거를 보고 판단할 수 있어야 하므로 각 항목에
// why 를 함께 표시한다(why 가 비어 있으면 claim 만).
export function UnsupportedClaimsNotice({ claims }: { claims: UnsupportedClaim[] | undefined }) {
  if (!claims || claims.length === 0) return null;
  return (
    <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
      <p className="font-medium">⚠ 검토 필요 — 다음 서술은 근거가 확인되지 않았습니다</p>
      <ul className="mt-1.5 flex flex-col gap-1 pl-4">
        {claims.map((c, i) => (
          <li key={i} className="list-disc leading-relaxed">
            <span>{c.claim}</span>
            {c.why && <span className="text-amber-600/80 dark:text-amber-400/80"> — {c.why}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Delta({ value, suffix = "%" }: { value: number; suffix?: string }) {
  const color =
    value > 0 ? "text-emerald-600 dark:text-emerald-400" : value < 0 ? "text-red-600 dark:text-red-400" : "text-zinc-600 dark:text-zinc-400";
  const sign = value > 0 ? "+" : "";
  return (
    <span className={`font-mono text-xs ${color}`}>
      {sign}
      {value.toFixed(1)}
      {suffix}
    </span>
  );
}
