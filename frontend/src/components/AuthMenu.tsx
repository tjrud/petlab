"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { AuthStatus } from "@/lib/types";

/** 헤더의 관리자 로그인 상태 표시 (인증이 꺼져 있으면 아무것도 표시하지 않음) */
export default function AuthMenu() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .authStatus()
      .then((s) => {
        if (alive) setStatus(s);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  if (!status || !status.auth_enabled) return null;
  if (!status.authenticated) {
    return (
      <Link href="/login" className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm hover:bg-stone-50">
        관리자 로그인
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-stone-500">관리자 {status.username}</span>
      {error && (
        <span role="alert" className="text-red-700">
          {error}
        </span>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
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
          // 전체 새로고침으로 이동: 숨김 상태로 남아 있던 이전 화면(설계 내용)과 클라이언트 캐시를 버린다
          window.location.replace("/login");
        }}
        className="rounded-lg border border-stone-300 px-3 py-1.5 hover:bg-stone-50 disabled:opacity-50"
      >
        로그아웃
      </button>
    </div>
  );
}
