"use client";

import { useRouter } from "next/navigation";

/** 관리자 로그인이 필요한 기능 대신 보여주는 안내 (로그인 후 지금 화면으로 돌아온다) */
export default function LoginRequired({ unavailable = false }: { unavailable?: boolean }) {
  const router = useRouter();

  if (unavailable) {
    return (
      <div role="status" className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-800">
        관리자 인증 설정이 끝나지 않아 지금은 설계 기능을 사용할 수 없어요.
      </div>
    );
  }
  return (
    <div role="status" className="rounded-2xl border border-amber-200 bg-white p-6 text-center shadow-sm sm:p-8">
      <p className="text-lg font-semibold">관리자 로그인 후 사용할 수 있어요</p>
      <p className="mt-2 text-sm text-stone-600">지금은 관리자 계정으로만 맞춤 설계를 만들고 내려받을 수 있어요.</p>
      <a
        href="/login"
        onClick={(e) => {
          e.preventDefault();
          router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
        }}
        className="mt-5 inline-block rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600"
      >
        관리자 로그인
      </a>
    </div>
  );
}
