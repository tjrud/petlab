import type { Metadata } from "next";
import { Suspense } from "react";

import PartRequestsAdmin, { PartRequestsPlaceholder } from "@/components/admin/PartRequestsAdmin";
import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("부품 요청"), robots: { index: false } };
}

/** 관리자 화면: 해석기가 카탈로그에 없다고 한 부품의 수요 (관리자만, API 가 403 으로도 막는다) */
export default async function PartRequestsPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <h1 className={ui.h1}>{t("부품 요청")}</h1>
        <p className={`${ui.muted} mb-6 mt-1`}>
          {t("설계 요청에서 카탈로그에 없다고 나온 부품이에요. 많이 찾는 부품부터 만들어 부품 라이브러리에 더해요.")}
        </p>
        {/* 주소의 ?status=·?sort=·?q=·?page= 를 읽으므로(useSearchParams) Suspense 안에서 그린다 */}
        <Suspense fallback={<PartRequestsPlaceholder />}>
          <PartRequestsAdmin />
        </Suspense>
      </main>
    </>
  );
}
