"use client";

import { useState } from "react";

import { api, ApiError, errorText } from "@/lib/api";

/** 설계 지우기 (소유자만 보이게 쓴다). 모든 버전이 지워지고, 커뮤니티 글에 첨부돼 있으면 글에서 빠진다 */
export default function DeleteDesignButton({
  id,
  title,
  versionCount,
  shared,
  onDeleted,
  className = "",
}: {
  id: string;
  title: string;
  versionCount: number;
  shared: boolean;
  onDeleted: () => void;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    const lines = [
      `"${title}" 설계를 지울까요?`,
      `버전 ${versionCount}개와 3D 파일이 모두 지워지고 되돌릴 수 없어요.`,
      ...(shared ? ["커뮤니티 글에 첨부된 설계는 글에서 빠져요 (글은 남아요)."] : []),
    ];
    if (!window.confirm(lines.join("\n"))) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteDesign(id);
      onDeleted();
    } catch (e) {
      // 다른 창에서 이미 지웠으면 지운 것으로 본다
      if (e instanceof ApiError && e.status === 404) return onDeleted();
      setError(errorText(e, "설계를 지우지 못했어요."));
      setBusy(false);
    }
  }

  return (
    <span className={`inline-flex flex-col items-end gap-1 ${className}`}>
      <button
        type="button"
        onClick={remove}
        disabled={busy}
        aria-label={`${title} 설계 지우기`}
        className="rounded-lg border border-red-200 bg-white px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
      >
        {busy ? "지우는 중…" : "삭제"}
      </button>
      {error && (
        <span role="alert" className="max-w-[14rem] text-right text-xs text-red-700">
          {error}
        </span>
      )}
    </span>
  );
}
