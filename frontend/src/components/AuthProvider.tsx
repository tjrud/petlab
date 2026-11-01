"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { AuthStatus, User } from "@/lib/types";

type AuthContextValue = {
  /** null = 아직 확인 중 */
  status: AuthStatus | null;
  user: User | null;
  /** 서버에 로그인 상태를 다시 묻는다 (닉네임 변경 등 후) */
  refresh: () => Promise<void>;
  /** 로그인·회원가입 응답으로 바로 갱신 */
  setStatus: (s: AuthStatus) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** 로그인 상태를 화면 전체에서 한 번만 불러와 공유한다 (헤더·메인·각 페이지). */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.authStatus());
    } catch {
      // 서버에 닿지 못하면 로그인하지 않은 것으로 보여 준다
      setStatus({ auth_enabled: true, authenticated: false, user: null, signup_enabled: false });
    }
  }, []);

  useEffect(() => {
    let alive = true;
    api
      .authStatus()
      .then((s) => alive && setStatus(s))
      .catch(() => alive && setStatus({ auth_enabled: true, authenticated: false, user: null, signup_enabled: false }));
    return () => {
      alive = false;
    };
  }, []);

  const value = useMemo(
    () => ({ status, user: status?.user ?? null, refresh, setStatus }),
    [status, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 는 AuthProvider 안에서만 쓸 수 있어요.");
  return ctx;
}
