import type { Metadata } from "next";
import { Link } from "@/i18n/client";
import { Suspense } from "react";

import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import { MARKET_PATH } from "@/components/market/common";
import MarketItemDetail, { MarketItemPlaceholder } from "@/components/market/MarketItemDetail";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("공유 작품") };
}

export default async function MarketItemPage({ params }: { params: Promise<{ id: string }> }) {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mx-auto max-w-3xl">
          <Link href={MARKET_PATH} className={`${ui.link} mb-3 inline-block text-sm font-medium`}>
            <span aria-hidden>← </span>
            {t("탐색")}
          </Link>
          <Suspense fallback={<MarketItemPlaceholder />}>{params.then(({ id }) => <MarketItemDetail id={id} />)}</Suspense>
        </div>
      </main>
    </>
  );
}
