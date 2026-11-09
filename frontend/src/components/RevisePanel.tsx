"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { clearDraft, ReloginNotice, useDraftBackup } from "@/components/DraftRelogin";
import { EmailUnverifiedNotice } from "@/components/EmailVerification";
import { useT } from "@/i18n/client";
import type { HabitatKind } from "@/lib/types";

// 수정 요청 예시. 어항 구조물(물속 동굴·터널)에는 환기구가 없다
const EXAMPLES: Record<HabitatKind, readonly string[]> = {
  cage: ["조금 더 크게 해 주세요", "환기구를 10개로 늘려 주세요", "오른쪽으로 옮겨 주세요"],
  aquarium: ["조금 더 크게 해 주세요", "출입구를 더 넓게 해 주세요", "오른쪽으로 옮겨 주세요"],
};

export default function RevisePanel({
  baseVersion,
  latestVersion,
  sharedVersions,
  busy,
  error,
  needsLogin,
  emailBlocked,
  draftKey,
  loginNext,
  onSubmit,
  kind = "cage",
}: {
  baseVersion: number;
  latestVersion: number;
  /** 커뮤니티 글에 첨부된 버전 (다른 사람은 이 버전만 볼 수 있다) */
  sharedVersions: number[];
  busy: boolean;
  error: string | null;
  /** 수정 요청이 로그인 문제로 실패했다 */
  needsLogin: boolean;
  /** 수정 요청을 서버가 이메일 인증 전이라고 거절했다 */
  emailBlocked: boolean;
  /** 로그인이 풀린 동안 쓴 요청을 맡겨 둘 이름 (설계마다 다르게) */
  draftKey: string;
  /** 다시 로그인한 뒤 돌아올 주소 */
  loginNext: string;
  onSubmit: (prompt: string) => Promise<boolean>;
  /** 사육 환경 종류 (예시 문구가 달라진다). 없으면 케이지 */
  kind?: HabitatKind;
}) {
  const t = useT();
  const { status, user, emailUnverified } = useAuth();
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
        {t("수정 요청")}
      </h2>
      {sharedVersions.length > 0 && (
        <p role="note" className="rounded-lg bg-teal-50 p-2 text-xs text-teal-900">
          {t(
            "커뮤니티에 공유한 버전({versions})만 다른 사람이 볼 수 있어요. 새로 만든 버전은 다시 공유하기 전까지 나만 볼 수 있어요.",
            { versions: sharedVersions.map((v) => `v${v}`).join(", ") },
          )}
        </p>
      )}
      {baseVersion !== latestVersion && (
        <p className="rounded-lg bg-sky-50 p-2 text-xs text-sky-900">
          {t(
            "지금 v{base}을 보고 있어요. 이 버전을 기준으로 수정하면 새 버전 v{next}이 만들어지고, 기존 버전은 그대로 남아요.",
            { base: baseVersion, next: latestVersion + 1 },
          )}
        </p>
      )}
      <textarea
        aria-label={t("수정할 내용")}
        rows={3}
        maxLength={2000}
        placeholder={kind === "aquarium" ? t("예: 동굴을 조금 더 크게, 출입구는 더 넓게") : t("예: 은신처를 조금 더 크게, 환기구는 더 많이")}
        className="w-full rounded-xl border border-stone-300 p-3 text-sm"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={busy}
      />
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES[kind].map((p) => (
          <button
            key={p}
            type="button"
            disabled={busy}
            onClick={() => setPrompt(t(p))}
            className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-200"
          >
            {t(p)}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {relogin && <ReloginNotice next={loginNext} />}
      {!relogin && (emailUnverified || emailBlocked) && <EmailUnverifiedNotice action="수정을 요청할" />}
      <button
        type="submit"
        disabled={busy || !prompt.trim() || emailUnverified}
        className="w-full rounded-xl bg-stone-800 px-4 py-2.5 font-semibold text-white hover:bg-stone-900 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {busy ? t("다시 설계하고 있어요…") : t("v{n} 기준으로 다시 설계", { n: baseVersion })}
      </button>
      {user?.role !== "admin" && (
        <p className="text-xs text-stone-500">
          {t("수정 요청도 최근 24시간 설계 횟수에 들어가요. 실패한 요청도 횟수에 포함돼요.")}
        </p>
      )}
    </form>
  );
}
