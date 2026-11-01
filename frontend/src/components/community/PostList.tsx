"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { COMMUNITY_PATH, errorText, Placeholder } from "@/components/community/common";
import Pagination from "@/components/community/Pagination";
import PostListItem from "@/components/community/PostListItem";
import { api } from "@/lib/api";
import type { Paged, PostSummary } from "@/lib/types";
import { ui } from "@/lib/ui";

const PAGE_SIZE = 20;
const MAX_PAGE = 10_000; // 백엔드 허용 범위

/** 주소의 ?page= 값 (잘못된 값이면 1쪽) */
function parsePage(raw: string | null): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 && n <= MAX_PAGE ? n : 1;
}

const pageHref = (p: number) => (p <= 1 ? COMMUNITY_PATH : `${COMMUNITY_PATH}?page=${p}`);

type Result =
  | { key: string; kind: "ok"; data: Paged<PostSummary> }
  | { key: string; kind: "error"; message: string };

export function PostListPlaceholder() {
  return <Placeholder rows={5} label="글 목록을 불러오는 중이에요" />;
}

/** 커뮤니티 글 목록 (누구나 볼 수 있음). 주소의 페이지가 바뀌면 다시 불러온다 */
export default function PostList() {
  const params = useSearchParams();
  const page = parsePage(params.get("page"));
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  // 결과의 key 가 지금 key 와 다르면(이전 페이지의 결과) 불러오는 중으로 본다
  const key = `${page}|${attempt}`;

  useEffect(() => {
    let alive = true;
    api.posts(page, PAGE_SIZE).then(
      (data) => {
        if (alive) setResult({ key, kind: "ok", data });
      },
      (e: unknown) => {
        if (alive) setResult({ key, kind: "error", message: errorText(e, "글 목록을 불러오지 못했어요.") });
      },
    );
    return () => {
      alive = false;
    };
  }, [page, key]);

  const r = result?.key === key ? result : null;
  if (!r) return <PostListPlaceholder />;

  if (r.kind === "error") {
    return (
      <div role="alert" className={`${ui.error} flex flex-wrap items-center justify-between gap-3`}>
        <span>{r.message}</span>
        <button type="button" className={ui.btnSecondary} onClick={() => setAttempt((n) => n + 1)}>
          다시 시도
        </button>
      </div>
    );
  }

  const { items, total, page_size } = r.data;
  const totalPages = Math.max(1, Math.ceil(total / page_size));

  if (total === 0) {
    return (
      <div className={`${ui.card} flex flex-col items-center py-12 text-center`}>
        <p className="text-4xl" aria-hidden>
          💬
        </p>
        <p className="mt-3 text-lg font-semibold">아직 글이 없어요. 첫 글을 남겨 보세요!</p>
        <p className="mt-1 text-sm text-stone-600">우리 아이 케이지 설계나 사육 경험을 나눠 주세요.</p>
      </div>
    );
  }

  if (items.length === 0) {
    // 주소의 페이지 번호가 전체 페이지 수보다 큰 경우
    return (
      <div className={`${ui.card} text-center`}>
        <p className="font-medium">이 페이지에는 글이 없어요.</p>
        <Link href={pageHref(1)} className={`${ui.btnSecondary} mt-4`}>
          첫 페이지로
        </Link>
      </div>
    );
  }

  return (
    <div>
      <p className={`${ui.muted} mb-3`}>총 {total}개의 글</p>
      <ul className="divide-y divide-amber-100 overflow-hidden rounded-2xl border border-amber-200 bg-white shadow-sm">
        {items.map((p) => (
          <PostListItem key={p.id} post={p} />
        ))}
      </ul>
      {total > page_size && <Pagination page={page} totalPages={totalPages} hrefFor={pageHref} />}
    </div>
  );
}
