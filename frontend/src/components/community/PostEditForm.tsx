"use client";

import { useEffect, useRef, useState } from "react";

import { checkPost, errorText } from "@/components/community/common";
import PostFields from "@/components/community/PostFields";
import { api } from "@/lib/api";
import type { Post } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 글 보기 화면 안에서 바로 고치는 폼 (작성자만) */
export default function PostEditForm({
  post,
  onSaved,
  onCancel,
}: {
  post: Post;
  onSaved: (p: Post) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(post.title);
  const [body, setBody] = useState(post.body);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tried, setTried] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  // 수정을 시작하면 제목 입력으로 초점을 옮긴다
  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setTried(true);
    const invalid = checkPost(title, body);
    if (invalid) {
      setError(invalid);
      return;
    }
    const patch: { title?: string; body?: string } = {};
    if (title.trim() !== post.title) patch.title = title.trim();
    if (body.trim() !== post.body) patch.body = body.trim();
    if (patch.title === undefined && patch.body === undefined) {
      onCancel(); // 바뀐 내용이 없으면 그냥 닫는다
      return;
    }
    setSaving(true);
    try {
      onSaved(await api.updatePost(post.id, patch));
    } catch (err) {
      setError(errorText(err, "글을 수정하지 못했어요. 다시 시도해 주세요."));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} noValidate aria-label="글 수정" className="space-y-4">
      <PostFields
        idPrefix="edit"
        title={title}
        body={body}
        onTitle={setTitle}
        onBody={setBody}
        disabled={saving}
        invalid={tried}
        titleRef={titleRef}
      />
      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" className={ui.btnSecondary} onClick={onCancel} disabled={saving}>
          취소
        </button>
        <button type="submit" className={ui.btnPrimary} disabled={saving}>
          {saving ? "저장 중…" : "저장"}
        </button>
      </div>
    </form>
  );
}
