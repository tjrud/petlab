"use client";

import { useId, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { api, ApiError, errorText, isAuthError } from "@/lib/api";
import type { User } from "@/lib/types";
import { ui } from "@/lib/ui";

import { Field, passwordRuleError } from "./common";

type Key = "current" | "next" | "confirm";
type Values = Record<Key, string>;
type Errors = Partial<Record<Key, string>>;

const ORDER: Key[] = ["current", "next", "confirm"];

/** 서버 검증(PasswordChangeIn)과 같은 규칙. 최종 판단은 서버가 한다. */
function validate(v: Values, username: string, t: TFunction): Errors {
  const errors: Errors = {};
  if (!v.current) errors.current = t("지금 쓰는 비밀번호를 입력해 주세요.");
  if (!v.next) errors.next = t("새 비밀번호를 입력해 주세요.");
  else {
    // 공통 규칙(길이·아이디)에 걸리지 않을 때만 지금 비밀번호와 같은지 본다
    const p = passwordRuleError(v.next, username);
    if (p) errors.next = t(p);
    else if (v.next === v.current) errors.next = t("지금 쓰는 비밀번호와 다르게 정해 주세요.");
  }
  if (!v.confirm) errors.confirm = t("새 비밀번호를 한 번 더 입력해 주세요.");
  else if (v.confirm !== v.next) errors.confirm = t("새 비밀번호가 서로 달라요. 다시 확인해 주세요.");
  return errors;
}

// 라벨·안내는 한국어 원문. 보여 줄 때 t(문구) 로 번역한다
const FIELDS: { key: Key; label: string; autoComplete: string; hint?: string }[] = [
  { key: "current", label: "현재 비밀번호", autoComplete: "current-password" },
  { key: "next", label: "새 비밀번호", autoComplete: "new-password", hint: "8자 이상, 아이디와 다르게 정해 주세요" },
  { key: "confirm", label: "새 비밀번호 확인", autoComplete: "new-password" },
];

/** 비밀번호 변경 (바꾸면 다른 기기의 로그인은 풀리고 이 기기는 유지된다). 관리자는 서버 설정으로만 바꾼다. */
export default function PasswordForm({ user, onAuthError }: { user: User; onAuthError: (e: ApiError) => void }) {
  const { setStatus } = useAuth();
  const t = useT();
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
        <h3 className="font-semibold">{t("비밀번호 바꾸기")}</h3>
        <p className="mt-1 text-sm text-stone-600">
          {t("관리자 비밀번호는 서버 환경변수(ADMIN_PASSWORD)로 관리해서 여기서는 바꿀 수 없어요.")}
        </p>
      </div>
    );
  }

  const errors = submitted ? validate(values, user.username, t) : {};

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    setSubmitted(true);
    const firstInvalid = ORDER.find((k) => validate(values, user.username, t)[k]);
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
      if (isAuthError(err)) onAuthError(err);
      else {
        setError(errorText(err, t("비밀번호를 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.")));
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
        {t("비밀번호 바꾸기")}
      </h3>
      {/* 비밀번호 관리 프로그램이 어느 계정의 비밀번호인지 알 수 있게 아이디를 함께 둔다 */}
      <input type="text" name="username" autoComplete="username" value={user.username} readOnly hidden />
      {FIELDS.map((f) => {
        const err = errors[f.key];
        const id = fieldId(f.key);
        return (
          <Field
            key={f.key}
            id={id}
            label={t(f.label)}
            hint={f.hint && t(f.hint)}
            error={err}
            type="password"
            autoComplete={f.autoComplete}
            required
            value={values[f.key]}
            onChange={(e) => {
              setValues((prev) => ({ ...prev, [f.key]: e.target.value }));
              setError(null);
              setDone(false);
            }}
          />
        );
      })}
      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      {done && (
        <p role="status" className={ui.success}>
          {t("비밀번호를 바꿨어요. 이 기기는 그대로 로그인되어 있고, 다른 기기에서는 로그아웃됐어요.")}
        </p>
      )}
      <button type="submit" disabled={submitting} className={ui.btnSecondary}>
        {submitting ? t("바꾸는 중…") : t("비밀번호 변경")}
      </button>
    </form>
  );
}
