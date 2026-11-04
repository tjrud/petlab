"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { withNext } from "@/lib/safeNext";

/** 로그인이 필요한 기능 대신 보여주는 안내 (로그인 후 지금 화면으로 돌아온다) */
export default function LoginRequired({
  unavailable = false,
  message = "로그인 후 사용할 수 있어요",
  description,
}: {
  unavailable?: boolean;
  message?: string;
  description?: string;
}) {
  const { status } = useAuth();
  const text =
    description ??
    (status?.email_verification
      ? "회원가입은 무료예요. 아이디·닉네임·이메일만 있으면 시작할 수 있어요."
      : "회원가입은 무료예요. 아이디와 닉네임만 있으면 바로 시작할 수 있어요.");
  const [next, setNext] = useState("/");
  // 렌더 중 window 를 읽지 않도록(서버 렌더와 일치) 마운트 후에 현재 경로를 읽는다
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setNext(window.location.pathname + window.location.search), []);

  if (unavailable) {
    return (
      <div role="status" className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-800">
        로그인 설정이 끝나지 않아 지금은 이 기능을 사용할 수 없어요.
      </div>
    );
  }
  return (
    <div role="status" className="rounded-2xl border border-amber-200 bg-white p-6 text-center shadow-sm sm:p-8">
      <p className="text-lg font-semibold">{message}</p>
      <p className="mt-2 text-sm text-stone-600">{text}</p>
      <div className="mt-5 flex justify-center gap-2">
        <Link href={withNext("/login", next)} className="rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600">
          로그인
        </Link>
        {status?.signup_enabled !== false && (
          <Link href={withNext("/signup", next)} className="rounded-xl border border-stone-300 bg-white px-6 py-3 font-semibold hover:bg-stone-50">
            회원가입
          </Link>
        )}
      </div>
    </div>
  );
}
