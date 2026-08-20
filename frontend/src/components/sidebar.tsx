"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { getRunningServerSnapshot, runningJobs, subscribe } from "@/lib/generation-jobs";

// layout.tsx 의 인라인 스크립트가 하이드레이션 전에 이미 .sidebar-collapsed 클래스를
// html 에 정한다(테마와 같은 패턴) — 접힘 상태를 새로고침 후에도 깜빡임 없이 유지.
function subscribeCollapsed(callback: () => void) {
  window.addEventListener("sidebar-change", callback);
  return () => window.removeEventListener("sidebar-change", callback);
}
function getCollapsedSnapshot() {
  return document.documentElement.classList.contains("sidebar-collapsed");
}
function getCollapsedServerSnapshot() {
  return false;
}

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
  activeClass?: string;
  items: NavItem[];
};

const navGroups: NavGroup[] = [
  { label: null, items: [{ href: "/", label: "대시보드", icon: "◧" }] },
  {
    label: "데이터",
    headerColor: "text-sky-600 dark:text-sky-500",
    activeClass: "bg-sky-50 text-sky-900 ring-1 ring-sky-200 dark:bg-sky-950/50 dark:text-sky-100 dark:ring-sky-900",
    items: [
      { href: "/collection", label: "데이터 수집", icon: "⬇", exact: true },
      // 데이터 수집 하위: 수집 결과 열람 페이지들
      { href: "/collection/documents", label: "수집 문서", icon: "🗎", exact: true, indent: true },
      { href: "/collection/results", label: "수집 결과", icon: "∑", exact: true, indent: true },
    ],
  },
  {
    label: "분석 & 리포트",
    headerColor: "text-emerald-600 dark:text-emerald-500",
    activeClass: "bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-100 dark:ring-emerald-900",
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
    activeClass: "bg-violet-50 text-violet-900 ring-1 ring-violet-200 dark:bg-violet-950/50 dark:text-violet-100 dark:ring-violet-900",
    items: [
      { href: "/ask", label: "문서 Q&A", icon: "?" },
      { href: "/voc", label: "VOC", icon: "🗣" },
    ],
  },
  {
    label: "운영",
    headerColor: "text-amber-600 dark:text-amber-500",
    activeClass: "bg-amber-50 text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-100 dark:ring-amber-900",
    items: [
      { href: "/schedule", label: "스케줄", icon: "⏰" },
      { href: "/quality", label: "품질", icon: "✓" },
      { href: "/settings", label: "설정", icon: "⚙" },
    ],
  },
  { label: null, items: [{ href: "/manual", label: "사용 안내", icon: "ⓘ" }] },
];

const JOB_HREF: Record<string, string> = {
  digest: "/digest",
  topic: "/topics",
  competitor: "/competitors",
  report: "/report",
};

// page 를 이동해도 계속 도는 AI 생성 작업을 어디서나 보이게 — generation-jobs 는
// 컴포넌트 밖 전역 상태라, 지금 보고 있는 page 와 무관하게 실행 중인 작업이 있을 수 있다.
function RunningJobsIndicator() {
  const running = useSyncExternalStore(subscribe, runningJobs, getRunningServerSnapshot);
  if (running.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-sky-100/60 dark:border-sky-900/60 bg-sky-50/40 dark:bg-sky-950/40 px-3 py-2">
      {running.map((j) => (
        <Link
          key={j.kind}
          href={JOB_HREF[j.kind] ?? "/"}
          className="flex items-center gap-1.5 text-[11px] text-sky-700 dark:text-sky-300 hover:underline"
        >
          <span className="inline-block h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-sky-500" />
          {j.label}
        </Link>
      ))}
    </div>
  );
}

function toggleSidebarCollapsed() {
  const next = !document.documentElement.classList.contains("sidebar-collapsed");
  document.documentElement.classList.toggle("sidebar-collapsed", next);
  localStorage.setItem("sidebar-collapsed", String(next));
  window.dispatchEvent(new Event("sidebar-change"));
}

export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useSyncExternalStore(subscribeCollapsed, getCollapsedSnapshot, getCollapsedServerSnapshot);
  return (
    <aside
      className={`flex w-full shrink-0 flex-col overflow-hidden border-b border-zinc-200 bg-white transition-[width] duration-150 dark:border-zinc-800 dark:bg-zinc-950 md:h-full md:overflow-y-auto md:border-b-0 md:border-r ${
        collapsed ? "md:w-16" : "md:w-60"
      }`}
    >
      <div className="flex items-center justify-between px-4 py-3 md:px-5 md:py-6">
        <div className={`min-w-0 ${collapsed ? "md:hidden" : ""}`}>
          <p className="truncate text-lg font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
            MI Report Agent
          </p>
          <p className="hidden text-[10px] text-zinc-500 md:mt-1 md:block md:text-xs">
            Market Intelligence 자동화
          </p>
        </div>
        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
        </div>
        {/* 접기/펼치기 — 데스크톱 전용(모바일은 상단 가로 스크롤 내비를 그대로 사용) */}
        <button
          onClick={toggleSidebarCollapsed}
          aria-label={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
          title={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
          className="hidden shrink-0 items-center justify-center rounded-md border border-zinc-200 p-1.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-800 dark:border-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-200 md:flex"
        >
          <span aria-hidden className={`inline-block text-xs transition-transform ${collapsed ? "rotate-180" : ""}`}>
            ◀
          </span>
        </button>
      </div>
      <nav className="flex gap-2 overflow-x-auto px-3 pb-3 md:flex-col md:gap-4 md:overflow-visible md:pb-0">
        {navGroups.map((group, gi) => (
          <div key={group.label ?? gi} className="flex shrink-0 gap-1 md:flex-col">
            {group.label && (
              <p
                className={`hidden px-3 pb-0.5 text-[10px] font-semibold uppercase tracking-wider md:block ${
                  collapsed ? "md:hidden" : ""
                } ${group.headerColor ?? "text-zinc-400 dark:text-zinc-600"}`}
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
                  title={collapsed ? item.label : undefined}
                  className={`flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-xs transition-colors md:gap-3 md:text-sm ${
                    collapsed ? "md:justify-center md:px-0" : item.indent ? "md:pl-9 md:pr-3" : "md:px-3"
                  } ${
                    active
                      ? `${group.activeClass ?? "bg-zinc-200 text-zinc-950 dark:bg-zinc-800 dark:text-zinc-50"} font-medium`
                      : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-900 hover:text-zinc-800 dark:hover:text-zinc-200"
                  }`}
                >
                  <span className="w-4 text-center text-zinc-500">{item.icon}</span>
                  <span className={collapsed ? "md:hidden" : ""}>{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className={`mt-auto hidden flex-col gap-3 px-5 py-4 md:flex ${collapsed ? "md:items-center md:px-2" : ""}`}>
        <div className={collapsed ? "md:hidden" : ""}>
          <RunningJobsIndicator />
        </div>
        <ThemeToggle compact={collapsed} />
        <p className={`rounded-md border border-emerald-100/70 bg-emerald-50/50 px-3 py-2 text-[11px] leading-relaxed text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300 ${collapsed ? "md:hidden" : ""}`}>
          실데이터 연동 · 상태 배지는 설정·실행·수집 결과를 함께 판정합니다.
        </p>
      </div>
    </aside>
  );
}
