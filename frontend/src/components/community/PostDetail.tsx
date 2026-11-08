"use client";

import { Link } from "@/i18n/client";
import { useRouter } from "@/i18n/client";
import { useEffect, useState } from "react";

import CommentSection from "@/components/community/CommentSection";
import { COMMUNITY_PATH, errorText, Placeholder } from "@/components/community/common";
import PostArticle from "@/components/community/PostArticle";
import SharedDesignCard from "@/components/community/SharedDesignCard";
import RetryAlert from "@/components/RetryAlert";
import { api, ApiError } from "@/lib/api";
import type { Post } from "@/lib/types";
import { ui } from "@/lib/ui";

type Result =
  | { key: string; kind: "ok"; post: Post }
  | { key: string; kind: "error"; status: number; message: string };

export function PostPlaceholder() {
  return (
    <div className="mx-auto max-w-3xl">
      <Placeholder rows={3} label="글을 불러오는 중이에요" rowClassName="h-32" />
    </div>
  );
}

function BackLink() {
  return (
    <Link href={COMMUNITY_PATH} className={`${ui.link} text-sm font-medium`}>
      <span aria-hidden>← </span>목록으로
    </Link>
  );
}

function PostNotFound() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className={`${ui.card} text-center`}>
        <h1 className="mt-3 text-xl font-bold">글을 찾을 수 없어요</h1>
        <p className="mt-2 text-sm text-stone-600">주소가 잘못되었거나 삭제된 글이에요.</p>
        <Link href={COMMUNITY_PATH} className={`${ui.btnSecondary} mt-5`}>
          커뮤니티로 돌아가기
        </Link>
      </div>
    </div>
  );
}

/** 커뮤니티 글 보기 (누구나). 수정·삭제·댓글 권한은 서버가 알려 준다 (can_edit / can_delete) */
export default function PostDetail({ id }: { id: string }) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const key = `${id}|${attempt}`;

  useEffect(() => {
    let alive = true;
    api.post(id).then(
      (post) => {
        if (alive) setResult({ key, kind: "ok", post });
      },
      (e: unknown) => {
        if (!alive) return;
        setResult({
          key,
          kind: "error",
          status: e instanceof ApiError ? e.status : 0,
          message: errorText(e, "글을 불러오지 못했어요."),
        });
      },
    );
    return () => {
      alive = false;
    };
  }, [id, key]);

  const r = result?.key === key ? result : null;
  if (!r) return <PostPlaceholder />;

  if (r.kind === "error") {
    if (r.status === 404) return <PostNotFound />;
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <BackLink />
        <RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} />
      </div>
    );
  }

  const post = r.post;
  const update = (fn: (p: Post) => Post) =>
    setResult((cur) => (cur && cur.kind === "ok" ? { ...cur, post: fn(cur.post) } : cur));
  // 지운 글은 방문 기록에서 빼서 뒤로 가기로 다시 열리지 않게 한다
  const leaveDeleted = () => router.replace(COMMUNITY_PATH);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <BackLink />
      <PostArticle post={post} onUpdated={(p) => update(() => p)} onDeleted={leaveDeleted} />
      {post.design && <SharedDesignCard design={post.design} />}
      <CommentSection
        postId={post.id}
        comments={post.comments}
        total={post.comment_total}
        onAdded={(c) => update((p) => ({ ...p, comments: [...p.comments, c], comment_total: p.comment_total + 1 }))}
        onRemoved={(cid) =>
          update((p) =>
            p.comments.some((x) => x.id === cid)
              ? {
                  ...p,
                  comments: p.comments.filter((x) => x.id !== cid),
                  comment_total: Math.max(0, p.comment_total - 1),
                }
              : p,
          )
        }
      />
    </div>
  );
}
