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
    >
      {/* 셸을 뷰포트 높이에 고정(h-screen + overflow-hidden)해야 main 의
          overflow-y-auto 가 바운드된 높이를 갖고 내부 스크롤이 동작한다.
          min-h-screen 으로 두면 main 이 콘텐츠만큼 늘어나 스크롤이 안 됐다. */}
      <body className="flex h-screen overflow-hidden bg-white dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200">
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto px-8 py-8">
          <div className="mx-auto max-w-5xl">{children}</div>
        </main>
      </body>
    </html>
  );
}
