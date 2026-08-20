import type { Source } from "@/lib/api";

const STYLE: Record<Source["operational"]["state"], string> = {
  healthy: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  manual: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/50 dark:text-sky-300",
  waiting: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/50 dark:text-blue-300",
  stale: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  warning: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/50 dark:text-orange-300",
  setup: "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700 dark:border-fuchsia-800 dark:bg-fuchsia-950/50 dark:text-fuchsia-300",
  error: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-300",
  disabled: "border-zinc-300 bg-zinc-100 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400",
};

const DOT: Record<Source["operational"]["state"], string> = {
  healthy: "bg-emerald-500",
  manual: "bg-sky-500",
  waiting: "bg-blue-500",
  stale: "bg-amber-500",
  warning: "bg-orange-500",
  setup: "bg-fuchsia-500",
  error: "bg-red-500",
  disabled: "bg-zinc-400",
};

export function SourceOperationalStatus({ source, showReason = false }: {
  source: Source;
  showReason?: boolean;
}) {
  const status = source.operational;
  return (
    <div className="min-w-0">
      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${STYLE[status.state]}`}>
        <span className={`h-2 w-2 rounded-full ${DOT[status.state]}`} />
        {status.label}
      </span>
      {showReason && (
        <p className="mt-1 max-w-sm text-[11px] leading-4 text-zinc-500" title={status.configuration}>
          {status.reason}
        </p>
      )}
    </div>
  );
}
