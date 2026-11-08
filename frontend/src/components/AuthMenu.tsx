"use client";

import { Link } from "@/i18n/client";
import { useState } from "react";

import { useAuth, useLogout } from "@/components/AuthProvider";

// 좁은 화면(360px)에서도 한 줄에 들어가도록 글자가 줄바꿈되거나 눌리지 않게 한다
const pill = "shrink-0 whitespace-nowrap rounded-lg px-3 py-1.5";

/** 헤더 오른쪽: 로그인·회원가입 또는 닉네임·로그아웃 (서버에 닿지 못하면 다시 시도) */
export default function AuthMenu() {
  const { status, user, unreachable, refresh } = useAuth();
  const { logout, busy, error } = useLogout();
  const [retrying, setRetrying] = useState(false);

  if (!status) {
    if (!unreachable) return <span className="h-8 w-24" aria-hidden />; // 자리만 잡아 화면이 흔들리지 않게
    // 로그인 상태를 한 번도 확인하지 못했다: 로그아웃·가입 마감으로 보이지 않게 연결 문제라고 알린다
    return (
      <div className="flex min-w-0 items-center gap-2 text-sm">
        <span role="status" className="min-w-0 text-xs leading-tight text-red-700">
          서버에 연결하지 못했어요
        </span>
        <button
          type="button"
          disabled={retrying}
          onClick={async () => {
            setRetrying(true);
            await refresh();
            setRetrying(false);
          }}
          className={`${pill} border border-stone-300 hover:bg-stone-50 disabled:opacity-50`}
        >
          {retrying ? "확인 중…" : "다시 시도"}
        </button>
      </div>
    );
  }
  if (!status.auth_enabled) return null;
  if (!user) {
    return (
      <div className="flex min-w-0 items-center gap-2 text-sm">
        <Link href="/login" className={`${pill} hover:bg-stone-100`}>
          로그인
        </Link>
        {status.signup_enabled && (
          <Link href="/signup" className={`${pill} bg-amber-500 font-medium text-white hover:bg-amber-600`}>
            회원가입
          </Link>
        )}
      </div>
    );
  }
  return (
    <div className="relative flex min-w-0 items-center gap-2 text-sm">
      <Link
        href="/me"
        className="min-w-0 max-w-[7.5rem] truncate text-stone-600 hover:text-stone-900 sm:max-w-[9rem]"
        title="내 정보"
      >
        {/* 좁은 화면에서는 이름표가 닉네임 자리를 다 차지해 "N…" 만 보이므로 빼고, 닉네임을 보인다 (내 정보에 관리자 표시가 있다) */}
        {user.role === "admin" && (
          <span className="mr-1 hidden rounded bg-stone-800 px-1.5 py-0.5 text-xs text-white sm:inline">관리자</span>
        )}
        {user.nickname}
      </Link>
      <button
        type="button"
        disabled={busy}
        onClick={logout}
        className={`${pill} border border-stone-300 hover:bg-stone-50 disabled:opacity-50`}
      >
        로그아웃
      </button>
      {/* 오류는 줄 밖(헤더 아래)에 띄운다: 헤더 줄이 넓어져 좁은 화면에서 가로로 넘치지 않게 */}
      {error && (
        <p
          role="alert"
          className="absolute right-0 top-full mt-2 w-max max-w-[16rem] rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 shadow-sm"
        >
          {error}
        </p>
      )}
    </div>
  );
}
