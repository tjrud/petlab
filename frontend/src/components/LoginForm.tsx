"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";

/** 내부 경로만 허용 (외부 주소로 보내는 open redirect 방지) */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/";
  return raw;
}

export default function LoginForm() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.login(username.trim(), password);
      // 전체 새로고침으로 이동해 헤더 등 모든 화면이 로그인 상태를 다시 읽게 한다
      window.location.assign(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.messageKo : "로그인하지 못했어요.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-amber-200 bg-white p-6">
      <p className="text-sm text-stone-600">설계 기능은 관리자만 사용할 수 있어요. 관리자 계정으로 로그인해 주세요.</p>
      <label className="block">
        <span className="mb-1 block text-sm font-medium">아이디</span>
        <input
          autoComplete="username"
          required
          className="w-full rounded-lg border border-stone-300 px-3 py-2"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-medium">비밀번호</span>
        <input
          type="password"
          autoComplete="current-password"
          required
          className="w-full rounded-lg border border-stone-300 px-3 py-2"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600 disabled:bg-amber-300"
      >
        {submitting ? "로그인 중…" : "로그인"}
      </button>
    </form>
  );
}
