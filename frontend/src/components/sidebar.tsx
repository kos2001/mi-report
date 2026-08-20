"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

type NavItem = {
  href: string;
  label: string;
  icon: string;
  exact?: boolean; // 정확히 일치할 때만 활성(하위 경로에서 부모가 같이 켜지는 것 방지)
  indent?: boolean; // 상위 항목의 하위 페이지로 들여쓰기 표시
};

type NavGroup = {
  label: string | null; // null이면 헤더 없이 단독 표시(대시보드 등)
  // 그룹 헤더 텍스트 색(고정 순서 카테고리 컬러 — bright 모드에서 그룹을 한눈에 구분).
  headerColor?: string;
  items: NavItem[];
};

const navGroups: NavGroup[] = [
  { label: null, items: [{ href: "/", label: "대시보드", icon: "◧" }] },
  {
    label: "데이터",
    headerColor: "text-sky-600 dark:text-sky-500",
    items: [
      { href: "/collection", label: "데이터 수집", icon: "⬇", exact: true },
      // 데이터 수집 하위: 수집 결과 열람 페이지들
      { href: "/collection/results", label: "수집 결과", icon: "∑", exact: true, indent: true },
      { href: "/collection/documents", label: "수집 문서", icon: "🗎", exact: true, indent: true },
    ],
  },
  {
    label: "분석 & 리포트",
    headerColor: "text-emerald-600 dark:text-emerald-500",
    items: [
      { href: "/topics", label: "주제별 History", icon: "≡" },
      { href: "/digest", label: "뉴스 다이제스트", icon: "✉" },
      { href: "/competitors", label: "경쟁사 IR", icon: "▤" },
      { href: "/report", label: "주간 리포트", icon: "▦" },
    ],
  },
  {
    label: "소통",
    headerColor: "text-violet-600 dark:text-violet-500",
    items: [
      { href: "/ask", label: "문서 Q&A", icon: "?" },
      { href: "/voc", label: "VOC", icon: "🗣" },
    ],
  },
  {
    label: "운영",
    headerColor: "text-amber-600 dark:text-amber-500",
    items: [
      { href: "/schedule", label: "스케줄", icon: "⏰" },
    ],
  },
  { label: null, items: [{ href: "/manual", label: "사용 안내", icon: "ⓘ" }] },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col overflow-y-auto border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
      <div className="px-5 py-6">
        <p className="text-lg font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
          MI Report Agent
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          Market Intelligence 자동화
        </p>
      </div>
      <nav className="flex flex-col gap-4 px-3">
        {navGroups.map((group, gi) => (
          <div key={group.label ?? gi} className="flex flex-col gap-1">
            {group.label && (
              <p
                className={`px-3 pb-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                  group.headerColor ?? "text-zinc-400 dark:text-zinc-600"
                }`}
              >
                {group.label}
              </p>
            )}
            {group.items.map((item) => {
              const active = item.exact
                ? pathname === item.href
                : item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg py-2 text-sm transition-colors ${
                    item.indent ? "pl-9 pr-3" : "px-3"
                  } ${
                    active
                      ? "bg-zinc-200 dark:bg-zinc-800 font-medium text-zinc-950 dark:text-zinc-50"
                      : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-900 hover:text-zinc-800 dark:hover:text-zinc-200"
                  }`}
                >
                  <span className="w-4 text-center text-zinc-500">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-3 px-5 py-4">
        <ThemeToggle />
        <p className="rounded-md border border-amber-100/50 dark:border-amber-900/50 bg-amber-50/30 dark:bg-amber-950/30 px-3 py-2 text-[11px] leading-relaxed text-amber-600/80 dark:text-amber-400/80">
          데이터 수집·대시보드 상태는 백엔드 실연동. 주제·다이제스트·경쟁사는 목업.
        </p>
      </div>
    </aside>
  );
}
