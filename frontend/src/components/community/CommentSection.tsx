"use client";

import CommentForm from "@/components/community/CommentForm";
import CommentItem from "@/components/community/CommentItem";
import type { Comment } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 댓글 목록과 댓글 쓰기 */
export default function CommentSection({
  postId,
  comments,
  onAdded,
  onRemoved,
}: {
  postId: string;
  comments: Comment[];
  onAdded: (c: Comment) => void;
  onRemoved: (id: string) => void;
}) {
  return (
    <section aria-labelledby="comments-title" className={ui.card}>
      <h2 id="comments-title" className={ui.h2}>
        댓글 {comments.length}
      </h2>
      {comments.length === 0 ? (
        <p className={`${ui.muted} mt-3`}>아직 댓글이 없어요. 첫 댓글을 남겨 보세요.</p>
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
