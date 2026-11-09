import Image from "next/image";
import { Link, useT } from "@/i18n/client";

import { AuthorName, postHref } from "@/components/community/common";
import type { PostSummary } from "@/lib/types";
import { formatDate, ui } from "@/lib/ui";

/** 글 목록의 한 줄 (누르면 글 보기). 제목·발췌·닉네임은 모두 일반 텍스트로 보여 준다 */
export default function PostListItem({ post: p }: { post: PostSummary }) {
  const t = useT();
  return (
    <li>
      <Link
        href={postHref(p.id)}
        className="flex gap-3 px-4 py-4 transition hover:bg-amber-50/60 focus-visible:bg-amber-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-400 sm:px-5"
      >
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start gap-2">
            <h2 className="min-w-0 flex-1 break-words font-semibold leading-snug">{p.title}</h2>
            {p.market_item_id && <span className={`${ui.badge} mt-0.5 shrink-0 bg-lime-100 text-lime-900`}>{t("탐색")}</span>}
            {p.has_design && <span className={`${ui.badge} mt-0.5 shrink-0`}>{t("설계 첨부")}</span>}
          </div>
          {p.excerpt && <p className="mt-1 line-clamp-2 break-words text-sm text-stone-600">{p.excerpt}</p>}
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-500">
            <AuthorName author={p.author} />
            <span aria-hidden>·</span>
            <time dateTime={p.created_at}>{formatDate(p.created_at)}</time>
            <span aria-hidden>·</span>
            <span>{t("댓글 {n}", { n: p.comment_count })}</span>
          </p>
        </div>
        {p.thumbnail && (
          <Image
            src={p.thumbnail.src}
            alt=""
            width={p.thumbnail.width}
            height={p.thumbnail.height}
            unoptimized
            className="h-16 w-20 shrink-0 rounded-lg bg-stone-100 object-cover sm:h-20 sm:w-28"
          />
        )}
      </Link>
    </li>
  );
}
