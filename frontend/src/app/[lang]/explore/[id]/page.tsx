import type { Metadata } from "next";
import { Link } from "@/i18n/client";
import { Suspense } from "react";

import Header from "@/components/Header";
import { MARKET_PATH } from "@/components/market/common";
import MarketItemDetail, { MarketItemPlaceholder } from "@/components/market/MarketItemDetail";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "공유 작품" };

export default function MarketItemPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mx-auto max-w-3xl">
          <Link href={MARKET_PATH} className={`${ui.link} mb-3 inline-block text-sm font-medium`}>
            <span aria-hidden>← </span>탐색
          </Link>
          <Suspense fallback={<MarketItemPlaceholder />}>{params.then(({ id }) => <MarketItemDetail id={id} />)}</Suspense>
        </div>
      </main>
    </>
  );
}
