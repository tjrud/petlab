"use client";

import { useAuth } from "@/components/AuthProvider";
import MyPets from "@/components/home/MyPets";
import RecentDesigns from "@/components/home/RecentDesigns";
import SignupBanner from "@/components/home/SignupBanner";

/** 로그인한 회원에게는 최근 설계·반려동물, 아니면 가입 안내 */
export default function MemberArea() {
  const { status, user } = useAuth();

  if (!status) {
    // 로그인 상태를 확인하는 동안 자리만 잡아 둔다 (화면이 흔들리지 않게)
    return (
      <div role="status" className="mt-12">
        <span className="sr-only">내 정보를 확인하는 중이에요</span>
        <div aria-hidden className="grid gap-4 lg:grid-cols-2">
          <div className="h-56 animate-pulse rounded-2xl bg-stone-100" />
          <div className="h-56 animate-pulse rounded-2xl bg-stone-100" />
        </div>
      </div>
    );
  }

  if (!user) return <SignupBanner signupEnabled={status.signup_enabled} />;

  return (
    <section aria-labelledby="my-area-title" className="mt-12">
      <h2 id="my-area-title" className="text-xl font-bold sm:text-2xl">
        내 공간
      </h2>
      <p className="mt-1 break-words text-sm text-stone-600">
        {user.nickname}님, 반가워요. 이어서 설계하거나 등록한 아이로 새 설계를 시작해 보세요.
      </p>
      {/* 다른 계정으로 바뀌면 이전 계정의 목록을 버리고 새로 불러온다 */}
      <div key={user.id} className="mt-5 grid gap-4 lg:grid-cols-2">
        <RecentDesigns />
        <MyPets />
      </div>
    </section>
  );
}
