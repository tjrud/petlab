"use client";

import { useId, useLayoutEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ResendVerification } from "@/components/EmailVerification";
import { api, ApiError, errorText, isAuthError } from "@/lib/api";
import { isPlausibleEmail } from "@/lib/email";
import type { User } from "@/lib/types";
import { ui } from "@/lib/ui";

import { Field } from "./common";

type Key = "email" | "password";
type Errors = Partial<Record<Key, string>>;

function validate(email: string, password: string, current: string | null): Errors {
  const errors: Errors = {};
  const v = email.trim();
  if (!v) errors.email = "새 이메일 주소를 입력해 주세요.";
  else if (!isPlausibleEmail(v)) errors.email = "이메일 주소를 확인해 주세요.";
  else if (current && v.toLowerCase() === current.toLowerCase()) errors.email = "지금 쓰고 있는 이메일과 같아요.";
  if (!password) errors.password = "본인 확인을 위해 지금 쓰는 비밀번호를 입력해 주세요.";
  return errors;
}

/**
 * 이메일: 주소와 인증 상태, 인증 메일 다시 보내기, 주소 바꾸기(지금 쓰는 비밀번호로 본인 확인).
 * 관리자에게는 보이지 않는다. 비밀번호는 저장하거나 맡겨 두지 않고, 화면을 떠나면 지운다.
 */
export default function EmailForm({ user, onAuthError }: { user: User; onAuthError: (e: ApiError) => void }) {
  const { status, setStatus } = useAuth();
  const verificationOn = !!status?.email_verification;
  const uid = useId();
  const fieldId = (k: Key) => `${uid}-${k}`;
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // 이 화면이 숨겨지면(다른 화면으로 이동) 입력한 비밀번호를 지운다
  useLayoutEffect(
    () => () => {
      setPassword("");
    },
    [],
  );

  if (user.role === "admin") return null;
  // 이메일 인증을 쓰지 않고 등록한 주소도 없으면 보여 줄 것이 없다
  if (!verificationOn && !user.email) return null;

  const showForm = open || !user.email;
  const errors = submitted ? validate(email, password, user.email) : {};

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(null);
    setSubmitted(true);
    const problems = validate(email, password, user.email);
    const first = (["email", "password"] as const).find((k) => problems[k]);
    if (first) {
      document.getElementById(fieldId(first))?.focus();
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.changeEmail(email.trim(), password);
      const { verification_email_sent: sent, ...auth } = res;
      setStatus(auth); // 헤더의 안내 띠와 인증 상태도 바로 바뀐다
      const addr = auth.user?.email ?? email.trim();
      setDone(
        sent === true
          ? `새 주소로 인증 메일을 보냈어요 (${addr}). 메일의 링크를 눌러 인증을 마쳐 주세요.`
          : sent === false
            ? "이메일을 바꿨지만 인증 메일을 보내지 못했어요. 잠시 뒤 인증 메일을 다시 보내 주세요."
            : "이메일을 바꿨어요.",
      );
      setEmail("");
      setPassword("");
      setSubmitted(false);
      setOpen(false);
    } catch (err) {
      if (isAuthError(err)) {
        onAuthError(err);
        return;
      }
      const code = err instanceof ApiError ? err.code : undefined;
      if (code === "validation_error") setError("이메일 주소를 확인해 주세요.");
      else setError(errorText(err, "이메일을 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요."));
      if (code === "invalid_credentials") {
        setPassword("");
        document.getElementById(fieldId("password"))?.focus();
      } else if (code === "email_taken" || code === "validation_error") {
        document.getElementById(fieldId("email"))?.focus();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div id="email" aria-labelledby={`${uid}-title`} role="group" className="scroll-mt-32 space-y-3">
      <h3 id={`${uid}-title`} className="font-semibold">
        이메일
      </h3>
      {user.email ? (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="break-all font-medium text-stone-800">{user.email}</span>
          {verificationOn &&
            (user.email_verified ? (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">인증됨</span>
            ) : (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">인증 전</span>
            ))}
        </p>
      ) : (
        <p className="text-sm text-stone-600">
          아직 등록한 이메일이 없어요. 이메일을 등록하고 인증하면 설계·글쓰기·댓글을 쓸 수 있어요.
        </p>
      )}
      {verificationOn && user.email && !user.email_verified && (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">
          <p>메일함에서 인증 링크를 눌러 주세요. 메일이 없다면 다시 보낼 수 있어요.</p>
          <ResendVerification className="mt-1" />
        </div>
      )}
      {done && (
        <p role="status" className={ui.success}>
          {done}
        </p>
      )}

      {showForm ? (
        <form onSubmit={submit} noValidate aria-label={user.email ? "이메일 바꾸기" : "이메일 등록"} className="space-y-3">
          {/* 비밀번호 관리 프로그램이 어느 계정의 비밀번호인지 알 수 있게 아이디를 함께 둔다 */}
          <input type="text" name="username" autoComplete="username" value={user.username} readOnly hidden />
          <Field
            id={fieldId("email")}
            label={user.email ? "새 이메일" : "이메일"}
            hint={verificationOn ? "새 주소로 인증 메일을 보내요. 인증을 마칠 때까지는 인증 전 상태가 돼요." : undefined}
            error={errors.email}
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setError(null);
              setDone(null);
            }}
          />
          <Field
            id={fieldId("password")}
            label="비밀번호 (본인 확인)"
            error={errors.password}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError(null);
            }}
          />
          {error && (
            <p role="alert" className={ui.error}>
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={submitting} className={ui.btnSecondary}>
              {submitting ? "바꾸는 중…" : user.email ? "이메일 변경" : "이메일 등록"}
            </button>
            {user.email && (
              <button
                type="button"
                disabled={submitting}
                className={ui.btnSecondary}
                onClick={() => {
                  setOpen(false);
                  setEmail("");
                  setPassword("");
                  setSubmitted(false);
                  setError(null);
                }}
              >
                취소
              </button>
            )}
          </div>
        </form>
      ) : (
        <button
          type="button"
          className={ui.btnSecondary}
          onClick={() => {
            setOpen(true);
            setDone(null);
          }}
        >
          이메일 바꾸기
        </button>
      )}
    </div>
  );
}
