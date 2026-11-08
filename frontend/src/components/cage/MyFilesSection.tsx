"use client";

import { Link } from "@/i18n/client";
import { useRef, useState } from "react";

import { getAsset, fileAssetKey, type CageAsset } from "@/lib/cageAssets";
import { errorText } from "@/lib/api";
import type { MarketFile } from "@/lib/types";
import { ui } from "@/lib/ui";

const cm = (mm: number) => (mm / 10).toFixed(mm % 10 === 0 ? 0 : 1);

/**
 * 카탈로그의 "내 파일": 탐색에 올린(또는 여기서 올린) STL·3MF 를 가상 케이지에 놓아 본다.
 * SketchUp(SKP)은 브라우저에서 3D 로 그릴 수 없어 놓을 수 없다 (SketchUp 에서 STL 로 내보내 올리면 된다).
 */
export default function MyFilesSection({
  loggedIn,
  files,
  onAdd,
  onUpload,
  onDelete,
}: {
  loggedIn: boolean;
  files: MarketFile[] | null;
  onAdd: (a: CageAsset) => void;
  onUpload: (file: File, onProgress: (pct: number) => void) => Promise<void>;
  onDelete: (file: MarketFile) => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!loggedIn) {
    return (
      <p className="mt-3 text-sm text-stone-600">
        <Link href="/login?next=%2Fcage" className={ui.link}>
          로그인
        </Link>
        하면 내가 올린 STL·3MF 파일을 케이지에 놓아 볼 수 있어요.
      </p>
    );
  }

  async function pick(f: File | undefined) {
    if (!f) return;
    setError(null);
    setProgress(0);
    try {
      await onUpload(f, setProgress);
    } catch (e) {
      setError(errorText(e, "올리지 못했어요."));
    } finally {
      setProgress(null);
    }
  }

  async function remove(f: MarketFile) {
    if (!window.confirm(`"${f.filename}" 파일을 지울까요? 이 파일을 놓아 둔 배치안에서도 보이지 않게 돼요.`)) return;
    setError(null);
    try {
      await onDelete(f);
    } catch (e) {
      setError(errorText(e, "지우지 못했어요."));
    }
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={input}
          type="file"
          accept=".stl,.3mf"
          className="sr-only"
          aria-label="케이지에 놓을 파일 올리기"
          onChange={(e) => {
            void pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <button type="button" className={ui.btnSecondary} onClick={() => input.current?.click()} disabled={progress !== null}>
          {progress !== null ? `올리는 중 ${progress}%` : "STL·3MF 올리기"}
        </button>
        <span className="text-xs text-stone-500">단위는 mm로 봐요.</span>
      </div>
      {error && <p className={ui.error}>{error}</p>}
      {files === null ? (
        <p className="text-sm text-stone-500">불러오는 중…</p>
      ) : files.length === 0 ? (
        <p className="text-sm text-stone-500">아직 올린 파일이 없어요.</p>
      ) : (
        <ul className="space-y-1.5">
          {files.map((f) => {
            const asset = getAsset(fileAssetKey(f.id));
            const reason =
              f.format === "skp"
                ? "SketchUp 파일은 3D로 볼 수 없어요. SketchUp에서 STL로 내보내 올려 주세요."
                : !asset
                  ? "크기를 읽지 못한 파일이에요."
                  : null;
            return (
              <li key={f.id} className="flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={!asset}
                  onClick={() => asset && onAdd(asset)}
                  aria-label={`${f.filename} ${asset ? "놓기" : "놓을 수 없음"}`}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-stone-200 bg-white p-2 text-left hover:border-amber-400 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:border-stone-200"
                >
                  <span className="grid h-10 w-12 shrink-0 place-items-center rounded-lg bg-violet-50 text-[11px] font-bold text-violet-800">
                    {f.format.toUpperCase()}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">{f.filename}</span>
                    <span className="block text-xs text-stone-500">
                      {reason ?? (f.dims_mm ? `${cm(f.dims_mm[0])}×${cm(f.dims_mm[1])}×${cm(f.dims_mm[2])}cm` : "")}
                    </span>
                  </span>
                </button>
                {!f.attached && (
                  <button
                    type="button"
                    onClick={() => void remove(f)}
                    aria-label={`${f.filename} 지우기`}
                    className="shrink-0 rounded-lg px-2 py-1 text-xs text-stone-500 hover:bg-red-50 hover:text-red-700"
                  >
                    지우기
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
