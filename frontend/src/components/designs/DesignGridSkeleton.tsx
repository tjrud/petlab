"use client";

import { useT } from "@/i18n/client";

/** 설계 카드 목록을 불러오는 동안 보여 주는 자리 표시 (화면 낭독기에는 안내 문구만 읽힌다) */
export default function DesignGridSkeleton({ count = 6 }: { count?: number }) {
  const t = useT();
  return (
    <div role="status">
      <span className="sr-only">{t("설계 내역을 불러오는 중이에요")}</span>
      <ul aria-hidden className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: count }, (_, i) => (
          <li key={i} className="h-44 animate-pulse rounded-2xl border border-stone-200 bg-stone-100" />
        ))}
      </ul>
    </div>
  );
}
