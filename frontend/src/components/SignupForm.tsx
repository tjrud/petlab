"use client";

import { Link } from "@/i18n/client";
import { useSearchParams } from "next/navigation";
import { useId, useRef, useState } from "react";

import { useAuth, useAuthRecheck } from "@/components/AuthProvider";
import { AlreadyLoggedIn, ServerUnreachable } from "@/components/LoginForm";
import { AuthChecking } from "@/components/LoginRequired";
import { Field, passwordRuleError } from "@/components/me/common";
import Turnstile, { type TurnstileHandle } from "@/components/Turnstile";
import { api, ApiError, errorText } from "@/lib/api";
import { isPlausibleEmail } from "@/lib/email";
import { NICKNAME_HINT, nicknameError } from "@/lib/nickname";
import { safeNext, withNext } from "@/lib/safeNext";
import { ui } from "@/lib/ui";

type FieldKey = "username" | "nickname" | "email" | "password" | "confirm";
type Values = Record<FieldKey, string>;
type Errors = Partial<Record<FieldKey, string>>;

const FIELD_ORDER: FieldKey[] = ["username", "nickname", "email", "password", "confirm"];
// 서버 오류 코드 → 고쳐야 할 칸 (오류가 나면 그 칸으로 커서를 옮긴다)
const SERVER_FIELD: Record<string, FieldKey> = {
  username_taken: "username",
  nickname_taken: "nickname",
  email_taken: "email",
  email_required: "email",
  weak_password: "password",
};

/** 서버의 입력 검사(422)가 칸을 짚었을 때 보여 줄 문구 */
const FIELD_MESSAGE: Record<Exclude<FieldKey, "confirm">, string> = {
  username: "아이디를 확인해 주세요.",
  nickname: "닉네임을 확인해 주세요.",
  email: "이메일 주소를 확인해 주세요.",
  password: "비밀번호를 확인해 주세요.",
};

/** 422 응답의 errors([{ loc: ["body", "email"], msg }])에서 칸별 오류를 뽑는다 */
function fieldErrorsFrom422(details: unknown): Errors {
  const out: Errors = {};
  if (!Array.isArray(details)) return out;
  for (const item of details) {
    const { loc, msg } = (item ?? {}) as { loc?: unknown; msg?: unknown };
    const key = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
    if (typeof key !== "string" || !(key in FIELD_MESSAGE)) continue;
    const field = key as keyof typeof FIELD_MESSAGE;
    if (out[field]) continue;
    // 서버가 한국어로 설명하면(닉네임 규칙 등) 그대로 보여 준다. 이메일 형식 설명은 영어라 우리 문구를 쓴다
    const text = typeof msg === "string" ? msg.replace(/^Value error,\s*/, "") : "";
    out[field] = field !== "email" && /[가-힣]/.test(text) ? text : FIELD_MESSAGE[field];
  }
  return out;
}

/** 서버 검증(backend/app/schemas.py SignupIn)과 같은 규칙. 최종 판단은 서버가 한다. */
function validate(v: Values, needEmail: boolean): Errors {
  const errors: Errors = {};
  const username = v.username.trim();
  const email = v.email.trim();

  if (!username) errors.username = "아이디를 입력해 주세요.";
  else if (!/^[a-z0-9_]+$/.test(username)) errors.username = "영문 소문자, 숫자, 밑줄(_)만 쓸 수 있어요.";
  else if (username.length < 4 || username.length > 20) errors.username = "아이디는 4~20자로 정해 주세요.";

  const nicknameProblem = nicknameError(v.nickname);
  if (nicknameProblem) errors.nickname = nicknameProblem;

  if (needEmail) {
    if (!email) errors.email = "이메일을 입력해 주세요.";
    else if (!isPlausibleEmail(email)) errors.email = "이메일 주소를 확인해 주세요.";
  }

  if (!v.password) errors.password = "비밀번호를 입력해 주세요.";
  else {
    const p = passwordRuleError(v.password, username);
    if (p) errors.password = p;
  }

  if (!v.confirm) errors.confirm = "비밀번호를 한 번 더 입력해 주세요.";
  else if (v.confirm !== v.password) errors.confirm = "비밀번호가 서로 달라요. 다시 확인해 주세요.";

  return errors;
}

/** 가입을 마친 뒤: 인증 메일을 보냈는지 알려 주고, 원래 가려던 화면으로 이어 간다 */
function SignupDone({ email, sent, next }: { email: string; sent: boolean; next: string | null }) {
  // 전체 새로고침으로 이동해 숨김 상태로 남은 화면까지 로그인 상태를 다시 읽게 한다
  const go = (path: string) => window.location.assign(path);
  return (
    <div role="status" className={`${ui.card} text-center`}>
      <h2 className={`${ui.h2} mt-2`}>{sent ? "인증 메일을 보냈어요" : "가입을 마쳤어요"}</h2>
      {sent ? (
        <p className="mt-2 text-sm text-stone-600">
          <span className="break-all font-medium text-stone-800">{email}</span> 주소로 보낸 메일의 링크를 누르면 인증이
          끝나요. 가입은 끝났고 바로 로그인되었어요. 인증 전에도 둘러보기와 반려동물 등록은 할 수 있고, 설계·글쓰기·댓글은 인증
          뒤에 쓸 수 있어요.
        </p>
      ) : (
        <p className="mt-2 text-sm text-stone-600">
          바로 로그인되었지만 인증 메일을 보내지 못했어요. 잠시 뒤 내 정보에서 인증 메일을 다시 보내 주세요. 인증을
          마쳐야 설계·글쓰기·댓글을 쓸 수 있어요.
        </p>
      )}
      <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-center">
        <button type="button" className={ui.btnPrimary} onClick={() => go(safeNext(next, window.location.origin))}>
          계속하기
        </button>
        {!sent && (
          <button type="button" className={ui.btnSecondary} onClick={() => go("/me#email")}>
            내 정보로 가기
          </button>
        )}
      </div>
    </div>
  );
}

export default function SignupForm() {
  const params = useSearchParams();
  const next = params.get("next");
  const { status, user, unreachable, setStatus } = useAuth();
  // 저장해 둔 로그인 상태는 오래됐을 수 있다 (세션 만료 등). 들어올 때마다 서버에 다시 묻는다
  const recheck = useAuthRecheck();
  const uid = useId();
  const fieldId = (k: FieldKey) => `${uid}-${k}`;
  // 이벤트 처리 중에만 부른다 (렌더 중에는 DOM 을 건드리지 않는다)
  const focusField = (k: FieldKey) => document.getElementById(fieldId(k))?.focus();
  const [values, setValues] = useState<Values>({ username: "", nickname: "", email: "", password: "", confirm: "" });
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 서버가 짚은 칸별 오류 (그 칸을 고치면 지운다) */
  const [serverErrors, setServerErrors] = useState<Errors>({});
  /** 보안 확인 토큰 (한 번만 쓸 수 있다) */
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const turnstile = useRef<TurnstileHandle>(null);
  /** 가입을 마쳤고 인증 메일 결과를 보여 주는 중 */
  const [done, setDone] = useState<{ email: string; sent: boolean } | null>(null);

  if (done) return <SignupDone email={done.email} sent={done.sent} next={next} />;
  // 로그인 상태를 확인하는 동안에는 폼을 띄우지 않는다 (가입을 받지 않는 경우 폼이 잠깐 보였다 사라지지 않게).
  // 서버에 닿지 못했으면 "가입을 받지 않아요" 대신 연결 문제라고 알린다 (다시 연결되면 폼이 보인다)
  if (!status) return unreachable ? <ServerUnreachable /> : <AuthChecking />;
  if (user && recheck === "checking") return <AuthChecking />;
  if (user && recheck === "ok") return <AlreadyLoggedIn nickname={user.nickname} />;
  if (!status.signup_enabled) {
    return (
      <div role="status" className={`${ui.card} text-center`}>
        <h2 className={ui.h2}>지금은 회원가입을 받지 않아요</h2>
        <p className="mt-2 text-sm text-stone-600">
          회원가입이 잠시 닫혀 있어요. 이미 계정이 있다면 로그인해 주세요.
        </p>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-center">
          <Link href={withNext("/login", next)} className={ui.btnPrimary}>
            로그인하러 가기
          </Link>
          <Link href="/" className={ui.btnSecondary}>
            메인 화면으로
          </Link>
        </div>
      </div>
    );
  }

  const needEmail = status.email_verification;
  const captcha = status.captcha;
  const errors = validate(values, needEmail);
  const shown = (k: FieldKey) => ((touched[k] || submitted) && errors[k]) || serverErrors[k] || undefined;

  const change = (k: FieldKey) => (e: React.ChangeEvent<HTMLInputElement>) => {
    // 아이디는 서버도 소문자로 저장하므로 입력할 때부터 소문자로 맞춘다
    const value = k === "username" ? e.target.value.toLowerCase() : e.target.value;
    setValues((prev) => ({ ...prev, [k]: value }));
    setError(null); // 고치기 시작하면 이전 서버 오류는 지운다
    setServerErrors((prev) => (prev[k] ? { ...prev, [k]: undefined } : prev));
  };
  const blur = (k: FieldKey) => () => {
    // 비어 있는 칸을 그냥 지나간 경우에는 아직 오류를 보여 주지 않는다
    if (values[k]) setTouched((prev) => ({ ...prev, [k]: true }));
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitted(true);
    const firstInvalid = FIELD_ORDER.find((k) => errors[k]);
    if (firstInvalid) {
      focusField(firstInvalid);
      return;
    }
    if (captcha && !captchaToken) {
      setError("보안 확인을 먼저 마쳐 주세요.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.signup({
        username: values.username.trim(),
        nickname: values.nickname.trim(),
        password: values.password,
        ...(needEmail ? { email: values.email.trim() } : {}),
        ...(captcha && captchaToken ? { captcha_token: captchaToken } : {}),
      });
      // 서버가 로그인 쿠키를 심어 준다
      const { verification_email_sent: sent, ...auth } = res;
      if (sent === true || sent === false) {
        // 인증 메일 결과를 먼저 알려 준다 (헤더도 바로 로그인 상태로)
        setDone({ email: auth.user?.email ?? values.email.trim(), sent });
        setStatus(auth);
        return;
      }
      // 이메일 인증을 쓰지 않으면 바로 이동한다. 전체 새로고침으로 모든 화면이 로그인 상태를 다시 읽게 한다
      window.location.assign(safeNext(next, window.location.origin));
    } catch (err) {
      setSubmitting(false);
      // 입력 검사(422)는 서버가 보안 확인보다 먼저 거절한 것이라 토큰을 쓰지 않았다
      const invalidInput = err instanceof ApiError && err.code === "validation_error";
      const fieldErrors = invalidInput ? fieldErrorsFrom422(err.details) : {};
      const badField = FIELD_ORDER.find((k) => fieldErrors[k]);
      if (badField) {
        setServerErrors(fieldErrors); // 칸 아래에 보여 주고 그 칸으로 옮긴다
      } else {
        setError(errorText(err, "회원가입하지 못했어요. 잠시 뒤 다시 시도해 주세요."));
      }
      // 그 밖의 거절은 토큰을 이미 썼을 수 있다 (한 번만 쓸 수 있으므로 새로 풀게 한다)
      if (captcha && !invalidInput) {
        turnstile.current?.reset();
        setCaptchaToken(null);
      }
      const field = badField ?? (err instanceof ApiError && err.code ? SERVER_FIELD[err.code] : undefined);
      if (field) focusField(field);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} noValidate className={`${ui.card} space-y-4`}>
        <p className="text-sm text-stone-600">
          {needEmail
            ? "회원가입은 무료예요. 가입하면 바로 로그인되고, 이메일 인증을 마치면 설계 내역 저장·커뮤니티를 쓸 수 있어요."
            : "회원가입은 무료예요. 가입하면 바로 로그인되고, 설계 내역 저장·커뮤니티·반려동물 정보 등록을 쓸 수 있어요."}
        </p>
        <Field
          id={fieldId("username")}
          label="아이디"
          hint="영문 소문자·숫자·밑줄(_) 4~20자"
          error={shown("username")}
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
          value={values.username}
          onChange={change("username")}
          onBlur={blur("username")}
        />
        <Field
          id={fieldId("nickname")}
          label="닉네임"
          hint={NICKNAME_HINT}
          error={shown("nickname")}
          name="nickname"
          autoComplete="nickname"
          required
          value={values.nickname}
          onChange={change("nickname")}
          onBlur={blur("nickname")}
        />
        {needEmail && (
          <Field
            id={fieldId("email")}
            label="이메일"
            hint="가입하면 이 주소로 인증 메일을 보내요. 인증을 마치면 설계·글쓰기·댓글을 쓸 수 있어요."
            error={shown("email")}
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={values.email}
            onChange={change("email")}
            onBlur={blur("email")}
          />
        )}
        <Field
          id={fieldId("password")}
          label="비밀번호"
          hint="8자 이상, 아이디와 다르게 정해 주세요"
          error={shown("password")}
          name="new-password"
          type="password"
          autoComplete="new-password"
          required
          value={values.password}
          onChange={change("password")}
          onBlur={blur("password")}
        />
        <Field
          id={fieldId("confirm")}
          label="비밀번호 확인"
          error={shown("confirm")}
          name="confirm-password"
          type="password"
          autoComplete="new-password"
          required
          value={values.confirm}
          onChange={change("confirm")}
          onBlur={blur("confirm")}
        />
        {captcha && (
          <div>
            <p className={ui.label}>보안 확인</p>
            <Turnstile ref={turnstile} siteKey={captcha.site_key} onToken={setCaptchaToken} />
          </div>
        )}
        {error && (
          <p role="alert" className={ui.error}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting || (!!captcha && !captchaToken)}
          className={`${ui.btnPrimary} w-full`}
        >
          {submitting ? "가입하는 중…" : "가입하기"}
        </button>
        {captcha && !captchaToken && !submitting && (
          <p className="text-center text-xs text-stone-500">보안 확인을 마치면 가입할 수 있어요.</p>
        )}
      </form>
      <p className="text-center text-sm text-stone-600">
        이미 회원이신가요?{" "}
        <Link href={withNext("/login", next)} className={`${ui.link} font-medium`}>
          로그인
        </Link>
      </p>
    </div>
  );
}
