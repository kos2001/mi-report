"use client";

import { useCallback, useEffect, useState } from "react";
import { artifactsApi, type ArtifactFull, type ArtifactMeta } from "@/lib/api";
import { Card } from "@/components/ui";

// 생성물 이력을 관련 page 안에서 조회·삭제할 수 있게 하는 공용 패널.
// kind 로 필터링해 이 페이지가 만든 생성물만 보여준다(다이제스트 페이지엔
// 다이제스트 이력만, 리포트 페이지엔 리포트 이력만 — 별도 "생성물 이력" page 대신).
export function ArtifactHistoryPanel({
  kind,
  refFilter,
  onSelect,
  onDeleted,
  emptyLabel = "아직 생성 이력이 없습니다.",
}: {
  kind: string;
  refFilter?: string;
  onSelect: (artifact: ArtifactFull) => void;
  // 삭제 성공 후 호출된다 — 이 패널 밖에서 같은 생성물을 별도로 캐싱해 보여주는
  // 화면(예: 다이제스트 page 의 "최신 자동 생성" 섹션)이 있다면 갱신할 수 있게.
  onDeleted?: (id: string) => void;
  emptyLabel?: string;
}) {
  const [items, setItems] = useState<ArtifactMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    artifactsApi
      .list({ kind, ref: refFilter, limit: 20 })
      .then((d) => {
        setItems(d.artifacts);
        setError(null);
      })
      .catch(() => setError("이력을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [kind, refFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function open(id: string) {
    try {
      onSelect(await artifactsApi.get(id));
    } catch {
      setError("불러오기 실패");
    }
  }

  async function remove(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!window.confirm("이 생성물을 삭제할까요? 되돌릴 수 없습니다.")) return;
    setBusyId(id);
    try {
      await artifactsApi.remove(id);
      setItems((prev) => prev.filter((a) => a.id !== id));
      onDeleted?.(id);
    } catch {
      setError("삭제 실패");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">생성 이력</h2>
        {items.length > 0 && <span className="text-xs text-zinc-500">{items.length}건</span>}
      </div>
      {error && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>}
      {loading ? (
        <p className="mt-3 text-xs text-zinc-500">불러오는 중…</p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-xs text-zinc-500">{emptyLabel}</p>
      ) : (
        <ul className="mt-2 flex flex-col divide-y divide-zinc-200/60 dark:divide-zinc-800/60">
          {items.map((a) => (
            <li key={a.id} className="flex items-center gap-2 py-2">
              <button
                onClick={() => open(a.id)}
                className="min-w-0 flex-1 truncate text-left text-sm text-zinc-700 dark:text-zinc-300 transition-colors hover:text-zinc-900 dark:hover:text-zinc-100"
              >
                {a.title}
                <span className="ml-2 font-mono text-[11px] text-zinc-500">{a.createdAt}</span>
              </button>
              <button
                onClick={(e) => remove(a.id, e)}
                disabled={busyId === a.id}
                className="shrink-0 rounded-md px-2 py-1 text-xs text-zinc-500 transition-colors hover:bg-red-50/40 dark:hover:bg-red-950/40 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-40"
                aria-label="삭제"
              >
                {busyId === a.id ? "…" : "삭제"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
