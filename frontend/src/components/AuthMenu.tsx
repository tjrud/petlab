"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { AuthStatus } from "@/lib/types";

/** 헤더의 관리자 로그인 상태 표시 (인증이 꺼져 있으면 아무것도 표시하지 않음) */
export default function AuthMenu() {
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus | null>(null);

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
      <button
        type="button"
        onClick={async () => {
          await api.logout().catch(() => {});
          setStatus({ auth_enabled: true, authenticated: false, username: null });
          router.push("/login");
        }}
        className="rounded-lg border border-stone-300 px-3 py-1.5 hover:bg-stone-50"
      >
        로그아웃
      </button>
    </div>
  );
}
