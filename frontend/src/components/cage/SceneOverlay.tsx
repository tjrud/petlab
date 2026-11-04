"use client";

import type { CameraView } from "@/components/cage/PlannerScene";
import type { Cage } from "@/lib/types";

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
}) {
  return (
    <>
      <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
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
      </div>
      <div className="absolute right-3 top-3 flex gap-1.5">
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
