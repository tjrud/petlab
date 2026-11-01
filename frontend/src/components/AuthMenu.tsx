"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api";

/** 헤더 오른쪽: 로그인·회원가입 또는 닉네임·로그아웃 */
export default function AuthMenu() {
  const { status, user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!status) return <span className="h-8 w-24" aria-hidden />; // 자리만 잡아 화면이 흔들리지 않게
  if (!status.auth_enabled) return null;
  if (!user) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <Link href="/login" className="rounded-lg px-3 py-1.5 hover:bg-stone-100">
          로그인
        </Link>
        {status.signup_enabled && (
          <Link href="/signup" className="rounded-lg bg-amber-500 px-3 py-1.5 font-medium text-white hover:bg-amber-600">
            회원가입
          </Link>
        )}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <Link href="/me" className="max-w-[9rem] truncate text-stone-600 hover:text-stone-900" title="내 정보">
        {user.role === "admin" && <span className="mr-1 rounded bg-stone-800 px-1.5 py-0.5 text-xs text-white">관리자</span>}
        {user.nickname}
      </Link>
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
          window.location.replace("/");
        }}
        className="rounded-lg border border-stone-300 px-3 py-1.5 hover:bg-stone-50 disabled:opacity-50"
      >
        로그아웃
      </button>
    </div>
  );
}
