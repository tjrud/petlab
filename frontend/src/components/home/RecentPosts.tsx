"use client";

import { Link } from "@/i18n/client";

import { LoadError, Skeleton, useLoad } from "@/components/home/Loadable";
import { api } from "@/lib/api";
import type { PostSummary } from "@/lib/types";
import { formatDate, ui } from "@/lib/ui";

const loadPosts = () => api.posts(1, 5);

function PostRow({ p }: { p: PostSummary }) {
  return (
    <li>
      <Link
        href={`/community/${encodeURIComponent(p.id)}`}
        className="block px-4 py-3 transition hover:bg-amber-50/60 sm:px-5"
      >
        <div className="flex min-w-0 items-center gap-2">
          <p className="min-w-0 truncate font-medium">{p.title}</p>
          {p.has_design && <span className={`${ui.badge} shrink-0`}>설계 첨부</span>}
        </div>
        {p.excerpt && <p className="mt-0.5 line-clamp-1 break-words text-sm text-stone-600">{p.excerpt}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-500">
          <span className="flex min-w-0 items-center gap-1">
            {p.author.role === "admin" && (
              <span className="shrink-0 rounded bg-stone-800 px-1.5 py-0.5 text-white">관리자</span>
            )}
            <span className="max-w-[12rem] truncate">{p.author.nickname}</span>
          </span>
          <span aria-hidden>·</span>
          <span>{formatDate(p.created_at)}</span>
          <span aria-hidden>·</span>
          <span>댓글 {p.comment_count}</span>
        </p>
      </Link>
    </li>
  );
}

/** 메인 화면: 최근 커뮤니티 글 5개 (누구나 볼 수 있음) */
export default function RecentPosts() {
  const { state, retry } = useLoad(loadPosts, "커뮤니티 글을 불러오지 못했어요.");

  return (
    <section aria-labelledby="recent-posts-title" className="mt-12">
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 id="recent-posts-title" className="text-xl font-bold sm:text-2xl">
            최근 커뮤니티 글
          </h2>
          <p className="mt-1 text-sm text-stone-600">다른 보호자들은 어떤 구조물을 만들었을까요?</p>
        </div>
        <Link href="/community" className={`${ui.link} shrink-0 text-sm font-medium`}>
          전체 보기
        </Link>
      </div>

      <div className="mt-5">
        {state.kind === "loading" && (
          <div className={ui.card}>
            <Skeleton rows={5} label="최근 글을 불러오는 중이에요" rowClassName="h-14" />
          </div>
        )}
        {state.kind === "error" && <LoadError message={state.message} needsLogin={state.needsLogin} onRetry={retry} />}
        {state.kind === "ok" &&
          (state.data.items.length === 0 ? (
            <div className={`${ui.card} text-center`}>
              <p className="font-medium">아직 올라온 글이 없어요.</p>
              <p className="mt-1 text-sm text-stone-600">설계나 사육 이야기를 올려 주세요.</p>
              <Link href="/community" className={`${ui.btnSecondary} mt-4`}>
                커뮤니티로 가기
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-amber-100 overflow-hidden rounded-2xl border border-amber-200 bg-white shadow-sm">
              {state.data.items.map((p) => (
                <PostRow key={p.id} p={p} />
              ))}
            </ul>
          ))}
      </div>
    </section>
  );
}
