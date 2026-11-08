"use client";

import { useT } from "@/i18n/client";
import CommentForm from "@/components/community/CommentForm";
import CommentItem from "@/components/community/CommentItem";
import type { Comment } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 댓글 목록과 댓글 쓰기. 댓글이 아주 많으면 서버가 최근 것만 보내 준다 (total 은 전체 개수) */
export default function CommentSection({
  postId,
  comments,
  total,
  onAdded,
  onRemoved,
}: {
  postId: string;
  comments: Comment[];
  total: number;
  onAdded: (c: Comment) => void;
  onRemoved: (id: string) => void;
}) {
  const t = useT();
  return (
    <section aria-labelledby="comments-title" className={ui.card}>
      <h2 id="comments-title" className={ui.h2}>
        {t("댓글 {n}", { n: total })}
      </h2>
      {total > comments.length && (
        <p className={`${ui.muted} mt-1`}>{t("댓글이 많아서 최근 {n}개만 보여요.", { n: comments.length })}</p>
      )}
      {comments.length === 0 ? (
        <p className={`${ui.muted} mt-3`}>{t("아직 댓글이 없어요.")}</p>
      ) : (
        <ul className="mt-1 divide-y divide-stone-100">
          {comments.map((c) => (
            <CommentItem key={c.id} comment={c} onRemoved={onRemoved} />
          ))}
        </ul>
      )}
      <CommentForm postId={postId} onAdded={onAdded} />
    </section>
  );
}
