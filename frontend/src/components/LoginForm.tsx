"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";

/** 로그인 후 돌아갈 경로. 같은 출처의 경로만 허용한다 (외부 주소로 보내는 open redirect 방지).
 *  브라우저는 경로 안의 역슬래시·탭·줄바꿈을 정규화해 "/\\evil.com" 같은 값을 외부 주소로 해석하므로,
 *  접두사 검사 대신 실제 URL 로 해석해 출처를 비교하고, 돌려줄 값도 다시 확인한다. */
export function safeNext(raw: string | null, origin: string): string {
  if (!raw || !raw.startsWith("/") || /[\\\u0000-\u001f\u007f]/.test(raw)) return "/";
  let url: URL;
  try {
    url = new URL(raw, origin);
  } catch {
    return "/";
  }
  // "/..//evil.com" 처럼 점 세그먼트가 접히면 경로가 "//evil.com" 이 되어 다른 사이트 주소로 해석된다.
  // 실제로 돌려줄 값을 다시 검사한다.
  const out = url.pathname + url.search + url.hash;
  if (url.origin !== origin || url.pathname.startsWith("//") || url.pathname.startsWith("/login")) return "/";
  if (new URL(out, origin).origin !== origin) return "/";
  return out;
}

export default function LoginForm() {
  const params = useSearchParams();
  const [username, setUsername] = useState("");
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
      window.location.assign(safeNext(params.get("next"), window.location.origin));
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
