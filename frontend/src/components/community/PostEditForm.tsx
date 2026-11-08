"use client";

import { useEffect, useRef, useState } from "react";

import { useT } from "@/i18n/client";
import { useAuth } from "@/components/AuthProvider";
import { checkPost, errorText } from "@/components/community/common";
import ImagePicker from "@/components/community/ImagePicker";
import PostFields from "@/components/community/PostFields";
import { api } from "@/lib/api";
import type { Post, PostImage } from "@/lib/types";
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
  const t = useT();
  const [title, setTitle] = useState(post.title);
  const [body, setBody] = useState(post.body);
  const [images, setImages] = useState<PostImage[]>(post.images ?? []);
  // 사진은 운영팀만 넣을 수 있다 (서버도 확인한다)
  const isAdmin = useAuth().user?.role === "admin";
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
    const invalid = checkPost(title, body, t);
    if (invalid) {
      setError(invalid);
      return;
    }
    const patch: { title?: string; body?: string; images?: PostImage[] } = {};
    if (title.trim() !== post.title) patch.title = title.trim();
    if (body.trim() !== post.body) patch.body = body.trim();
    const srcs = (l: PostImage[]) => l.map((i) => i.src).join("|");
    if (isAdmin && srcs(images) !== srcs(post.images ?? [])) patch.images = images;
    if (patch.title === undefined && patch.body === undefined && patch.images === undefined) {
      onCancel(); // 바뀐 내용이 없으면 그냥 닫는다
      return;
    }
    setSaving(true);
    try {
      onSaved(await api.updatePost(post.id, patch));
    } catch (err) {
      setError(errorText(err, t("글을 수정하지 못했어요. 다시 시도해 주세요.")));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} noValidate aria-label={t("글 수정")} className="space-y-4">
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
      {isAdmin && <ImagePicker value={images} onChange={setImages} disabled={saving} />}
      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" className={ui.btnSecondary} onClick={onCancel} disabled={saving}>
          {t("취소")}
        </button>
        <button type="submit" className={ui.btnPrimary} disabled={saving}>
          {saving ? t("저장 중…") : t("저장")}
        </button>
      </div>
    </form>
  );
}
