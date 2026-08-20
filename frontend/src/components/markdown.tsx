import type { ReactNode } from "react";

// LLM 답변/리포트가 쓰는 마크다운 부분집합을 안전하게 렌더한다(HTML 주입 없이 React 노드로).
// 지원: # ## ### 제목, - / * / 1. 목록, > 인용(리포트 검토 경고), --- 구분선,
// **굵게**, `코드`, 빈 줄 = 문단 구분.

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      nodes.push(<strong key={key++} className="font-semibold text-zinc-900 dark:text-zinc-100">{tok.slice(2, -2)}</strong>);
    } else {
      nodes.push(
        <code key={key++} className="rounded bg-zinc-200 dark:bg-zinc-800 px-1 py-0.5 text-[0.85em] text-zinc-800 dark:text-zinc-200">
          {tok.slice(1, -1)}
        </code>,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const lines = (text ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    // 제목 (#, ##, ###)
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const cls =
        level === 1
          ? "mt-3 mb-1 text-base font-semibold text-zinc-950 dark:text-zinc-50"
          : level === 2
            ? "mt-3 mb-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100"
            : "mt-2 mb-1 text-sm font-medium text-zinc-800 dark:text-zinc-200";
      blocks.push(<p key={key++} className={cls}>{renderInline(h[2])}</p>);
      i++;
      continue;
    }

    // 구분선 (---)
    if (/^-{3,}\s*$/.test(line)) {
      blocks.push(<hr key={key++} className="my-3 border-zinc-200 dark:border-zinc-800" />);
      i++;
      continue;
    }

    // 인용(>) — 리포트의 "검토 필요" 경고 등
    if (/^>\s?/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        items.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote
          key={key++}
          className="my-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
        >
          {items.map((it, j) => (
            <p key={j}>{renderInline(it)}</p>
          ))}
        </blockquote>,
      );
      continue;
    }

    // 불릿 목록 (-, *)
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={key++} className="my-1 ml-4 list-disc space-y-1">
          {items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}
        </ul>,
      );
      continue;
    }

    // 번호 목록 (1. 2. ...)
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={key++} className="my-1 ml-4 list-decimal space-y-1">
          {items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}
        </ol>,
      );
      continue;
    }

    // 문단 (연속 비목록/비제목 줄)
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !/^-{3,}\s*$/.test(lines[i]) &&
      !/^>\s?/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={key++} className="my-1 leading-relaxed">
        {para.map((p, j) => (
          <span key={j}>
            {renderInline(p)}
            {j < para.length - 1 && <br />}
          </span>
        ))}
      </p>,
    );
  }

  return <div className={className}>{blocks}</div>;
}
