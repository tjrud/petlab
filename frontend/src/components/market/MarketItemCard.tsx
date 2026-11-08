/* eslint-disable @next/next/no-img-element -- 미리보기는 Blob 공개 주소(외부)에서 바로 받는다 */
import Link from "next/link";

import { AuthorName } from "@/components/community/common";
import { FormatChips, imageSrc, marketHref, NoPreview } from "@/components/market/common";
import type { MarketItemSummary } from "@/lib/types";
import { formatDate } from "@/lib/ui";

/** 탐색 목록의 작품 카드 */
/** eager: 첫 줄 카드는 이미지를 미리 받는다 (나머지는 화면에 들어올 때) */
export default function MarketItemCard({ item, eager = false }: { item: MarketItemSummary; eager?: boolean }) {
  return (
    <li>
      <Link
        href={marketHref(item.id)}
        className="group flex h-full flex-col overflow-hidden rounded-2xl border border-amber-200 bg-white shadow-sm transition hover:border-amber-400 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
      >
        <div className="aspect-[4/3] w-full overflow-hidden bg-stone-100">
          {item.image ? (
            <img
              src={imageSrc(item.image)}
              alt=""
              loading={eager ? "eager" : "lazy"}
              fetchPriority={eager ? "high" : "auto"}
              decoding="async"
              className="h-full w-full object-cover transition group-hover:scale-[1.02]" />
          ) : (
            <NoPreview formats={item.formats} />
          )}
        </div>
        <div className="flex flex-1 flex-col gap-2 p-4">
          <p className="text-xs font-medium text-amber-800">{item.category_name_ko}</p>
          <h2 className="break-words font-semibold leading-snug">{item.title}</h2>
          <FormatChips formats={item.formats} />
          {item.reason_ko && <p className="text-xs text-teal-800">{item.reason_ko}</p>}
          <p className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 text-xs text-stone-500">
            <AuthorName author={item.author} />
            <span aria-hidden>·</span>
            <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
            <span aria-hidden>·</span>
            <span>내려받기 {item.download_count}</span>
          </p>
        </div>
      </Link>
    </li>
  );
}
