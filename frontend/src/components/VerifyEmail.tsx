"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ResendVerification } from "@/components/EmailVerification";
import { api, ApiError } from "@/lib/api";
import type { VerifyEmailResult } from "@/lib/types";
import { ui } from "@/lib/ui";

type State =
  | { kind: "ok"; message: string }
  | { kind: "invalid" }
  | { kind: "taken" }
  | { kind: "error"; message: string };

// 같은 토큰은 한 번만 보낸다 (개발 모드에서 effect 가 두 번 돌거나, 숨겨졌던 화면이 다시 보여도).
// 실패해서 "다시 시도"를 누를 때만 지운다.
const attempts = new Map<string, Promise<VerifyEmailResult>>();

function verifyOnce(token: string): Promise<VerifyEmailResult> {
  let p = attempts.get(token);
  if (!p) {
    p = api.verifyEmail(token);
    attempts.set(token, p);
  }
  return p;
}

function classify(e: unknown): State {
  if (e instanceof ApiError) {
    if (e.code === "invalid_token" || e.code === "validation_error") return { kind: "invalid" };
    if (e.code === "email_taken") return { kind: "taken" };
    return { kind: "error", message: e.messageKo };
  }
  return { kind: "error", message: "인증하지 못했어요. 잠시 뒤 다시 시도해 주세요." };
}

export function VerifyEmailPlaceholder() {
  return (
    <div className={ui.card}>
      <p role="status" className={ui.muted}>
        이메일을 인증하는 중이에요…
      </p>
    </div>
  );
}

function Links({ primary }: { primary: "design" | "me" }) {
  return (
    <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-center">
      {primary === "design" ? (
        <Link href="/design" className={ui.btnPrimary}>
          설계하기
        </Link>
      ) : (
        <Link href="/me#email" className={ui.btnPrimary}>
          내 정보로 가기
        </Link>
      )}
      <Link href="/" className={ui.btnSecondary}>
        메인 화면으로
      </Link>
      {primary === "design" && (
        <Link href="/me" className={ui.btnSecondary}>
          내 정보 보기
        </Link>
      )}
    </div>
  );
}

/** 인증을 마친 화면 */
function Verified({ message, loggedOut }: { message: string; loggedOut: boolean }) {
  return (
    <div role="status" className={`${ui.card} text-center`}>
      <p className="text-4xl" aria-hidden>
        🎉
      </p>
      <h2 className={`${ui.h2} mt-2`}>이메일 인증을 마쳤어요</h2>
      <p className="mt-2 text-sm text-stone-600">
        {message}
        {loggedOut && " 로그인하면 바로 설계·글쓰기·댓글을 쓸 수 있어요."}
      </p>
      <Links primary="design" />
    </div>
  );
}

/**
 * 메일의 인증 링크(/verify-email?token=...)를 연 화면. 로그인하지 않아도 된다 (다른 브라우저에서 열 수 있다).
 * 인증에 성공하면 주소를 /verify-email?done=1 로 바꿔 토큰을 방문 기록에서 지운다
 * (새로고침하거나 탭을 되살려도 쓴 토큰을 다시 보내 "만료"로 보이지 않게).
 */
export default function VerifyEmail() {
  const params = useSearchParams();
  const token = params.get("token")?.trim() ?? "";
  const done = params.get("done") === "1";
  const { status, user, refresh } = useAuth();
  const loggedOut = status !== null && !user;
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; state: State } | null>(null);
  const key = `${token}|${attempt}`;

  useEffect(() => {
    if (!token) return;
    let alive = true;
    verifyOnce(token).then(
      (r) => {
        if (!alive) return;
        setResult({ key, state: { kind: "ok", message: r.message_ko } });
        void refresh(); // 헤더의 안내 띠를 걷고, 막혀 있던 기능을 바로 쓸 수 있게
        // 쓴 토큰을 주소와 방문 기록에서 지운다 (Next 가 useSearchParams 에 반영한다)
        window.history.replaceState(null, "", "/verify-email?done=1");
      },
      (e: unknown) => {
        if (alive) setResult({ key, state: classify(e) });
      },
    );
    return () => {
      alive = false;
    };
  }, [token, key, refresh]);

  if (!token) {
    if (done) return <Verified message="이제 설계·글쓰기·댓글을 쓸 수 있어요." loggedOut={loggedOut} />;
    return (
      <div role="alert" className={`${ui.card} text-center`}>
        <h2 className={ui.h2}>인증 링크가 올바르지 않아요</h2>
        <p className="mt-2 text-sm text-stone-600">
          링크의 일부가 빠진 것 같아요. 메일에 있는 링크를 다시 눌러 주세요. 메일을 찾을 수 없다면 내 정보에서 인증 메일을
          다시 보낼 수 있어요.
        </p>
        <Links primary="me" />
      </div>
    );
  }

  const state = result?.key === key ? result.state : null;
  if (!state) return <VerifyEmailPlaceholder />;

  if (state.kind === "ok") return <Verified message={state.message} loggedOut={loggedOut} />;

  if (state.kind === "invalid") {
    // 이미 인증을 마친 회원이 예전 링크를 다시 연 경우
    const alreadyVerified = !!user && user.role !== "admin" && user.email_verified;
    return (
      <div role="alert" className={`${ui.card} text-center`}>
        <h2 className={ui.h2}>{alreadyVerified ? "이미 인증을 마친 계정이에요" : "인증 링크가 올바르지 않거나 만료되었어요"}</h2>
        <p className="mt-2 text-sm text-stone-600">
          {alreadyVerified
            ? "이 링크는 이미 쓰였거나 만료되었지만, 지금 로그인한 계정은 이메일 인증을 마쳤어요."
            : "인증 링크는 한 번만 쓸 수 있고, 시간이 지나면 만료돼요. 가장 최근에 받은 메일의 링크를 눌러 주시거나 인증 메일을 다시 보내 주세요."}
        </p>
        {!alreadyVerified && user?.email && !user.email_verified && (
          <p className="mt-3 text-sm">
            <ResendVerification className="justify-center" />
          </p>
        )}
        {loggedOut && (
          <p className="mt-3 text-sm text-stone-600">
            이미 이 링크로 인증했다면 인증은 끝났어요. 로그인하면 확인할 수 있어요.{" "}
            <Link href={`/login?next=${encodeURIComponent("/me#email")}`} className={`${ui.link} font-semibold`}>
              로그인하기
            </Link>
          </p>
        )}
        <Links primary={alreadyVerified ? "design" : "me"} />
      </div>
    );
  }

  if (state.kind === "taken") {
    return (
      <div role="alert" className={`${ui.card} text-center`}>
        <h2 className={ui.h2}>다른 계정에서 이미 인증한 이메일이에요</h2>
        <p className="mt-2 text-sm text-stone-600">
          이 이메일 주소는 다른 계정에서 먼저 인증했어요. 내 정보에서 다른 이메일 주소로 바꾼 뒤 다시 인증해 주세요.
        </p>
        <Links primary="me" />
      </div>
    );
  }

  return (
    <div role="alert" className={`${ui.error} flex flex-wrap items-center justify-between gap-3`}>
      <span>{state.message}</span>
      <button
        type="button"
        className={ui.btnSecondary}
        onClick={() => {
          attempts.delete(token);
          setAttempt((n) => n + 1);
        }}
      >
        다시 시도
      </button>
    </div>
  );
}
