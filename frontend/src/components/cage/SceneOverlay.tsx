"use client";

import type { CameraView } from "@/components/cage/PlannerScene";
import type { Cage } from "@/lib/types";

const BACKGROUNDS = [
  { label: "쿨그레이 (기본)", color: "#eef1f4" },
  { label: "크림", color: "#fbf7f0" },
  { label: "흰색", color: "#ffffff" },
  { label: "하늘", color: "#e6eef6" },
  { label: "연두", color: "#eef4e4" },
  { label: "회색", color: "#e7e5e4" },
  { label: "남색", color: "#1e293b" },
  { label: "검정", color: "#111111" },
];

/** 3D 화면 위 도구 모음: 시점·1cm 격자·붙이기(왼쪽 위), 되돌리기·다시 하기(오른쪽 위), 케이지 크기·구조물 수와 조작 안내(오른쪽 아래) */
export default function SceneOverlay({
  view,
  onView,
  grid,
  onGrid,
  magnet,
  onMagnet,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  cage,
  itemCount,
  background,
  onBackground,
}: {
  view: CameraView;
  onView: (v: CameraView) => void;
  grid: boolean;
  onGrid: (on: boolean) => void;
  magnet: boolean;
  onMagnet: (on: boolean) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  cage: Cage;
  itemCount: number;
  background: string;
  onBackground: (color: string) => void;
}) {
  return (
    <>
      {/* 위쪽 도구 모음: 화면이 좁으면 오른쪽 묶음(되돌리기)이 다음 줄로 내려가 겹치지 않아요 */}
      <div className="pointer-events-none absolute inset-x-3 top-3 flex flex-wrap items-start justify-between gap-1.5">
      <div className="pointer-events-auto flex flex-wrap gap-1.5">
        <div className="flex overflow-hidden rounded-lg border border-stone-200 bg-white/90 text-xs shadow-sm" role="group" aria-label="시점">
          {(
            [
              ["3d", "3D"],
              ["top", "위에서"],
              ["front", "정면"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => onView(v)}
              className={`px-2.5 py-1.5 ${view === v ? "bg-amber-100 font-semibold text-amber-900" : "text-stone-600 hover:bg-stone-50"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white/90 px-2 py-1.5 text-xs text-stone-600 shadow-sm">
          <input type="checkbox" checked={grid} onChange={(e) => onGrid(e.target.checked)} />
          1cm 격자
        </label>
        <label className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white/90 px-2 py-1.5 text-xs text-stone-600 shadow-sm">
          <input type="checkbox" checked={magnet} onChange={(e) => onMagnet(e.target.checked)} />
          벽·구조물에 붙이기
        </label>
        <details className="relative rounded-lg border border-stone-200 bg-white/90 text-xs text-stone-600 shadow-sm">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2 py-1.5">
            <span className="inline-block h-3 w-3 rounded-full ring-1 ring-stone-300" style={{ backgroundColor: background }} />
            배경
          </summary>
          <div className="absolute left-0 top-full z-10 mt-1 w-52 rounded-lg border border-stone-200 bg-white p-2 shadow-md" role="group" aria-label="배경색">
            <div className="flex flex-wrap gap-1.5">
              {BACKGROUNDS.map((b) => (
                <button
                  key={b.color}
                  type="button"
                  title={b.label}
                  aria-label={`배경 ${b.label}`}
                  aria-pressed={background.toLowerCase() === b.color}
                  onClick={() => onBackground(b.color)}
                  className={`h-7 w-7 rounded-full ring-1 ring-stone-300 ${background.toLowerCase() === b.color ? "outline outline-2 outline-offset-1 outline-amber-500" : ""}`}
                  style={{ backgroundColor: b.color }}
                />
              ))}
            </div>
            <label className="mt-2 flex items-center justify-between gap-2">
              직접 고르기
              <input
                type="color"
                aria-label="배경색 직접 고르기"
                value={background}
                onChange={(e) => onBackground(e.target.value)}
                className="h-7 w-10 cursor-pointer rounded border border-stone-200 bg-white"
              />
            </label>
          </div>
        </details>
      </div>
      <div className="pointer-events-auto flex gap-1.5">
        <button
          type="button"
          className="rounded-lg border border-stone-200 bg-white/90 px-2.5 py-1.5 text-xs shadow-sm disabled:opacity-40"
          onClick={onUndo}
          disabled={!canUndo}
          title="되돌리기 (Ctrl+Z)"
        >
          ↶ 되돌리기
        </button>
        <button
          type="button"
          className="rounded-lg border border-stone-200 bg-white/90 px-2.5 py-1.5 text-xs shadow-sm disabled:opacity-40"
          onClick={onRedo}
          disabled={!canRedo}
          title="다시 하기 (Ctrl+Shift+Z)"
        >
          ↷ 다시 하기
        </button>
      </div>
      </div>
      <div className="pointer-events-none absolute bottom-3 right-3 max-w-[calc(100%-1.5rem)] rounded-lg bg-white/85 px-3 py-2 text-right text-[11px] leading-relaxed text-stone-600 shadow-sm">
        <p className="font-semibold text-stone-800">
          케이지 {cage.width_mm}×{cage.depth_mm}×{cage.height_mm}mm · 구조물 {itemCount}개
        </p>
        <p className="hidden sm:block">끌어서 옮기기 · R 90° 회전 · Q/E 15° · 방향키 1cm(Shift 1mm) · Del 삭제</p>
        <p className="sm:hidden">구조물을 끌어서 옮기고, 아래 패널에서 돌려요</p>
      </div>
    </>
  );
}
