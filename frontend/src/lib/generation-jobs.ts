// AI 생성(다이제스트/주제 요약/경쟁사 분석/리포트)을 페이지 컴포넌트가 아니라
// 모듈 전역 상태에 묶는다 — 컴포넌트에 묶으면 page 이동으로 언마운트될 때
// (React 상태 갱신은 멈추더라도) 사실 fetch 자체는 계속 흐르지만 진행률·결과를
// 다시 볼 방법이 없었다. 백엔드는 이미 요청 연결과 무관하게 끝까지 실행한다
// (asyncio.create_task) — 프론트도 같은 성질을 갖게 맞춘다. RootLayout 은 페이지
// 이동에도 계속 마운트돼 있으므로, 이 모듈 상태만 컴포넌트 생명주기 밖에 두면
// 다른 페이지에 있다가 돌아와도 진행 중이던 작업을 그대로 이어 볼 수 있다.

import { applyProgress, streamAgent, type ProgressStep } from "./agent-stream";

export type JobKind = "digest" | "topic" | "competitor" | "report";

export interface JobState<T = unknown> {
  status: "idle" | "running" | "done" | "error";
  steps: ProgressStep[];
  result: T | null;
  error: string | null;
  label: string;
}

const IDLE: JobState = { status: "idle", steps: [], result: null, error: null, label: "" };

const jobs = new Map<JobKind, JobState>();
const listeners = new Set<() => void>();

// useSyncExternalStore 는 getSnapshot 이 매번 새 참조를 주면 무한 재렌더로 이어진다
// (React 가 Object.is 로 비교). getJob 은 Map 에 저장된 객체를 그대로 돌려주므로
// 안전하지만, runningJobs() 처럼 매번 새 배열을 만드는 파생값은 emit 시점에 한 번만
// 계산해 캐싱해야 한다.
let runningCache: { kind: JobKind; label: string }[] = [];

function recomputeRunningCache() {
  runningCache = [...jobs.entries()]
    .filter(([, j]) => j.status === "running")
    .map(([kind, j]) => ({ kind, label: j.label }));
}

function emit() {
  recomputeRunningCache();
  listeners.forEach((l) => l());
}

function setJob(kind: JobKind, next: JobState) {
  jobs.set(kind, next);
  emit();
}

export function getJob<T = unknown>(kind: JobKind): JobState<T> {
  return (jobs.get(kind) as JobState<T> | undefined) ?? (IDLE as JobState<T>);
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getServerSnapshot(): JobState {
  return IDLE;
}

// 사이드바 등 페이지 어디서든 "지금 뭔가 돌고 있다" 를 보여주기 위한 전역 조회.
// useSyncExternalStore 의 getSnapshot 으로 쓸 수 있도록 캐싱된 참조를 돌려준다.
export function runningJobs(): { kind: JobKind; label: string }[] {
  return runningCache;
}

const EMPTY_RUNNING: { kind: JobKind; label: string }[] = [];
export function getRunningServerSnapshot(): { kind: JobKind; label: string }[] {
  return EMPTY_RUNNING;
}

// 결과 타입 T 는 호출부가 안다(예: GeneratedDigest) — 여기선 모른 채로 그대로 흘린다.
export async function startJob<T>(
  kind: JobKind, label: string, path: string, body: unknown,
): Promise<void> {
  setJob(kind, { status: "running", steps: [], result: null, error: null, label });
  try {
    const result = await streamAgent<T>(path, body, {
      progress: (p) => {
        const cur = getJob(kind);
        if (cur.status !== "running") return; // 그 사이 clearJob 됐으면 무시
        setJob(kind, { ...cur, steps: applyProgress(cur.steps, p) });
      },
    });
    setJob(kind, { ...getJob(kind), status: "done", result: result as unknown });
  } catch (e) {
    setJob(kind, {
      ...getJob(kind), status: "error",
      error: e instanceof Error ? e.message : "생성 실패",
    });
  }
}

export function clearJob(kind: JobKind): void {
  setJob(kind, IDLE);
}
