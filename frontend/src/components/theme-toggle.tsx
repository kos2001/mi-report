"use client";

import { useSyncExternalStore } from "react";

// layout.tsx 의 인라인 스크립트가 하이드레이션 전에 이미 .dark 클래스를 정했다.
// useSyncExternalStore 로 그 DOM 상태를 읽으면(getServerSnapshot 로 SSR 과 값을
// 맞춰) 하이드레이션 불일치 경고 없이 외부 상태(classList)를 구독할 수 있다.
function subscribe(callback: () => void) {
  window.addEventListener("theme-change", callback);
  return () => window.removeEventListener("theme-change", callback);
}
function getSnapshot() {
  return document.documentElement.classList.contains("dark");
}
function getServerSnapshot() {
  return false; // 서버 렌더 기본값 — 하이드레이션 직후 실제 값으로 즉시 갱신됨
}

export function ThemeToggle() {
  const dark = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
    // subscribe 가 실제 이벤트를 쏘지 않으므로, DOM 변경 후 강제로 재구독 트리거.
    window.dispatchEvent(new Event("theme-change"));
  }

  return (
    <button
      onClick={toggle}
      aria-pressed={dark}
      aria-label="다크/라이트 모드 전환"
      className="flex items-center gap-1.5 rounded-md border border-zinc-300 bg-zinc-100 px-2.5 py-1.5 text-xs text-zinc-600 transition-colors hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
    >
      {dark ? "🌙 다크" : "☀️ 라이트"}
    </button>
  );
}
