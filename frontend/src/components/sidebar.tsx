"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/", label: "대시보드", icon: "◧" },
  { href: "/collection", label: "데이터 수집", icon: "⬇" },
  { href: "/topics", label: "주제별 History", icon: "≡" },
  { href: "/digest", label: "뉴스 다이제스트", icon: "✉" },
  { href: "/competitors", label: "경쟁사 IR", icon: "▤" },
  { href: "/ask", label: "문서 Q&A", icon: "?" },
  { href: "/report", label: "주간 리포트", icon: "▦" },
  { href: "/manual", label: "사용 안내", icon: "ⓘ" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col overflow-y-auto border-r border-zinc-800 bg-zinc-950">
      <div className="px-5 py-6">
        <p className="text-lg font-semibold tracking-tight text-zinc-50">
          MI Report Agent
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          Market Intelligence 자동화
        </p>
      </div>
      <nav className="flex flex-col gap-1 px-3">
        {nav.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-zinc-800 font-medium text-zinc-50"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span className="w-4 text-center text-zinc-500">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto px-5 py-4">
        <p className="rounded-md border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-[11px] leading-relaxed text-amber-400/80">
          데이터 수집·대시보드 상태는 백엔드 실연동. 주제·다이제스트·경쟁사는 목업.
        </p>
      </div>
    </aside>
  );
}
