"use client";

import { useSyncExternalStore } from "react";
import { getJob, getServerSnapshot, subscribe, type JobKind, type JobState } from "./generation-jobs";

// generation-jobs 스토어(모듈 전역 — 컴포넌트 생명주기 밖)를 구독하는 훅.
// page 를 이동했다 돌아와도 useSyncExternalStore 가 현재 스토어 상태를 즉시 읽어오므로
// 진행 중이던 작업의 진행률·완료 결과가 그대로 이어져 보인다.
export function useJob<T = unknown>(kind: JobKind): JobState<T> {
  return useSyncExternalStore(subscribe, () => getJob<T>(kind), getServerSnapshot as () => JobState<T>);
}
