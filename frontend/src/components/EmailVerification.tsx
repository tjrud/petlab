"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { api, ApiError } from "@/lib/api";

// 이메일 인증: 인증 메일 다시 보내기, 헤더 아래 안내 띠, 설계·글쓰기·댓글 폼 안의 안내

type ResendResult = { ok: boolean; message: string };

/** 인증 메일 다시 보내기. 1분 안에 다시 누르거나 하루 한도를 넘으면 서버 안내(email_cooldown·too_many_emails)를 보여 준다 */
export function useResendVerification() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ResendResult | null>(null);

  const resend = useCallback(async () => {
    setBusy(true);
    setResult(null);
    try {
      const r = await api.resendVerification();
      setResult(
        r.sent
          ? { ok: true, message: `인증 메일을 보냈어요 (${r.email}). 메일함(스팸함 포함)을 확인해 주세요.` }
          : { ok: false, message: r.message_ko },
      );
    } catch (e) {
      setResult({
        ok: false,
        message: e instanceof ApiError ? e.messageKo : "인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.",
      });
    } finally {
      setBusy(false);
    }
  }, []);

  return { resend, busy, result };
}

/** "인증 메일 다시 보내기" 버튼과 결과 */
export function ResendVerification({ className = "" }: { className?: string }) {
  const { resend, busy, result } = useResendVerification();
  return (
    <span className={`inline-flex flex-wrap items-center gap-x-2 gap-y-1 ${className}`}>
      <button
        type="button"
        onClick={resend}
        disabled={busy}
        className="whitespace-nowrap font-semibold underline underline-offset-2 disabled:opacity-50"
      >
        {busy ? "보내는 중…" : "인증 메일 다시 보내기"}
      </button>
      {result && (
        <span role={result.ok ? "status" : "alert"} className={result.ok ? "text-emerald-800" : "text-red-700"}>
          {result.message}
        </span>
      )}
    </span>
  );
}

/** 헤더 아래 안내 띠: 이메일 인증을 마치지 않은 회원에게 (이메일이 없는 예전 회원에게는 등록 안내) */
export function EmailVerifyBanner() {
  const { user, emailUnverified } = useAuth();
  if (!emailUnverified || !user) return null;
  return (
    <section aria-label="이메일 인증 안내" className="border-b border-amber-200 bg-amber-50 text-sm text-amber-950">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2">
        {user.email ? (
          <>
            <p className="min-w-0">
              이메일 인증을 마치면 설계·글쓰기·댓글을 쓸 수 있어요.{" "}
              <span className="break-all font-medium">({user.email})</span>
            </p>
            <ResendVerification />
          </>
        ) : (
          <>
            <p className="min-w-0">이메일을 등록하고 인증하면 설계·글쓰기·댓글을 쓸 수 있어요.</p>
            <Link href="/me#email" className="whitespace-nowrap font-semibold underline underline-offset-2">
              내 정보에서 이메일 등록하기
            </Link>
          </>
        )}
      </div>
    </section>
  );
}

/**
 * 폼 안의 안내: 이메일 인증 전이라 보낼 수 없을 때 (쓰던 내용은 그대로 둔다).
 * action 은 "설계를 받을", "글을 올릴"처럼 "~ 수 있어요" 앞에 오는 말.
 */
export function EmailUnverifiedNotice({ action }: { action: string }) {
  const { user, refresh } = useAuth();
  const [checking, setChecking] = useState(false);
  return (
    <div role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">
      <p>
        이메일 인증을 마치면 {action} 수 있어요.{" "}
        {user?.email ? (
          <>
            메일함에서 인증 링크를 눌러 주세요 <span className="break-all">({user.email})</span>.
          </>
        ) : (
          "내 정보에서 이메일을 등록하고 인증해 주세요."
        )}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        {user?.email ? (
          <ResendVerification />
        ) : (
          <Link href="/me#email" className="font-semibold underline underline-offset-2">
            내 정보로 가기
          </Link>
        )}
        <button
          type="button"
          disabled={checking}
          onClick={async () => {
            setChecking(true);
            await refresh(); // 다른 기기에서 인증했을 수 있다
            setChecking(false);
          }}
          className="whitespace-nowrap underline underline-offset-2 disabled:opacity-50"
        >
          {checking ? "확인 중…" : "인증을 마쳤다면 다시 확인"}
        </button>
      </div>
    </div>
  );
}
