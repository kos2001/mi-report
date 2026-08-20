"use client";

import { useEffect, useState } from "react";
import {
  authApi,
  getStoredToken,
  setStoredToken,
  type AuthUser,
  type CurrentUser,
} from "@/lib/api";
import { Card, PageHeader, Tag } from "@/components/ui";

function Account({
  me,
  authEnabled,
  onSaved,
}: {
  me: CurrentUser | null;
  authEnabled: boolean;
  onSaved: () => void;
}) {
  // localStorage 는 서버에 없으므로 SSR 은 빈 문자열 — 하이드레이션 후 클라이언트
  // 값으로 바뀌는 이 한 input 만 suppressHydrationWarning 으로 그 불일치를 허용한다.
  const [tokenInput, setTokenInput] = useState(() => getStoredToken());
  const [saving, setSaving] = useState(false);
  const [oidcConfigured, setOidcConfigured] = useState(false);

  useEffect(() => {
    authApi.oidcStatus().then((d) => setOidcConfigured(d.configured)).catch(() => setOidcConfigured(false));
  }, []);

  async function save() {
    setSaving(true);
    try {
      setStoredToken(tokenInput.trim());
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">내 계정</h2>
      {!authEnabled && (
        <p className="mt-2 rounded-lg border border-amber-200/60 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/40 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          아직 인증이 꺼져 있습니다(사용자가 한 명도 없음) — 모든 요청이 관리자로 취급됩니다.
          아래에서 첫 관리자를 만들면 그때부터 토큰이 필요해집니다.
        </p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <input
          type="text"
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
          placeholder="사용자 토큰 붙여넣기"
          suppressHydrationWarning
          className="w-full max-w-md rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 font-mono text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
        />
        <button
          onClick={save}
          disabled={saving}
          className="shrink-0 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-40"
        >
          저장
        </button>
      </div>
      {oidcConfigured ? (
        <a
          href={authApi.oidcLoginUrl()}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-200 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-700"
        >
          SSO로 로그인
        </a>
      ) : (
        <p className="mt-3 text-[11px] text-zinc-500">
          SSO(OIDC) 미설정 — OIDC_ISSUER/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET 환경변수를 설정하면 여기에 로그인 버튼이 나타납니다.
        </p>
      )}
      <div className="mt-3 flex items-center gap-2 text-sm">
        <span className="text-zinc-500">현재 사용자:</span>
        {me ? (
          <>
            <span className="font-medium text-zinc-900 dark:text-zinc-100">{me.name}</span>
            <Tag>{me.role}</Tag>
          </>
        ) : (
          <span className="text-red-600 dark:text-red-400">토큰이 없거나 유효하지 않습니다.</span>
        )}
      </div>
    </Card>
  );
}

function UserManagement({ isAdmin, onUserChange }: { isAdmin: boolean; onUserChange: () => void }) {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState<"admin" | "viewer">("viewer");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<AuthUser | null>(null);
  const [busyName, setBusyName] = useState<string | null>(null);

  function load() {
    authApi
      .listUsers()
      .then((u) => {
        setUsers(u);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "목록을 불러올 수 없습니다(관리자 권한 필요)."));
  }

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  async function create() {
    if (!name.trim()) return;
    setError(null);
    setCreated(null);
    try {
      const u = await authApi.createUser({ name: name.trim(), role });
      setCreated(u);
      setName("");
      load();
      onUserChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성 실패");
    }
  }

  async function remove(n: string) {
    if (!window.confirm(`${n} 사용자를 삭제할까요?`)) return;
    setBusyName(n);
    try {
      await authApi.deleteUser(n);
      load();
      onUserChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusyName(null);
    }
  }

  async function promote(n: string, role: "admin" | "viewer") {
    setBusyName(n);
    try {
      await authApi.updateRole(n, role);
      load();
      onUserChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "역할 변경 실패");
    } finally {
      setBusyName(null);
    }
  }

  if (!isAdmin) {
    return (
      <Card>
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">사용자 관리</h2>
        <p className="mt-2 text-xs text-zinc-500">관리자만 볼 수 있습니다.</p>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">사용자 관리</h2>

      <div className="mt-3 flex items-center gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="이름"
          className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 outline-none focus:border-sky-500"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as "admin" | "viewer")}
          title="역할"
          className="rounded-lg border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100"
        >
          <option value="viewer">viewer</option>
          <option value="admin">admin</option>
        </select>
        <button
          onClick={create}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500"
        >
          사용자 추가
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>}
      {created && (
        <p className="mt-2 rounded-lg border border-emerald-200/60 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/40 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">
          {created.name} 생성됨 — 토큰은 지금만 표시됩니다, 복사해 전달하세요:{" "}
          <span className="font-mono">{created.token}</span>
        </p>
      )}

      <table className="mt-4 w-full text-left text-xs">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800 text-zinc-500">
            <th className="pb-2 font-medium">이름</th>
            <th className="pb-2 font-medium">역할</th>
            <th className="pb-2 font-medium">토큰</th>
            <th className="pb-2 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.name} className="border-b border-zinc-100 dark:border-zinc-900 last:border-0">
              <td className="py-2 text-zinc-900 dark:text-zinc-100">{u.name}</td>
              <td className="py-2">
                <select
                  value={u.role}
                  onChange={(e) => promote(u.name, e.target.value as "admin" | "viewer")}
                  disabled={busyName === u.name}
                  title="역할 변경"
                  className="rounded-md border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 px-1.5 py-1 text-xs text-zinc-900 dark:text-zinc-100 disabled:opacity-40"
                >
                  <option value="viewer">viewer</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td className="py-2 font-mono text-zinc-500">{u.token.slice(0, 8)}…</td>
              <td className="py-2 text-right">
                <button
                  onClick={() => remove(u.name)}
                  disabled={busyName === u.name}
                  className="rounded-md px-2 py-1 text-zinc-500 transition-colors hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-40"
                >
                  삭제
                </button>
              </td>
            </tr>
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={4} className="py-3 text-zinc-500">아직 사용자가 없습니다.</td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}

export default function SettingsPage() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);

  function refresh() {
    authApi
      .me()
      .then((d) => {
        setMe(d.user);
        setAuthEnabled(d.authEnabled);
      })
      .catch(() => {
        setMe(null);
      });
  }

  useEffect(() => {
    // SSO 콜백이 /settings?token=... 으로 돌려보낸다 — 있으면 저장하고 URL 에서 지운다.
    const url = new URL(window.location.href);
    const oidcToken = url.searchParams.get("token");
    if (oidcToken) {
      setStoredToken(oidcToken);
      url.searchParams.delete("token");
      window.history.replaceState({}, "", url.toString());
    }
    refresh();
  }, []);

  return (
    <>
      <PageHeader
        title="설정"
        description="사용자 토큰·권한(admin/viewer)을 관리합니다"
      />
      <div className="flex flex-col gap-5">
        <Account me={me} authEnabled={authEnabled} onSaved={refresh} />
        <UserManagement isAdmin={me?.role === "admin"} onUserChange={refresh} />
      </div>
    </>
  );
}
