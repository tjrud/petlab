"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";
import LoginRequired from "@/components/LoginRequired";

/**
 * 설계를 불러오지 못했을 때. 볼 수 없는 설계는 서버가 404 로 답하므로,
 * 로그인하지 않은 상태라면 "없음" 대신 로그인 안내를 보여 준다 (내 설계일 수 있으니).
 */
export default function DesignLoadError({ status: httpStatus, message }: { status: number; message: string }) {
  const { status, user } = useAuth();
  const notFound = httpStatus === 404;

  if (notFound && status === null) {
    return <div className="py-20 text-center text-stone-500">설계를 불러오는 중…</div>;
  }
  if (notFound && !user) {
    return (
      <div className="mx-auto max-w-xl">
        <LoginRequired
          message="로그인하면 내 설계를 볼 수 있어요"
          description="만든 설계는 로그인한 뒤에 다시 열 수 있어요. 회원가입은 무료예요."
        />
      </div>
    );
  }
  return (
    <div role="alert" className="mx-auto max-w-xl rounded-2xl border border-red-200 bg-red-50 p-6 text-red-800">
      <p className="text-lg font-semibold">{notFound ? "설계를 찾을 수 없어요" : "설계를 불러오지 못했어요"}</p>
      <p className="mt-2 text-sm">
        {notFound
          ? "주소가 잘못되었거나 삭제된 설계예요. 다른 회원의 설계는 커뮤니티에 공유된 경우에만 볼 수 있어요."
          : message}
      </p>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm font-medium">
        <Link href="/designs" className="underline underline-offset-2">
          내 설계 목록
        </Link>
        <Link href="/" className="underline underline-offset-2">
          처음으로
        </Link>
      </div>
    </div>
  );
}
