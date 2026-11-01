"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { api, ApiError } from "@/lib/api";
import { safeNext, withNext } from "@/lib/safeNext";
import { ui } from "@/lib/ui";

/** 이미 로그인한 사람이 로그인·회원가입 화면에 들어왔을 때 폼 대신 보여 준다 */
export function AlreadyLoggedIn({ nickname }: { nickname: string }) {
  return (
    <div role="status" className={`${ui.card} text-center`}>
      <h2 className={ui.h2}>이미 로그인했어요</h2>
      <p className="mt-2 break-words text-sm text-stone-600">
        <span className="font-medium text-stone-800">{nickname}</span>님으로 로그인한 상태예요.
      </p>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-center">
        <Link href="/" className={ui.btnPrimary}>
          메인 화면으로
        </Link>
        <Link href="/me" className={ui.btnSecondary}>
          내 정보 보기
        </Link>
      </div>
    </div>
  );
}

export default function LoginForm() {
  const params = useSearchParams();
  const next = params.get("next");
  const { status, user } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) return <AlreadyLoggedIn nickname={user.nickname} />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // 회원 아이디는 서버가 소문자로 맞춘다 (관리자 아이디는 대소문자를 그대로 비교하므로 여기서 바꾸지 않는다)
      await api.login(username.trim(), password);
      // 전체 새로고침으로 이동해 헤더 등 모든 화면이 로그인 상태를 다시 읽게 한다
      window.location.assign(safeNext(next, window.location.origin));
    } catch (err) {
      setError(err instanceof ApiError ? err.messageKo : "로그인하지 못했어요.");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className={`${ui.card} space-y-4`}>
        <p className="text-sm text-stone-600">
          회원 계정으로 로그인하면 AI 설계를 만들고, 내 설계 내역을 모아 보고, 커뮤니티에 글을 남길 수 있어요.
        </p>
        <div>
          <label htmlFor="login-username" className={ui.label}>
            아이디
          </label>
          <input
            id="login-username"
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            className={ui.input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="login-password" className={ui.label}>
            비밀번호
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className={ui.input}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p role="alert" className={ui.error}>
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting} className={`${ui.btnPrimary} w-full`}>
          {submitting ? "로그인 중…" : "로그인"}
        </button>
      </form>
      {status?.signup_enabled !== false && (
        <p className="text-center text-sm text-stone-600">
          아직 회원이 아니신가요?{" "}
          <Link href={withNext("/signup", next)} className={`${ui.link} font-medium`}>
            회원가입
          </Link>
        </p>
      )}
    </div>
  );
}
