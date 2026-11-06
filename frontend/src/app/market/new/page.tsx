import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import Header from "@/components/Header";
import { MARKET_PATH } from "@/components/market/common";
import MarketNewForm, { MarketNewPlaceholder } from "@/components/market/MarketNewForm";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "작품 올리기 · 둥지마당" };

export default function MarketNewPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mx-auto max-w-3xl">
          <Link href={MARKET_PATH} className={`${ui.link} text-sm font-medium`}>
            <span aria-hidden>← </span>둥지마당
          </Link>
          <h1 className={`${ui.h1} mb-6 mt-2`}>작품 올리기</h1>
          <Suspense fallback={<MarketNewPlaceholder />}>
            <MarketNewForm />
          </Suspense>
        </div>
      </main>
    </>
  );
}
