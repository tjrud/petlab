"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { checkPost, COMMUNITY_PATH, errorText, NEW_POST_PATH, Placeholder, postHref } from "@/components/community/common";
import DesignAttachField, { useAttachOptions } from "@/components/community/DesignAttachField";
import PostFields from "@/components/community/PostFields";
import { clearDraft, ReloginNotice, useDraftBackup } from "@/components/DraftRelogin";
import { EmailUnverifiedNotice } from "@/components/EmailVerification";
import LoginRequired from "@/components/LoginRequired";
import { api, isAuthError, isEmailUnverified } from "@/lib/api";
import { ui } from "@/lib/ui";

const ID_RE = /^[0-9a-f]{32}$/;
const DRAFT_KEY = "post:new";

/** ?version= 값 (잘못된 값이면 최신 버전) */
function parseVersion(raw: string | null): number | undefined {
  const n = Number(raw);
  return raw && Number.isInteger(n) && n >= 1 && n <= 2 ** 31 - 1 ? n : undefined;
}

export function NewPostPlaceholder() {
  return <Placeholder rows={3} label="글쓰기 화면을 준비하는 중이에요" rowClassName="h-24" />;
}

/** 글쓰기 (회원 전용). 내 설계를 하나 골라 첨부할 수 있다 */
export default function NewPostForm() {
  const router = useRouter();
  const params = useSearchParams();
  const rawId = params.get("design");
  const preId = rawId && ID_RE.test(rawId) ? rawId : null;
  const preVersion = preId ? parseVersion(params.get("version")) : undefined;

  const { status, user, refresh, emailUnverified } = useAuth();
  const attach = useAttachOptions(user?.id ?? null, preId, preVersion);

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  /**
   * 사용자가 직접 고른 설계 (없으면 주소로 넘어온 설계를 그대로 쓴다).
   * 고를 때의 주소(?design=&version=)와 함께 기억해, 이 화면이 숨김 상태로 남아 있다가
   * "커뮤니티에 공유"로 다시 열리면(같은 설계라도 새로 들어온 경우: bfcacheId) 예전 선택 대신 넘어온 설계를 쓴다.
   * 뒤로 가기로 돌아오거나 그냥 글쓰기로 들어오면 고른 값을 그대로 둔다.
   */
  const preKey = preId ? `${router.bfcacheId}|${preId}|${preVersion}` : "";
  const [choice, setChoice] = useState<{ preKey: string; id: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; needsLogin: boolean } | null>(null);
  const [tried, setTried] = useState(false);
  /** 서버가 이메일 인증 전이라고 거절했다 (쓴 내용은 그대로 두고 안내한다) */
  const [emailBlocked, setEmailBlocked] = useState(false);

  const selectedId =
    choice?.preKey === preKey ? choice.id : attach.kind === "ok" ? (attach.preselect ?? "") : "";
  const selected = attach.kind === "ok" ? (attach.options.find((o) => o.id === selectedId) ?? null) : null;
  const dirty = title.trim() !== "" || body.trim() !== "";
  const query = params.toString();
  const here = query ? `${NEW_POST_PATH}?${query}` : NEW_POST_PATH;
  const attachAuthCode = attach.kind === "error" ? attach.authCode : null;
  // 로그인이 필요한 상태: 로그인이 풀렸거나(세션 만료 등), 글 올리기·내 설계 목록이 로그인 문제로 실패했다
  const needsLogin = status !== null && (!user || !!error?.needsLogin || attachAuthCode !== null);

  // 그동안 쓴 내용은 맡겨 두었다가 다시 로그인하고 돌아오면 되살린다
  useDraftBackup<{ title: string; body: string; design: string }>(
    DRAFT_KEY,
    dirty ? { title, body, design: selectedId } : null,
    needsLogin,
    (d) => {
      setTitle(d.title);
      setBody(d.body);
      setChoice({ preKey, id: d.design });
    },
  );

  if (status === null) return <NewPostPlaceholder />;
  // 쓰던 내용이 있으면 로그인이 풀려도 폼을 바꾸지 않는다 (아래 안내로 다시 로그인하게 한다)
  if (!user && !dirty) return <LoginRequired message="로그인하고 글을 써 보세요" />;
  if (attachAuthCode && !dirty) {
    return <LoginRequired message="로그인하고 글을 써 보세요" unavailable={attachAuthCode === "auth_unavailable"} />;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setEmailBlocked(false);
    setTried(true);
    const invalid = checkPost(title, body);
    if (invalid) {
      setError({ message: invalid, needsLogin: false });
      return;
    }
    setSubmitting(true);
    try {
      const post = await api.createPost({
        title: title.trim(),
        body: body.trim(),
        design_id: selected?.id ?? null,
        design_version: selected?.version ?? null,
      });
      // 이 화면은 숨김 상태로 남아 있을 수 있으므로(뒤로 가기·다시 방문) 입력을 비워 둔다
      setTitle("");
      setBody("");
      setChoice(null);
      setTried(false);
      setSubmitting(false);
      clearDraft(DRAFT_KEY);
      if (!user) void refresh(); // 다른 탭에서 다시 로그인한 경우: 헤더 등도 로그인 상태로 바꾼다
      // 글쓰기 화면을 기록에서 빼서, 뒤로 가기로 같은 글을 다시 올리지 않게 한다
      router.replace(postHref(post.id));
    } catch (err) {
      if (isEmailUnverified(err)) setEmailBlocked(true); // 아래 안내로 알려 준다 (쓴 내용은 그대로)
      else setError({ message: errorText(err, "글을 올리지 못했어요. 다시 시도해 주세요."), needsLogin: isAuthError(err) });
      setSubmitting(false);
    }
  }

  function cancel() {
    if (dirty && !window.confirm("작성 중인 내용이 사라져요. 글쓰기를 그만둘까요?")) return;
    setTitle("");
    setBody("");
    setChoice(null);
    setError(null);
    setTried(false);
    clearDraft(DRAFT_KEY);
    router.push(COMMUNITY_PATH);
  }

  return (
    <form onSubmit={submit} noValidate className={`${ui.card} space-y-5`}>
      <PostFields
        idPrefix="post"
        title={title}
        body={body}
        onTitle={setTitle}
        onBody={setBody}
        disabled={submitting}
        invalid={tried}
      />
      <DesignAttachField
        state={attach}
        value={selectedId}
        onChange={(id) => setChoice({ preKey, id })}
        disabled={submitting}
      />

      {error && !error.needsLogin && (
        <p role="alert" className={ui.error}>
          {error.message}
        </p>
      )}
      {needsLogin && <ReloginNotice next={here} message={error?.needsLogin ? error.message : undefined} />}
      {!needsLogin && (emailUnverified || emailBlocked) && <EmailUnverifiedNotice action="글을 올릴" />}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" className={ui.btnSecondary} onClick={cancel} disabled={submitting}>
          취소
        </button>
        <button
          type="submit"
          className={ui.btnPrimary}
          disabled={submitting || attach.kind === "loading" || emailUnverified}
        >
          {submitting ? "등록 중…" : "등록"}
        </button>
      </div>
    </form>
  );
}
