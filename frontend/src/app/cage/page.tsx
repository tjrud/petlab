import type { Metadata } from "next";
import { Suspense } from "react";

import CagePlanner from "@/components/cage/CagePlanner";
import Header from "@/components/Header";

export const metadata: Metadata = {
  title: "가상 케이지",
  description: "케이지 치수를 정하고 은신처·쳇바퀴·모래목욕통 같은 구조물을 놓아 보며 겹침과 끼임 틈을 미리 확인해요.",
};

export default function CagePage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-7xl px-4 py-8">
        <p className="text-xs font-semibold tracking-widest text-amber-700">VIRTUAL CAGE SIMULATION</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">가상 케이지 시뮬레이션</h1>
        <p className="mt-2 max-w-3xl text-stone-600">
          케이지 치수를 정하고 카탈로그의 구조물을 게임처럼 골라 옮기고 돌려 보세요. 겹침·케이지 밖·끼임 틈·출입구 앞 공간을
          놓는 대로 확인해 드려요. 사기 전에, 옮기기 전에 미리 맞춰 보면 몇 번씩 재고 옮기는 수고를 줄일 수 있어요.
        </p>
        <div className="mt-6">
          {/* 화면이 주소의 ?layout= 을 읽으므로(useSearchParams) Suspense 안에서 그린다 */}
          <Suspense fallback={<div className="h-[620px] animate-pulse rounded-2xl bg-amber-50" />}>
            <CagePlanner />
          </Suspense>
        </div>
      </main>
    </>
  );
}
