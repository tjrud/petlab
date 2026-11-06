import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import Header from "@/components/Header";
import { NEW_MARKET_PATH } from "@/components/market/common";
import MarketList, { MarketListPlaceholder } from "@/components/market/MarketList";
import { ui } from "@/lib/ui";

export const metadata: Metadata = {
  title: "둥지마당",
  description: "보호자들이 만든 은신처·터널·경사로 SKP·3MF·STL 파일과 NestForge 설계를 나누는 곳.",
};

export default function MarketPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className={ui.h1}>둥지마당</h1>
            <p className={`${ui.muted} mt-1`}>보호자들이 만든 구조물 파일(SKP·3MF·STL)과 NestForge 설계를 내려받고 나누는 곳이에요.</p>
          </div>
          <Link href={NEW_MARKET_PATH} className={ui.btnPrimary}>
            작품 올리기
          </Link>
        </div>
        <Suspense fallback={<MarketListPlaceholder />}>
          <MarketList />
        </Suspense>
      </main>
    </>
  );
}
