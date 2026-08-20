import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

// 저장된 테마(localStorage) 또는 시스템 설정을 하이드레이션 전에 적용해
// 깜빡임(FOUC: 다크 유저에게 밝은 화면이 잠깐 보였다가 바뀌는 현상)을 막는다.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
    var collapsed = localStorage.getItem("sidebar-collapsed") === "true";
    document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
  } catch (e) {}
})();
`;

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MI Report Agent",
  description:
    "시장 센싱·뉴스 다이제스트·경쟁사 IR 분석을 자동화하는 Market Intelligence 에이전트",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      // next/font 가 생성하는 이 클래스 해시가 Turbopack dev 에서 서버/클라이언트
      // 패스 사이에 흔들리는 경우가 있다(폰트 로더 자체의 dev-mode 재계산 —
      // 앱 로직과 무관). Next 공식 문서가 바로 이 케이스(next/font + html 태그)를
      // suppressHydrationWarning 의 대표 예시로 든다: 시각적 영향 없는 CSS 클래스
      // 해시 하나만 다를 뿐이라 진짜 불일치를 숨기는 게 아니다.
      suppressHydrationWarning
    >
      {/* 셸을 뷰포트 높이에 고정(h-screen + overflow-hidden)해야 main 의
          overflow-y-auto 가 바운드된 높이를 갖고 내부 스크롤이 동작한다.
          min-h-screen 으로 두면 main 이 콘텐츠만큼 늘어나 스크롤이 안 됐다. */}
      <body className="flex h-screen flex-col overflow-hidden bg-white text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 md:flex-row">
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        <Sidebar />
        {/* 사이드바 폭에 맞춰 화면 크기 전체를 활용 — 초광폭 모니터에서는 가독성을
            위해 max-w 로 상한만 둔다(고정 1024px 캡을 없애 화면 크기에 맞게 늘어남). */}
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 md:px-8 md:py-8">
          <div className="mx-auto w-full max-w-[1920px]">{children}</div>
        </main>
      </body>
    </html>
  );
}
