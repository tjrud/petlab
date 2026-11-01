"use client";

import { useId, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { api, ApiError, isAuthError } from "@/lib/api";
import { NICKNAME_HINT, nicknameError, normalizeNickname } from "@/lib/nickname";
import type { User } from "@/lib/types";
import { ui } from "@/lib/ui";

import { describedBy, FieldError, inputClass } from "./common";

/** 서버 검증(ProfileUpdateIn)과 같은 규칙. 최종 판단은 서버가 한다. */
function validateNickname(value: string, current: string): string | undefined {
  const problem = nicknameError(value);
  if (problem) return problem;
  if (normalizeNickname(value) === current) return "지금 쓰고 있는 닉네임과 같아요.";
  return undefined;
}

/** 닉네임 변경 (관리자는 바꿀 수 없다) */
export default function NicknameForm({ user, onAuthError }: { user: User; onAuthError: (e: ApiError) => void }) {
  const { setStatus } = useAuth();
  const uid = useId();
  const inputId = `${uid}-nickname`;
  const [value, setValue] = useState(user.nickname);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (user.role === "admin") {
    return (
      <div>
        <h3 className="font-semibold">닉네임 바꾸기</h3>
        <p className="mt-1 text-sm text-stone-600">관리자 닉네임은 바꿀 수 없어요.</p>
      </div>
    );
  }

  const fieldError = submitted ? validateNickname(value, user.nickname) : undefined;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(null);
    setSubmitted(true);
    if (validateNickname(value, user.nickname)) {
      document.getElementById(inputId)?.focus();
      return;
    }
    setSubmitting(true);
    try {
      const status = await api.updateProfile(value.trim());
      setStatus(status); // 헤더의 닉네임도 바로 바뀐다
      setValue(status.user?.nickname ?? value.trim());
      setSubmitted(false);
      setDone("닉네임을 바꿨어요.");
    } catch (err) {
      if (isAuthError(err)) onAuthError(err as ApiError);
      else setError(err instanceof ApiError ? err.messageKo : "닉네임을 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-labelledby={`${uid}-title`} className="space-y-3">
      <h3 id={`${uid}-title`} className="font-semibold">
        닉네임 바꾸기
      </h3>
      <div>
        <label htmlFor={inputId} className={ui.label}>
          닉네임
        </label>
        <input
          id={inputId}
          name="nickname"
          autoComplete="nickname"
          required
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
            setDone(null);
          }}
          aria-invalid={fieldError ? true : undefined}
          aria-describedby={describedBy(fieldError && `${uid}-error`, `${uid}-hint`)}
          className={inputClass(!!fieldError)}
        />
        <FieldError id={`${uid}-error`} message={fieldError} />
        <p id={`${uid}-hint`} className="mt-1 text-xs text-stone-500">
          {NICKNAME_HINT}
        </p>
      </div>
      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      {done && (
        <p role="status" className={ui.success}>
          {done}
        </p>
      )}
      <button type="submit" disabled={submitting} className={ui.btnSecondary}>
        {submitting ? "바꾸는 중…" : "닉네임 변경"}
      </button>
    </form>
  );
}
