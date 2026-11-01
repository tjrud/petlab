"use client";

import { useState } from "react";

import { AuthorName, errorText } from "@/components/community/common";
import { api, ApiError } from "@/lib/api";
import type { Comment } from "@/lib/types";
import { formatDateTime, ui } from "@/lib/ui";

/** 댓글 하나 (작성자·관리자는 지울 수 있다). 본문은 일반 텍스트로 보여 준다 */
export default function CommentItem({ comment: c, onRemoved }: { comment: Comment; onRemoved: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (!window.confirm("이 댓글을 삭제할까요?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteComment(c.id);
      onRemoved(c.id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        onRemoved(c.id); // 이미 지워진 댓글
        return;
      }
      setError(errorText(e, "댓글을 삭제하지 못했어요. 다시 시도해 주세요."));
      setBusy(false);
    }
  }

  return (
    <li className="py-4">
      <div className="flex items-start justify-between gap-3">
        <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <AuthorName author={c.author} />
          <time dateTime={c.created_at} className="text-xs text-stone-500">
            {formatDateTime(c.created_at)}
          </time>
        </p>
        {c.can_delete && (
          <button
            type="button"
            className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            disabled={busy}
            onClick={remove}
          >
            <span className="sr-only">댓글 </span>
            {busy ? "삭제 중…" : "삭제"}
          </button>
        )}
      </div>
      <p className="mt-1.5 whitespace-pre-wrap break-words leading-relaxed text-stone-800">{c.body}</p>
      {error && (
        <p role="alert" className={`${ui.error} mt-2`}>
          {error}
        </p>
      )}
    </li>
  );
}
