"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { errorText, Placeholder } from "@/components/community/common";
import Pagination from "@/components/Pagination";
import { MARKET_CATEGORIES, MARKET_PATH } from "@/components/market/common";
import MarketItemCard from "@/components/market/MarketItemCard";
import RetryAlert from "@/components/RetryAlert";
import { api } from "@/lib/api";
import type { MarketItemSummary, Paged } from "@/lib/types";
import { ui } from "@/lib/ui";

const PAGE_SIZE = 24;
/** 주소에 분류가 없으면 "추천", ?category=all 이면 "전체" */
const ALL = "all";

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
  | { key: string; kind: "list"; data: Paged<MarketItemSummary> }
  | { key: string; kind: "recommended"; items: MarketItemSummary[] }
  | { key: string; kind: "error"; message: string };

export function MarketListPlaceholder() {
  return <Placeholder rows={3} label="작품 목록을 불러오는 중이에요" rowClassName="h-40" />;
}

/** 탐색 (누구나): 추천(기본)·전체·분류별. 분류·페이지는 주소(?category=&page=)로 */
export default function MarketList() {
  const params = useSearchParams();
  const { user, status } = useAuth();
  const rawCat = params.get("category");
  const category = rawCat === ALL || MARKET_CATEGORIES.some((c) => c.key === rawCat) ? rawCat : null;
  const page = parsePage(params.get("page"));
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  // 추천은 서버가 로그인 쿠키로 정하므로 로그인 확인을 기다리지 않고 바로 받는다.
  // 이 화면에서 로그인·로그아웃해 회원이 바뀌었을 때만 다시 받는다 (처음 확인된 회원은 그대로)
  const uid = status === null ? undefined : (user?.id ?? null);
  const [seen, setSeen] = useState<{ uid: string | null | undefined; epoch: number }>({ uid: undefined, epoch: 0 });
  if (uid !== undefined && uid !== seen.uid) {
    setSeen({ uid, epoch: seen.uid === undefined ? seen.epoch : seen.epoch + 1 });
  }
  const key = `${category}|${page}|${attempt}|${category === null ? seen.epoch : 0}`;

  useEffect(() => {
    let alive = true;
    const fail = (e: unknown) => alive && setResult({ key, kind: "error", message: errorText(e, "작품 목록을 불러오지 못했어요.") });
    if (category === null) {
      api.marketRecommended(PAGE_SIZE).then((items) => alive && setResult({ key, kind: "recommended", items }), fail);
    } else {
      api
        .marketItems(page, PAGE_SIZE, category === ALL ? undefined : category)
        .then((data) => alive && setResult({ key, kind: "list", data }), fail);
    }
    return () => {
      alive = false;
    };
  }, [page, category, key]);

  const r = result?.key === key ? result : null;
  const chips = (
    <nav aria-label="분류" className="mb-5 flex flex-wrap gap-1.5">
      {[{ key: null, label: "추천" }, { key: ALL, label: "전체" }, ...MARKET_CATEGORIES].map((c) => {
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

  const grid = (items: MarketItemSummary[]) => (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((it, i) => (
        <MarketItemCard key={it.id} item={it} eager={i < 3} />
      ))}
    </ul>
  );
  const empty = (msg: string) => (
    <div className={`${ui.card} py-12 text-center`}>
      <p className="text-lg font-semibold">{msg}</p>
      <p className="mt-1 text-sm text-stone-600">SKP·3MF·STL 파일이나 가상 케이지 배치를 올려 주세요.</p>
    </div>
  );

  if (!r) return (<>{chips}<MarketListPlaceholder /></>);
  if (r.kind === "error") return (<>{chips}<RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} /></>);
  if (r.kind === "recommended") {
    return (
      <>
        {chips}
        <p className={`${ui.muted} mb-3`}>
          {user
            ? "내 설계·가상 케이지 배치안·반려동물·최근에 본 작품을 바탕으로 골랐어요."
            : "3D로 바로 볼 수 있는 작품, 많이 내려받은 작품, 새 작품 순이에요. 로그인하면 내 설계와 반려동물에 맞춘 추천이 보여요."}
        </p>
        {r.items.length === 0 ? empty("아직 추천할 작품이 없어요.") : grid(r.items)}
      </>
    );
  }
  const { items, total, page_size } = r.data;
  return (
    <>
      {chips}
      {total === 0 ? (
        empty(category === ALL ? "아직 올라온 작품이 없어요." : "이 분류에는 아직 작품이 없어요.")
      ) : (
        <>
          <p className={`${ui.muted} mb-3`}>작품 {total}개</p>
          {grid(items)}
          {total > page_size && (
            <Pagination page={page} totalPages={Math.ceil(total / page_size)} hrefFor={(p) => listHref(category, p)} />
          )}
        </>
      )}
    </>
  );
}
