// 브라우저별 사용자 ID(localStorage) — 멀티유저 세션 분리의 기본 신원.
// 에이전트 대화(/agent/chat)의 userId 로 쓰인다. 클라이언트 전용.

export function loadUserId(): string {
  const KEY = "mi-user-id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = `user-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}
