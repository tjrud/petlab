"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { CharCount, errorText, LIMITS, loginHref, postHref } from "@/components/community/common";
import { clearDraft, ReloginNotice, useDraftBackup } from "@/components/DraftRelogin";
import { EmailUnverifiedNotice } from "@/components/EmailVerification";
import { api, isAuthError, isEmailUnverified } from "@/lib/api";
import type { Comment } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 댓글 쓰기 (회원만). 로그인하지 않았으면 로그인 안내를 보여 준다 */
export default function CommentForm({ postId, onAdded }: { postId: string; onAdded: (c: Comment) => void }) {
  const { status, user, refresh, emailUnverified } = useAuth();
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 댓글 등록이 로그인 문제로 실패했다 */
  const [loginLost, setLoginLost] = useState(false);
  /** 서버가 이메일 인증 전이라고 거절했다 (쓴 내용은 그대로 두고 안내한다) */
  const [emailBlocked, setEmailBlocked] = useState(false);

  const draftKey = `comment:${postId}`;
  const dirty = body.trim() !== "";
  const needsLogin = status !== null && (!user || loginLost);
  // 그동안 쓴 댓글은 맡겨 두었다가 다시 로그인하고 돌아오면 되살린다
  useDraftBackup<{ body: string }>(draftKey, dirty ? { body } : null, needsLogin, (d) => setBody(d.body));

  if (status === null) return null;
  // 쓰던 댓글이 있으면 로그인이 풀려도 폼을 바꾸지 않는다 (아래 안내로 다시 로그인하게 한다)
  if (!user && !dirty) {
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
    setEmailBlocked(false);
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
      setLoginLost(false);
      clearDraft(draftKey);
      if (!user) void refresh(); // 다른 탭에서 다시 로그인한 경우: 헤더 등도 로그인 상태로 바꾼다
      onAdded(c);
    } catch (err) {
      if (isAuthError(err)) setLoginLost(true); // 쓴 내용은 그대로 두고 다시 로그인하게 한다
      else if (isEmailUnverified(err)) setEmailBlocked(true);
      else setError(errorText(err, "댓글을 올리지 못했어요. 다시 시도해 주세요."));
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
      {needsLogin && <ReloginNotice next={postHref(postId)} />}
      {!needsLogin && (emailUnverified || emailBlocked) && <EmailUnverifiedNotice action="댓글을 쓸" />}
      <div className="flex items-center justify-between gap-3">
        <CharCount id="comment-body-count" length={body.length} max={LIMITS.comment} />
        <button type="submit" className={ui.btnPrimary} disabled={submitting || emailUnverified}>
          {submitting ? "등록 중…" : "댓글 등록"}
        </button>
      </div>
    </form>
  );
}
