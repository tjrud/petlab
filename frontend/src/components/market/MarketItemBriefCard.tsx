/* eslint-disable @next/next/no-img-element -- 미리보기는 Blob 공개 주소(외부)에서 바로 받는다 */
import { Link, useT } from "@/i18n/client";

import { FormatChips, imageSrc, marketHref, NoPreview } from "@/components/market/common";
import type { MarketItemBrief } from "@/lib/types";

/** 커뮤니티 소개 글에 붙는 공유 작품 카드 */
export default function MarketItemBriefCard({ item }: { item: MarketItemBrief }) {
  const t = useT();
  return (
    <Link
      href={marketHref(item.id)}
      className="mt-5 flex items-center gap-4 rounded-xl border border-lime-200 bg-lime-50/60 p-3 hover:border-lime-400"
    >
      <span className="h-16 w-20 shrink-0 overflow-hidden rounded-lg bg-stone-100">
        {item.image ? <img src={imageSrc(item.image)} alt="" className="h-full w-full object-cover" /> : <NoPreview formats={item.formats} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-semibold text-lime-800">{t("공유 작품")}</span>
        <span className="block truncate font-semibold">{item.title}</span>
        <FormatChips formats={item.formats} className="mt-1" />
      </span>
      <span className="shrink-0 text-sm font-medium text-lime-800">{t("파일 받기 →")}</span>
    </Link>
  );
}
