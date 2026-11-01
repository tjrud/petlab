"use client";

import { useId, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { api, ApiError, isAuthError } from "@/lib/api";
import type { User } from "@/lib/types";
import { ui } from "@/lib/ui";

import { charCount, describedBy, FieldError, inputClass } from "./common";

type Key = "current" | "next" | "confirm";
type Values = Record<Key, string>;
type Errors = Partial<Record<Key, string>>;

const ORDER: Key[] = ["current", "next", "confirm"];

/** 서버 검증(PasswordChangeIn)과 같은 규칙. 최종 판단은 서버가 한다. */
function validate(v: Values, username: string): Errors {
  const errors: Errors = {};
  if (!v.current) errors.current = "지금 쓰는 비밀번호를 입력해 주세요.";
  if (!v.next) errors.next = "새 비밀번호를 입력해 주세요.";
  else if (charCount(v.next) < 8) errors.next = "비밀번호는 8자 이상이어야 해요.";
  else if (charCount(v.next) > 128) errors.next = "비밀번호는 128자 이하로 정해 주세요.";
  else if (v.next.toLowerCase() === username) errors.next = "비밀번호를 아이디와 다르게 정해 주세요.";
  else if (v.next === v.current) errors.next = "지금 쓰는 비밀번호와 다르게 정해 주세요.";
  if (!v.confirm) errors.confirm = "새 비밀번호를 한 번 더 입력해 주세요.";
  else if (v.confirm !== v.next) errors.confirm = "새 비밀번호가 서로 달라요. 다시 확인해 주세요.";
  return errors;
}

const FIELDS: { key: Key; label: string; autoComplete: string; hint?: string }[] = [
  { key: "current", label: "현재 비밀번호", autoComplete: "current-password" },
  { key: "next", label: "새 비밀번호", autoComplete: "new-password", hint: "8자 이상, 아이디와 다르게 정해 주세요" },
  { key: "confirm", label: "새 비밀번호 확인", autoComplete: "new-password" },
];

/** 비밀번호 변경 (바꾸면 다른 기기의 로그인은 풀리고 이 기기는 유지된다). 관리자는 서버 설정으로만 바꾼다. */
export default function PasswordForm({ user, onAuthError }: { user: User; onAuthError: (e: ApiError) => void }) {
  const { setStatus } = useAuth();
  const uid = useId();
  const fieldId = (k: Key) => `${uid}-${k}`;
  const [values, setValues] = useState<Values>({ current: "", next: "", confirm: "" });
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (user.role === "admin") {
    return (
      <div>
        <h3 className="font-semibold">비밀번호 바꾸기</h3>
        <p className="mt-1 text-sm text-stone-600">
          관리자 비밀번호는 서버 환경변수(ADMIN_PASSWORD)로 관리해서 여기서는 바꿀 수 없어요.
        </p>
      </div>
    );
  }

  const errors = submitted ? validate(values, user.username) : {};

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    setSubmitted(true);
    const firstInvalid = ORDER.find((k) => validate(values, user.username)[k]);
    if (firstInvalid) {
      document.getElementById(fieldId(firstInvalid))?.focus();
      return;
    }
    setSubmitting(true);
    try {
      const status = await api.changePassword(values.current, values.next);
      setStatus(status); // 이 기기는 새 로그인 쿠키로 그대로 로그인되어 있다
      setValues({ current: "", next: "", confirm: "" });
      setSubmitted(false);
      setDone(true);
    } catch (err) {
      if (isAuthError(err)) onAuthError(err as ApiError);
      else {
        setError(err instanceof ApiError ? err.messageKo : "비밀번호를 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.");
        if (err instanceof ApiError && err.code === "invalid_credentials") document.getElementById(fieldId("current"))?.focus();
        if (err instanceof ApiError && err.code === "weak_password") document.getElementById(fieldId("next"))?.focus();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-labelledby={`${uid}-title`} className="space-y-3">
      <h3 id={`${uid}-title`} className="font-semibold">
        비밀번호 바꾸기
      </h3>
      {/* 비밀번호 관리 프로그램이 어느 계정의 비밀번호인지 알 수 있게 아이디를 함께 둔다 */}
      <input type="text" name="username" autoComplete="username" value={user.username} readOnly hidden />
      {FIELDS.map((f) => {
        const err = errors[f.key];
        const id = fieldId(f.key);
        return (
          <div key={f.key}>
            <label htmlFor={id} className={ui.label}>
              {f.label}
            </label>
            <input
              id={id}
              type="password"
              autoComplete={f.autoComplete}
              required
              value={values[f.key]}
              onChange={(e) => {
                setValues((prev) => ({ ...prev, [f.key]: e.target.value }));
                setError(null);
                setDone(false);
              }}
              aria-invalid={err ? true : undefined}
              aria-describedby={describedBy(err && `${id}-error`, f.hint && `${id}-hint`)}
              className={inputClass(!!err)}
            />
            <FieldError id={`${id}-error`} message={err} />
            {f.hint && (
              <p id={`${id}-hint`} className="mt-1 text-xs text-stone-500">
                {f.hint}
              </p>
            )}
          </div>
        );
      })}
      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      {done && (
        <p role="status" className={ui.success}>
          비밀번호를 바꿨어요. 이 기기는 그대로 로그인되어 있고, 다른 기기에서는 로그아웃됐어요.
        </p>
      )}
      <button type="submit" disabled={submitting} className={ui.btnSecondary}>
        {submitting ? "바꾸는 중…" : "비밀번호 변경"}
      </button>
    </form>
  );
}
