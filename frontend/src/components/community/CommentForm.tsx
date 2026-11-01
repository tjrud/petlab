"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { CharCount, errorText, LIMITS, loginHref, postHref } from "@/components/community/common";
import { api } from "@/lib/api";
import type { Comment } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 댓글 쓰기 (회원만). 로그인하지 않았으면 로그인 안내를 보여 준다 */
export default function CommentForm({ postId, onAdded }: { postId: string; onAdded: (c: Comment) => void }) {
  const { status, user } = useAuth();
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === null) return null;
  if (!user) {
    return (
      <div className="mt-4 rounded-xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-700">
        <p>댓글은 회원만 남길 수 있어요.</p>
        <Link href={loginHref(postHref(postId))} className={`${ui.link} mt-1 inline-block font-semibold`}>
          로그인하고 댓글 쓰기
        </Link>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const text = body.trim();
    if (!text) {
      setError("댓글 내용을 입력해 주세요.");
      return;
    }
    if (text.length > LIMITS.comment) {
      setError(`댓글은 ${LIMITS.comment}자까지 쓸 수 있어요.`);
      return;
    }
    setSubmitting(true);
    try {
      const c = await api.createComment(postId, text);
      setBody("");
      onAdded(c);
    } catch (err) {
      setError(errorText(err, "댓글을 올리지 못했어요. 다시 시도해 주세요."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="mt-4 space-y-2">
      <label htmlFor="comment-body" className={ui.label}>
        댓글
      </label>
      <textarea
        id="comment-body"
        rows={3}
        className={`${ui.input} resize-y leading-relaxed`}
        value={body}
        maxLength={LIMITS.comment}
        disabled={submitting}
        aria-describedby="comment-body-count"
        placeholder="따뜻한 말 한마디나 궁금한 점을 남겨 주세요."
        onChange={(e) => setBody(e.target.value)}
      />
      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      <div className="flex items-center justify-between gap-3">
        <CharCount id="comment-body-count" length={body.length} max={LIMITS.comment} />
        <button type="submit" className={ui.btnPrimary} disabled={submitting}>
          {submitting ? "등록 중…" : "댓글 등록"}
        </button>
      </div>
    </form>
  );
}
