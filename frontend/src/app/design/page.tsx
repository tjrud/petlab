import type { Metadata } from "next";
import { Suspense } from "react";

import Header from "@/components/Header";
import NewDesignWizard, { WizardSkeleton } from "@/components/NewDesignWizard";

export const metadata: Metadata = { title: "설계하기" };

export default function DesignPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <h1 className="text-3xl font-bold leading-tight sm:text-4xl">
          우리 아이 케이지에 꼭 맞는{" "}
          <br className="hidden sm:block" />
          구조물을 설계해 드려요
        </h1>
        <p className="mt-3 text-stone-600">
          케이지 크기와 원하는 구성을 알려 주시면 AI가 은신처 같은 구조물을 맞춤 설계합니다. 결과는 3D로
          확인하고, 3D 프린팅 파일(STL·3MF)로 내려받을 수 있어요.
        </p>
        <div className="mt-8">
          {/* 마법사가 주소의 ?pet= 을 읽으므로(useSearchParams) Suspense 안에서 그린다 */}
          <Suspense fallback={<WizardSkeleton />}>
            <NewDesignWizard />
          </Suspense>
        </div>
      </main>
    </>
  );
}
