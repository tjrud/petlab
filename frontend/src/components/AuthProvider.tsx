"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { api, AUTH_ERROR_EVENT } from "@/lib/api";
import type { AuthStatus, User } from "@/lib/types";

type AuthContextValue = {
  /** 마지막으로 확인한 로그인 상태. null = 아직 한 번도 확인하지 못함 (확인 중이거나 서버에 닿지 못함) */
  status: AuthStatus | null;
  user: User | null;
  /** 마지막 확인이 실패했다 (서버에 닿지 못했거나 서버 오류). 이때도 이전에 확인한 status 는 그대로 둔다 */
  unreachable: boolean;
  /** 이메일 인증을 마치지 않은 회원 (서버가 인증을 요구할 때만). 설계·글쓰기·댓글·제작 신청이 막혀 있다 */
  emailUnverified: boolean;
  /** 서버에 로그인 상태를 다시 묻는다. 서버가 답하면 true */
  refresh: () => Promise<boolean>;
  /** 로그인·회원가입 응답으로 바로 갱신 */
  setStatus: (s: AuthStatus) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** 확인에 실패하면 이 간격(ms)으로 다시 묻는다. 그 뒤로는 창으로 돌아오거나 네트워크가 다시 연결될 때만 묻는다 */
const RETRY_DELAYS = [2_000, 5_000, 15_000, 30_000, 60_000];

/**
 * 로그인 상태를 화면 전체에서 공유한다 (헤더·메인·각 페이지).
 * 처음 한 번 묻고, 회원 API 가 로그인 문제로 실패하면(AUTH_ERROR_EVENT) 다시 묻는다.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{ status: AuthStatus | null; failures: number }>({ status: null, failures: 0 });
  const inflight = useRef<Promise<boolean> | null>(null);
  // setStatus 로 바로 갱신한 뒤에 늦게 도착한 이전 확인 결과로 되돌리지 않게 한다
  const generation = useRef(0);

  const refresh = useCallback((): Promise<boolean> => {
    // 이미 묻는 중이면 그 결과를 함께 기다린다 (여러 요청이 한꺼번에 401 을 받아도 한 번만 묻는다)
    if (inflight.current) return inflight.current;
    const gen = generation.current;
    const p = api
      .authStatus()
      .then(
        (s) => {
          if (gen === generation.current) {
            setState((prev) => ({
              // 내용이 같으면 이전 객체를 그대로 둔다 (화면 전체를 다시 그리지 않게)
              status: prev.status && JSON.stringify(prev.status) === JSON.stringify(s) ? prev.status : s,
              failures: 0,
            }));
          }
          return true;
        },
        () => {
          // 서버에 닿지 못했거나 서버 오류: 로그아웃·가입 마감으로 보지 않고, 마지막으로 확인한 상태를 둔 채 다시 묻는다
          if (gen === generation.current) setState((prev) => ({ ...prev, failures: prev.failures + 1 }));
          return false;
        },
      )
      .finally(() => {
        inflight.current = null;
      });
    inflight.current = p;
    return p;
  }, []);

  const setStatus = useCallback((s: AuthStatus) => {
    generation.current += 1;
    setState({ status: s, failures: 0 });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 회원 API 가 로그인 문제로 실패했다: 저장해 둔 로그인 상태가 오래됐을 수 있으므로 다시 묻는다
  useEffect(() => {
    const onAuthError = () => void refresh();
    window.addEventListener(AUTH_ERROR_EVENT, onAuthError);
    return () => window.removeEventListener(AUTH_ERROR_EVENT, onAuthError);
  }, [refresh]);

  // 확인에 실패했으면 잠시 뒤, 창으로 돌아올 때, 네트워크가 다시 연결될 때 다시 묻는다
  const failures = state.failures;
  useEffect(() => {
    if (failures === 0) return;
    const retry = () => void refresh();
    const delay = RETRY_DELAYS[failures - 1];
    const timer = delay === undefined ? undefined : window.setTimeout(retry, delay);
    window.addEventListener("focus", retry);
    window.addEventListener("online", retry);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("focus", retry);
      window.removeEventListener("online", retry);
    };
  }, [failures, refresh]);

  const user = state.status?.user ?? null;
  const emailUnverified = !!state.status?.email_verification && !!user && user.role !== "admin" && !user.email_verified;

  // 인증 링크는 보통 다른 탭(메일)에서 연다: 이 탭으로 돌아오면 인증을 마쳤는지 다시 묻는다
  useEffect(() => {
    if (!emailUnverified) return;
    const recheck = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    window.addEventListener("focus", recheck);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      window.removeEventListener("focus", recheck);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, [emailUnverified, refresh]);

  const value = useMemo(
    () => ({
      status: state.status,
      user,
      unreachable: state.failures > 0,
      emailUnverified,
      refresh,
      setStatus,
    }),
    [state, user, emailUnverified, refresh, setStatus],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 는 AuthProvider 안에서만 쓸 수 있어요.");
  return ctx;
}

export type RecheckResult = "checking" | "ok" | "failed";

/**
 * 이 화면이 보일 때마다(숨김 상태로 남아 있다가 다시 보일 때도) 로그인 상태를 서버에 다시 묻는다.
 * 로그인·회원가입 화면이 오래된 로그인 상태로 "이미 로그인했어요"를 띄우지 않게 할 때 쓴다.
 * "checking" 동안 useAuth() 의 값은 오래됐을 수 있고, "failed" 는 서버에 닿지 못한 경우.
 */
export function useAuthRecheck(): RecheckResult {
  const { refresh, unreachable } = useAuth();
  const [result, setResult] = useState<RecheckResult>("checking");

  useEffect(() => {
    let alive = true;
    void refresh().then((ok) => {
      if (alive) setResult(ok ? "ok" : "failed");
    });
    return () => {
      alive = false;
    };
  }, [refresh]);

  // 화면이 숨겨질 때 되돌린다 (다시 보일 때 이전 확인 결과를 쓰지 않게)
  useLayoutEffect(
    () => () => {
      setResult("checking");
    },
    [],
  );

  // 실패한 뒤 다른 곳(헤더의 다시 시도·자동 재시도)에서 확인에 성공했으면 그 결과를 쓴다
  return result === "failed" && !unreachable ? "ok" : result;
}

/** 로그아웃. 성공하면 전체 새로고침으로 메인 화면에 간다 (숨김 상태로 남아 있던 이전 화면과 클라이언트 캐시를 버린다) */
export function useLogout() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const logout = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api.logout();
    } catch {
      // 서버가 쿠키를 지우지 못했으면 로그인 상태를 그대로 보여 준다
      setError("로그아웃하지 못했어요. 다시 시도해 주세요.");
      setBusy(false);
      return;
    }
    window.location.replace("/");
  }, []);

  return { logout, busy, error };
}
