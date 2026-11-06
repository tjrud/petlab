"use client";

import { useState } from "react";

import { AuthorName, errorText, wasEdited } from "@/components/community/common";
import PostEditForm from "@/components/community/PostEditForm";
import PostImages from "@/components/community/PostImages";
import MarketItemBriefCard from "@/components/market/MarketItemBriefCard";
import { api } from "@/lib/api";
import type { Post } from "@/lib/types";
import { formatDateTime, ui } from "@/lib/ui";

/** 글 본문 (작성자는 바로 고치고, 작성자·관리자는 지울 수 있다). 모든 내용은 일반 텍스트로 보여 준다 */
export default function PostArticle({
  post,
  onUpdated,
  onDeleted,
}: {
  post: Post;
  onUpdated: (p: Post) => void;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (!window.confirm("이 글을 삭제할까요? 달린 댓글도 함께 지워지고 되돌릴 수 없어요.")) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deletePost(post.id);
      setDeleting(false);
      onDeleted();
    } catch (e) {
      setError(errorText(e, "글을 삭제하지 못했어요. 다시 시도해 주세요."));
      setDeleting(false);
    }
  }

  const edited = wasEdited(post.created_at, post.updated_at);

  return (
    <article className={ui.card}>
      {editing ? (
        <>
          <h1 className="sr-only">{post.title}</h1>
          <h2 className={`${ui.h2} mb-4`}>글 수정</h2>
          <PostEditForm
            post={post}
            onCancel={() => setEditing(false)}
            onSaved={(p) => {
              setEditing(false);
              onUpdated(p);
            }}
          />
        </>
      ) : (
        <>
          <header className="border-b border-amber-100 pb-4">
            <h1 className="break-words text-2xl font-bold leading-snug sm:text-3xl">{post.title}</h1>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-stone-500">
                <AuthorName author={post.author} />
                <span aria-hidden>·</span>
                <time dateTime={post.created_at}>{formatDateTime(post.created_at)}</time>
                {edited && <span title={`${formatDateTime(post.updated_at)} 수정`}>(수정됨)</span>}
              </p>
              {(post.can_edit || post.can_delete) && (
                <div className="flex shrink-0 gap-2">
                  {post.can_edit && (
                    <button
                      type="button"
                      className={ui.btnSecondary}
                      disabled={deleting}
                      onClick={() => {
                        setError(null);
                        setEditing(true);
                      }}
                    >
                      수정
                    </button>
                  )}
                  {post.can_delete && (
                    <button type="button" className={ui.btnDanger} disabled={deleting} onClick={remove}>
                      {deleting ? "삭제 중…" : "삭제"}
                    </button>
                  )}
                </div>
              )}
            </div>
          </header>
          {error && (
            <p role="alert" className={`${ui.error} mt-4`}>
              {error}
            </p>
          )}
          <PostImages images={post.images ?? []} />
          {post.market_item && <MarketItemBriefCard item={post.market_item} />}
          <div className="mt-5 whitespace-pre-wrap break-words leading-relaxed text-stone-800">{post.body}</div>
        </>
      )}
    </article>
  );
}
