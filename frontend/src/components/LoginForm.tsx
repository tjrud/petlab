"use client";

import { Link, useHref, useT } from "@/i18n/client";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth, useAuthRecheck, useLogout } from "@/components/AuthProvider";
import { AuthChecking } from "@/components/LoginRequired";
import { api, errorText } from "@/lib/api";
import { safeNext, withNext } from "@/lib/safeNext";
import { ui } from "@/lib/ui";

/** 서버에 닿지 못해 로그인 상태를 확인하지 못했을 때. 로그아웃·가입 마감으로 오해하지 않게 연결 문제라고 알린다 */
export function ServerUnreachable() {
  const { refresh } = useAuth();
  const t = useT();
  const [retrying, setRetrying] = useState(false);
  return (
    <div role="alert" className={`${ui.error} flex flex-wrap items-center justify-between gap-2`}>
      <span>{t("서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.")}</span>
      <button
        type="button"
        disabled={retrying}
        onClick={async () => {
          setRetrying(true);
          await refresh();
          setRetrying(false);
        }}
        className="font-semibold underline underline-offset-2 disabled:opacity-50"
      >
        {retrying ? t("확인 중…") : t("다시 시도")}
      </button>
    </div>
  );
}

/** 이미 로그인한 사람이 로그인·회원가입 화면에 들어왔을 때 폼 대신 보여 준다 */
export function AlreadyLoggedIn({ nickname }: { nickname: string }) {
  const { logout, busy, error } = useLogout();
  const t = useT();
  // 닉네임 자리에 굵은 글씨를 넣으려고 번역문을 {name} 에서 나눈다
  const [before, after] = t("{name}님으로 로그인한 상태예요. 다른 계정으로 로그인하려면 먼저 로그아웃해 주세요.").split("{name}");
  return (
    <div role="status" className={`${ui.card} text-center`}>
      <h2 className={ui.h2}>{t("이미 로그인했어요")}</h2>
      <p className="mt-2 break-words text-sm text-stone-600">
        {before}
        <span className="font-medium text-stone-800">{nickname}</span>
        {after}
      </p>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-center">
        <Link href="/" className={ui.btnPrimary}>
          {t("메인 화면으로")}
        </Link>
        <Link href="/me" className={ui.btnSecondary}>
          {t("내 정보 보기")}
        </Link>
        <button type="button" onClick={logout} disabled={busy} className={ui.btnSecondary}>
          {busy ? t("로그아웃하는 중…") : t("로그아웃")}
        </button>
      </div>
      {error && (
        <p role="alert" className={`${ui.error} mt-4`}>
          {error}
        </p>
      )}
    </div>
  );
}

export default function LoginForm() {
  const params = useSearchParams();
  const next = params.get("next");
  const t = useT();
  const href = useHref();
  const { status, user, unreachable } = useAuth();
  // 저장해 둔 로그인 상태는 오래됐을 수 있다 (세션 만료 등). 들어올 때마다 서버에 다시 묻는다
  const recheck = useAuthRecheck();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user && recheck === "checking") return <AuthChecking />;
  // 서버에 닿지 못해 확인하지 못했으면 폼을 보여 준다 (다시 로그인해도 문제없다)
  if (user && recheck === "ok") return <AlreadyLoggedIn nickname={user.nickname} />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // 회원 아이디는 서버가 소문자로 맞춘다 (관리자 아이디는 대소문자를 그대로 비교하므로 여기서 바꾸지 않는다)
      await api.login(username.trim(), password);
      // 전체 새로고침으로 이동해 헤더 등 모든 화면이 로그인 상태를 다시 읽게 한다
      window.location.assign(href(safeNext(next, window.location.origin)));
    } catch (err) {
      setError(errorText(err, t("로그인하지 못했어요.")));
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      {unreachable && <ServerUnreachable />}
      <form onSubmit={submit} className={`${ui.card} space-y-4`}>
        <p className="text-sm text-stone-600">
          {t("로그인하면 설계를 만들고, 설계 내역을 보고, 커뮤니티에 글을 쓸 수 있어요.")}
        </p>
        <div>
          <label htmlFor="login-username" className={ui.label}>
            {t("아이디")}
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
            {t("비밀번호")}
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
          {submitting ? t("로그인 중…") : t("로그인")}
        </button>
      </form>
      {status?.signup_enabled !== false && (
        <p className="text-center text-sm text-stone-600">
          {t("아직 회원이 아니신가요?")}{" "}
          <Link href={withNext("/signup", next)} className={`${ui.link} font-medium`}>
            {t("회원가입")}
          </Link>
        </p>
      )}
    </div>
  );
}
