import type { Metadata } from "next";
import { Link } from "@/i18n/client";
import { Suspense } from "react";

import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import { NEW_MARKET_PATH } from "@/components/market/common";
import MarketList, { MarketListPlaceholder } from "@/components/market/MarketList";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return {
    title: t("탐색"),
    description: t("보호자들이 만든 은신처·터널·경사로 SKP·3MF·STL 파일과 가상 케이지 배치를 나누는 곳."),
  };
}

export default async function MarketPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className={ui.h1}>{t("탐색")}</h1>
            <p className={`${ui.muted} mt-1`}>
              {t("보호자들이 만든 구조물 파일(SKP·3MF·STL)과 가상 케이지 배치를 내려받고 나누는 곳이에요.")}
            </p>
          </div>
          <Link href={NEW_MARKET_PATH} className={ui.btnPrimary}>
            {t("작품 올리기")}
          </Link>
        </div>
        <Suspense fallback={<MarketListPlaceholder />}>
          <MarketList />
        </Suspense>
      </main>
    </>
  );
}
