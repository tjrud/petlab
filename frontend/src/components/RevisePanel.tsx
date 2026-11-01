"use client";

import { useState } from "react";

const EXAMPLES = ["조금 더 크게 해 주세요", "환기구를 10개로 늘려 주세요", "오른쪽으로 옮겨 주세요"];

export default function RevisePanel({
  baseVersion,
  latestVersion,
  busy,
  error,
  onSubmit,
}: {
  baseVersion: number;
  latestVersion: number;
  busy: boolean;
  error: string | null;
  onSubmit: (prompt: string) => Promise<boolean>;
}) {
  const [prompt, setPrompt] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    const ok = await onSubmit(prompt.trim());
    if (ok) setPrompt("");
  }

  return (
    <form onSubmit={submit} aria-labelledby="revise-title" className="space-y-2">
      <h2 id="revise-title" className="font-bold">
        수정 요청
      </h2>
      {baseVersion !== latestVersion && (
        <p className="rounded-lg bg-sky-50 p-2 text-xs text-sky-900">
          지금 v{baseVersion}을 보고 있어요. 이 버전을 기준으로 수정하면 새 버전 v{latestVersion + 1}이 만들어지고, 기존
          버전은 그대로 남아요.
        </p>
      )}
      <textarea
        aria-label="수정할 내용"
        rows={3}
        maxLength={2000}
        placeholder="예: 은신처를 조금 더 크게, 환기구는 더 많이"
        className="w-full rounded-xl border border-stone-300 p-3 text-sm"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={busy}
      />
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((p) => (
          <button
            key={p}
            type="button"
            disabled={busy}
            onClick={() => setPrompt(p)}
            className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-200"
          >
            {p}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !prompt.trim()}
        className="w-full rounded-xl bg-stone-800 px-4 py-2.5 font-semibold text-white hover:bg-stone-900 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {busy ? "다시 설계하고 있어요…" : `v${baseVersion} 기준으로 다시 설계`}
      </button>
    </form>
  );
}
