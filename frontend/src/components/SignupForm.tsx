"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useId, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { AlreadyLoggedIn } from "@/components/LoginForm";
import { api, ApiError } from "@/lib/api";
import { safeNext, withNext } from "@/lib/safeNext";
import { ui } from "@/lib/ui";

type FieldKey = "username" | "nickname" | "password" | "confirm";
type Values = Record<FieldKey, string>;
type Errors = Partial<Record<FieldKey, string>>;

const FIELD_ORDER: FieldKey[] = ["username", "nickname", "password", "confirm"];
// 서버 오류 코드 → 고쳐야 할 칸 (오류가 나면 그 칸으로 커서를 옮긴다)
const SERVER_FIELD: Record<string, FieldKey> = {
  username_taken: "username",
  nickname_taken: "nickname",
  weak_password: "password",
};

/** 서버(Python)와 같은 기준으로 글자 수를 센다 (이모지 같은 문자도 한 글자) */
const charCount = (s: string) => Array.from(s).length;

/** 서버 검증(backend/app/schemas.py SignupIn)과 같은 규칙. 최종 판단은 서버가 한다. */
function validate(v: Values): Errors {
  const errors: Errors = {};
  const username = v.username.trim();
  const nickname = v.nickname.trim();

  if (!username) errors.username = "아이디를 입력해 주세요.";
  else if (!/^[a-z0-9_]+$/.test(username)) errors.username = "영문 소문자, 숫자, 밑줄(_)만 쓸 수 있어요.";
  else if (username.length < 4 || username.length > 20) errors.username = "아이디는 4~20자로 정해 주세요.";

  if (!nickname) errors.nickname = "닉네임을 입력해 주세요.";
  else if (/[\u0000-\u001f\u007f-\u009f]/.test(nickname)) errors.nickname = "닉네임에 쓸 수 없는 문자가 있어요.";
  else if (charCount(nickname) < 2 || charCount(nickname) > 20) errors.nickname = "닉네임은 2~20자로 정해 주세요.";

  if (!v.password) errors.password = "비밀번호를 입력해 주세요.";
  else if (charCount(v.password) < 8) errors.password = "비밀번호는 8자 이상이어야 해요.";
  else if (charCount(v.password) > 128) errors.password = "비밀번호는 128자 이하로 정해 주세요.";
  else if (username && v.password.toLowerCase() === username) errors.password = "비밀번호를 아이디와 다르게 정해 주세요.";

  if (!v.confirm) errors.confirm = "비밀번호를 한 번 더 입력해 주세요.";
  else if (v.confirm !== v.password) errors.confirm = "비밀번호가 서로 달라요. 다시 확인해 주세요.";

  return errors;
}

function Field({
  id,
  label,
  hint,
  error,
  ...input
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "id">) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={id} className={ui.label}>
        {label}
      </label>
      <input
        {...input}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={error ? ui.input.replace("border-stone-300", "border-red-400") : ui.input}
      />
      {error && (
        <p id={errorId} className="mt-1 text-sm text-red-700">
          {error}
        </p>
      )}
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-stone-500">
          {hint}
        </p>
      )}
    </div>
  );
}

export default function SignupForm() {
  const params = useSearchParams();
  const next = params.get("next");
  const { status, user } = useAuth();
  const uid = useId();
  const fieldId = (k: FieldKey) => `${uid}-${k}`;
  // 이벤트 처리 중에만 부른다 (렌더 중에는 DOM 을 건드리지 않는다)
  const focusField = (k: FieldKey) => document.getElementById(fieldId(k))?.focus();
  const [values, setValues] = useState<Values>({ username: "", nickname: "", password: "", confirm: "" });
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 로그인 상태를 확인하는 동안에는 폼을 띄우지 않는다 (가입을 받지 않는 경우 폼이 잠깐 보였다 사라지지 않게)
  if (!status) {
    return (
      <div className={ui.card}>
        <p role="status" className={ui.muted}>
          잠시만 기다려 주세요…
        </p>
      </div>
    );
  }
  if (user) return <AlreadyLoggedIn nickname={user.nickname} />;
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

  const errors = validate(values);
  const shown = (k: FieldKey) => ((touched[k] || submitted) && errors[k]) || undefined;

  const change = (k: FieldKey) => (e: React.ChangeEvent<HTMLInputElement>) => {
    // 아이디는 서버도 소문자로 저장하므로 입력할 때부터 소문자로 맞춘다
    const value = k === "username" ? e.target.value.toLowerCase() : e.target.value;
    setValues((prev) => ({ ...prev, [k]: value }));
    setError(null); // 고치기 시작하면 이전 서버 오류는 지운다
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
    setSubmitting(true);
    try {
      await api.signup(values.username.trim(), values.nickname.trim(), values.password);
      // 서버가 로그인 쿠키를 심어 준다. 전체 새로고침으로 이동해 모든 화면이 로그인 상태를 다시 읽게 한다
      window.location.assign(safeNext(next, window.location.origin));
    } catch (err) {
      setError(err instanceof ApiError ? err.messageKo : "회원가입하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
      setSubmitting(false);
      const field = err instanceof ApiError && err.code ? SERVER_FIELD[err.code] : undefined;
      if (field) focusField(field);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} noValidate className={`${ui.card} space-y-4`}>
        <p className="text-sm text-stone-600">
          회원가입은 무료예요. 가입하면 바로 로그인되고, 설계 내역 저장·커뮤니티·반려동물 정보 등록을 쓸 수 있어요.
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
          hint="커뮤니티에 보이는 이름이에요. 2~20자"
          error={shown("nickname")}
          name="nickname"
          autoComplete="nickname"
          required
          value={values.nickname}
          onChange={change("nickname")}
          onBlur={blur("nickname")}
        />
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
        {error && (
          <p role="alert" className={ui.error}>
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting} className={`${ui.btnPrimary} w-full`}>
          {submitting ? "가입하는 중…" : "가입하기"}
        </button>
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
