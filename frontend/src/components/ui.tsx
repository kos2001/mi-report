import type { ImpactLevel } from "@/lib/data";

export function PageHeader({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <header className="mb-8">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
        {title}
      </h1>
      <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
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
      className={`rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-100/60 dark:bg-zinc-900/60 p-5 ${className}`}
    >
      {children}
    </div>
  );
}

const impactStyle: Record<ImpactLevel, string> = {
  high: "bg-red-50/60 dark:bg-red-950/60 text-red-600 dark:text-red-400 border-red-100/60 dark:border-red-900/60",
  medium: "bg-amber-50/60 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border-amber-100/60 dark:border-amber-900/60",
  low: "bg-zinc-200/80 dark:bg-zinc-800/80 text-zinc-600 dark:text-zinc-400 border-zinc-300/60 dark:border-zinc-700/60",
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

export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-zinc-200 dark:bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-400">
      {children}
    </span>
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
