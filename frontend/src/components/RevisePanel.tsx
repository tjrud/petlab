"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { clearDraft, ReloginNotice, useDraftBackup } from "@/components/DraftRelogin";

const EXAMPLES = ["조금 더 크게 해 주세요", "환기구를 10개로 늘려 주세요", "오른쪽으로 옮겨 주세요"];

export default function RevisePanel({
  baseVersion,
  latestVersion,
  sharedVersions,
  busy,
  error,
  needsLogin,
  draftKey,
  loginNext,
  onSubmit,
}: {
  baseVersion: number;
  latestVersion: number;
  /** 커뮤니티 글에 첨부된 버전 (다른 사람은 이 버전만 볼 수 있다) */
  sharedVersions: number[];
  busy: boolean;
  error: string | null;
  /** 수정 요청이 로그인 문제로 실패했다 */
  needsLogin: boolean;
  /** 로그인이 풀린 동안 쓴 요청을 맡겨 둘 이름 (설계마다 다르게) */
  draftKey: string;
  /** 다시 로그인한 뒤 돌아올 주소 */
  loginNext: string;
  onSubmit: (prompt: string) => Promise<boolean>;
}) {
  const { status, user } = useAuth();
  const [prompt, setPrompt] = useState("");
  const relogin = needsLogin || (status !== null && !user);
  // 쓴 요청은 맡겨 두었다가 다시 로그인하고 돌아오면 되살린다
  useDraftBackup<{ prompt: string }>(draftKey, prompt.trim() ? { prompt } : null, relogin, (d) => setPrompt(d.prompt));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    const ok = await onSubmit(prompt.trim());
    if (ok) {
      setPrompt("");
      clearDraft(draftKey);
    }
  }

  return (
    <form onSubmit={submit} aria-labelledby="revise-title" className="space-y-2">
      <h2 id="revise-title" className="font-bold">
        수정 요청
      </h2>
      {sharedVersions.length > 0 && (
        <p role="note" className="rounded-lg bg-teal-50 p-2 text-xs text-teal-900">
          커뮤니티에 공유한 버전({sharedVersions.map((v) => `v${v}`).join(", ")})만 다른 사람이 볼 수 있어요. 새로 만든
          버전은 다시 공유하기 전까지 나만 볼 수 있어요.
        </p>
      )}
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
      {relogin && <ReloginNotice next={loginNext} />}
      <button
        type="submit"
        disabled={busy || !prompt.trim()}
        className="w-full rounded-xl bg-stone-800 px-4 py-2.5 font-semibold text-white hover:bg-stone-900 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {busy ? "다시 설계하고 있어요…" : `v${baseVersion} 기준으로 다시 설계`}
      </button>
      {user?.role !== "admin" && (
        <p className="text-xs text-stone-500">
          수정 요청도 최근 24시간 설계 횟수에 들어가요. 실패한 요청도 횟수에 포함돼요.
        </p>
      )}
    </form>
  );
}
