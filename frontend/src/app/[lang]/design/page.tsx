import type { Metadata } from "next";
import { Suspense } from "react";

import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import NewDesignWizard, { WizardSkeleton } from "@/components/NewDesignWizard";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("설계하기") };
}

export default async function DesignPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <h1 className="text-2xl font-bold sm:text-3xl">{t("맞춤 설계하기")}</h1>
        <p className="mt-2 text-stone-600">
          {t(
            "사육 환경과 원하는 구조물을 적으면 설계와 함께 안전·출력 기준 검사 결과가 나와요. 결과는 3D로 보고 STL·3MF 파일로 내려받을 수 있어요.",
          )}
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
