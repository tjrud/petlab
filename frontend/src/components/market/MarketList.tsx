"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { errorText, Placeholder } from "@/components/community/common";
import Pagination from "@/components/community/Pagination";
import { MARKET_CATEGORIES, MARKET_PATH } from "@/components/market/common";
import MarketItemCard from "@/components/market/MarketItemCard";
import RetryAlert from "@/components/RetryAlert";
import { api } from "@/lib/api";
import type { MarketItemSummary, Paged } from "@/lib/types";
import { ui } from "@/lib/ui";

const PAGE_SIZE = 24;

function parsePage(raw: string | null): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 && n <= 1000 ? n : 1;
}

function listHref(category: string | null, page = 1): string {
  const q = new URLSearchParams();
  if (category) q.set("category", category);
  if (page > 1) q.set("page", String(page));
  const s = q.toString();
  return s ? `${MARKET_PATH}?${s}` : MARKET_PATH;
}

type Result =
  | { key: string; kind: "ok"; data: Paged<MarketItemSummary> }
  | { key: string; kind: "error"; message: string };

export function MarketListPlaceholder() {
  return <Placeholder rows={3} label="작품 목록을 불러오는 중이에요" rowClassName="h-40" />;
}

/** 둥지마당 작품 목록 (누구나). 분류·페이지는 주소(?category=&page=)로 */
export default function MarketList() {
  const params = useSearchParams();
  const rawCat = params.get("category");
  const category = MARKET_CATEGORIES.some((c) => c.key === rawCat) ? rawCat : null;
  const page = parsePage(params.get("page"));
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const key = `${category}|${page}|${attempt}`;

  useEffect(() => {
    let alive = true;
    api.marketItems(page, PAGE_SIZE, category ?? undefined).then(
      (data) => alive && setResult({ key, kind: "ok", data }),
      (e: unknown) => alive && setResult({ key, kind: "error", message: errorText(e, "작품 목록을 불러오지 못했어요.") }),
    );
    return () => {
      alive = false;
    };
  }, [page, category, key]);

  const r = result?.key === key ? result : null;
  const chips = (
    <nav aria-label="분류" className="mb-5 flex flex-wrap gap-1.5">
      {[{ key: null, label: "전체" }, ...MARKET_CATEGORIES].map((c) => {
        const on = category === c.key;
        return (
          <Link
            key={c.label}
            href={listHref(c.key)}
            aria-current={on ? "page" : undefined}
            className={`rounded-full border px-3 py-1 text-sm ${
              on ? "border-amber-500 bg-amber-100 font-semibold text-amber-900" : "border-stone-300 text-stone-600 hover:bg-stone-50"
            }`}
          >
            {c.label}
          </Link>
        );
      })}
    </nav>
  );

  if (!r) return (<>{chips}<MarketListPlaceholder /></>);
  if (r.kind === "error") return (<>{chips}<RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} /></>);
  const { items, total, page_size } = r.data;
  return (
    <>
      {chips}
      {total === 0 ? (
        <div className={`${ui.card} py-12 text-center`}>
          <p className="text-lg font-semibold">{category ? "이 분류에는 아직 작품이 없어요." : "아직 올라온 작품이 없어요."}</p>
          <p className="mt-1 text-sm text-stone-600">SKP·3MF·STL 파일이나 NestForge 설계를 올려 주세요.</p>
        </div>
      ) : (
        <>
          <p className={`${ui.muted} mb-3`}>작품 {total}개</p>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((it) => (
              <MarketItemCard key={it.id} item={it} />
            ))}
          </ul>
          {total > page_size && (
            <Pagination page={page} totalPages={Math.ceil(total / page_size)} hrefFor={(p) => listHref(category, p)} />
          )}
        </>
      )}
    </>
  );
}
