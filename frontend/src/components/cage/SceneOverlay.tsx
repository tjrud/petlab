"use client";

import { useEffect, useRef } from "react";

import type { CameraView } from "@/components/cage/PlannerScene";
import { useT } from "@/i18n/client";
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
  panMode,
  onPanMode,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  cage,
  itemCount,
  background,
  onBackground,
  onInsets,
}: {
  view: CameraView;
  onView: (v: CameraView) => void;
  grid: boolean;
  onGrid: (on: boolean) => void;
  magnet: boolean;
  onMagnet: (on: boolean) => void;
  /** 화면 이동 모드 (빈 곳을 끌면 회전 대신 이동) */
  panMode: boolean;
  onPanMode: (on: boolean) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  cage: Cage;
  itemCount: number;
  background: string;
  onBackground: (color: string) => void;
  /** 3D 화면 위·아래를 가리는 높이(px): 위쪽 도구 모음, 아래쪽 안내 상자. 카메라를 그 사이 공간에 맞춰요 */
  onInsets?: (insets: { top: number; bottom: number }) => void;
}) {
  const t = useT();
  const toolbar = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const bar = toolbar.current;
    const info = card.current;
    const box = bar?.offsetParent as HTMLElement | null;
    if (!bar || !info || !box || !onInsets) return;
    let last = "";
    const report = () => {
      const top = bar.offsetTop + bar.offsetHeight;
      const bottom = box.clientHeight - info.offsetTop;
      const key = `${top}|${bottom}`;
      if (key !== last) {
        last = key;
        onInsets({ top, bottom });
      }
    };
    report();
    const ro = new ResizeObserver(report);
    [bar, info, box].forEach((el) => ro.observe(el));
    return () => ro.disconnect();
  }, [onInsets]);
  return (
    <>
      {/* 위쪽 도구 모음: 화면이 좁으면 줄을 바꿔 겹치지 않아요. 되돌리기·다시 하기는 오른쪽 끝(좁은 화면에서는 화살표만) */}
      <div ref={toolbar} className="pointer-events-none absolute inset-x-3 top-3 flex flex-wrap items-start gap-1.5 *:pointer-events-auto">
        <div className="flex overflow-hidden rounded-lg border border-stone-200 bg-white/90 text-xs shadow-sm" role="group" aria-label={t("시점")}>
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
              {t(label)}
            </button>
          ))}
        </div>
        {/* 화면 이동: 마우스·트랙패드로 왼쪽 끌기만 할 때를 위해 (휴대폰은 두 손가락으로 끌면 이동) */}
        <button
          type="button"
          aria-pressed={panMode}
          onClick={() => onPanMode(!panMode)}
          title={t("켜면 빈 곳을 끌어 화면을 옮겨요(Shift를 누르고 끌면 돌려요). 끄면 돌리고, 오른쪽 버튼이나 Shift를 누르고 끌면 옮겨요")}
          className={`hidden rounded-lg border px-2.5 py-1.5 text-xs shadow-sm sm:block ${
            panMode ? "border-amber-400 bg-amber-100 font-semibold text-amber-900" : "border-stone-200 bg-white/90 text-stone-600 hover:bg-stone-50"
          }`}
        >
          {t("화면 이동")}
        </button>
        <label className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white/90 px-2 py-1.5 text-xs text-stone-600 shadow-sm">
          <input type="checkbox" checked={grid} onChange={(e) => onGrid(e.target.checked)} />
          {t("1cm 격자")}
        </label>
        <label className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white/90 px-2 py-1.5 text-xs text-stone-600 shadow-sm">
          <input type="checkbox" checked={magnet} onChange={(e) => onMagnet(e.target.checked)} />
          {t("벽·구조물에 붙이기")}
        </label>
        <details className="relative rounded-lg border border-stone-200 bg-white/90 text-xs text-stone-600 shadow-sm">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2 py-1.5">
            <span className="inline-block h-3 w-3 rounded-full ring-1 ring-stone-300" style={{ backgroundColor: background }} />
            {t("배경")}
          </summary>
          <div className="absolute left-0 top-full z-10 mt-1 w-52 rounded-lg border border-stone-200 bg-white p-2 shadow-md" role="group" aria-label={t("배경색")}>
            <div className="flex flex-wrap gap-1.5">
              {BACKGROUNDS.map((b) => (
                <button
                  key={b.color}
                  type="button"
                  title={t(b.label)}
                  aria-label={t("배경 {color}", { color: t(b.label) })}
                  aria-pressed={background.toLowerCase() === b.color}
                  onClick={() => onBackground(b.color)}
                  className={`h-7 w-7 rounded-full ring-1 ring-stone-300 ${background.toLowerCase() === b.color ? "outline outline-2 outline-offset-1 outline-amber-500" : ""}`}
                  style={{ backgroundColor: b.color }}
                />
              ))}
            </div>
            <label className="mt-2 flex items-center justify-between gap-2">
              {t("직접 고르기")}
              <input
                type="color"
                aria-label={t("배경색 직접 고르기")}
                value={background}
                onChange={(e) => onBackground(e.target.value)}
                className="h-7 w-10 cursor-pointer rounded border border-stone-200 bg-white"
              />
            </label>
          </div>
        </details>
      <div className="ml-auto flex gap-1.5">
        <button
          type="button"
          className="rounded-lg border border-stone-200 bg-white/90 px-2.5 py-1.5 text-xs shadow-sm disabled:opacity-40"
          onClick={onUndo}
          disabled={!canUndo}
          title={t("되돌리기 (Ctrl+Z)")}
          aria-label={`↶ ${t("되돌리기")}`}
        >
          ↶<span className="hidden sm:inline"> {t("되돌리기")}</span>
        </button>
        <button
          type="button"
          className="rounded-lg border border-stone-200 bg-white/90 px-2.5 py-1.5 text-xs shadow-sm disabled:opacity-40"
          onClick={onRedo}
          disabled={!canRedo}
          title={t("다시 하기 (Ctrl+Shift+Z)")}
          aria-label={`↷ ${t("다시 하기")}`}
        >
          ↷<span className="hidden sm:inline"> {t("다시 하기")}</span>
        </button>
      </div>
      </div>
      <div ref={card} className="pointer-events-none absolute bottom-3 right-3 max-w-[calc(100%-1.5rem)] rounded-lg bg-white/85 px-3 py-2 text-right text-[11px] leading-relaxed text-stone-600 shadow-sm">
        <p className="font-semibold text-stone-800">
          {t("케이지 {w}×{d}×{h}mm · 구조물 {n}개", { w: cage.width_mm, d: cage.depth_mm, h: cage.height_mm, n: itemCount })}
        </p>
        <p className="hidden sm:block">{t("구조물 끌기: 옮기기 · R 90° 회전 · Q/E 15° · 방향키 1cm(Shift 1mm) · Del 삭제")}</p>
        <p className="hidden sm:block">
          {panMode
            ? t("빈 곳 끌기: 화면 이동 · Shift 끌기: 돌려 보기 · 휠: 확대")
            : t("빈 곳 끌기: 돌려 보기 · 오른쪽 버튼·Shift 끌기: 화면 이동 · 휠: 확대")}
        </p>
        <p className="sm:hidden">{t("구조물을 끌어서 옮기고, 두 손가락으로 화면을 옮기거나 확대해요")}</p>
      </div>
    </>
  );
}
