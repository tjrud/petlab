import type { Metadata } from "next";
import { Link } from "@/i18n/client";
import { Suspense } from "react";

import DesignGridSkeleton from "@/components/designs/DesignGridSkeleton";
import DesignHistory from "@/components/designs/DesignHistory";
import Header from "@/components/Header";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "내 설계" };

export default function DesignsPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className={ui.h1}>내 설계</h1>
            <p className={`${ui.muted} mt-1`}>만든 설계를 최근 수정한 순서로 보여요.</p>
          </div>
          <Link href="/design" className={ui.btnPrimary}>
            새 설계
          </Link>
        </div>
        <Suspense fallback={<DesignGridSkeleton />}>
          <DesignHistory />
        </Suspense>
      </main>
    </>
  );
}
