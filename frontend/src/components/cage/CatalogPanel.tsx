"use client";

import { useState } from "react";

import MyFilesSection from "@/components/cage/MyFilesSection";
import { useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { CAGE_ASSETS, CATEGORIES, type AssetCategory, type CageAsset } from "@/lib/cageAssets";
import type { MarketFile } from "@/lib/types";

/** 화면에 보일 에셋 이름: 기본 에셋은 번역하고, 내가 올린 파일은 파일 이름 그대로 */
export function assetName(a: CageAsset, t: TFunction): string {
  if (a.mesh) return a.name === "내 파일" ? t("내 파일") : a.name;
  return t(a.name);
}

/** 화면에 보일 에셋 설명 (내가 올린 파일은 cageAssets.registerFileAsset 과 같은 문구) */
export function assetDescription(a: CageAsset, t: TFunction): string {
  if (a.mesh) return t("올린 {format} 파일 (실제 크기)", { format: a.mesh.format.toUpperCase() });
  return t(a.description);
}

const cm = (mm: number) => (mm % 10 === 0 ? `${mm / 10}` : (mm / 10).toFixed(1));

/** 위에서 본 모양 미리보기 (가로·세로 비율, 앞쪽 출입구는 주황 선) */
function TopView({ asset }: { asset: CageAsset }) {
  const [w, d] = asset.size;
  const S = 44;
  const k = S / Math.max(w, d);
  const rw = w * k;
  const rd = d * k;
  const x = (56 - rw) / 2;
  const y = (52 - rd) / 2;
  const sides = asset.accessSides ?? [];
  const mark = "#f59e0b";
  return (
    <svg viewBox="0 0 56 52" className="h-12 w-14 shrink-0" aria-hidden>
      <rect x={x} y={y} width={rw} height={rd} rx={asset.shape === "bowl" || asset.shape === "water_stand" ? rw / 2 : 4} fill={asset.color} stroke="#78716c" strokeOpacity={0.35} />
      {/* 화면 아래쪽 = 케이지 앞쪽 */}
      {sides.includes("front") && <line x1={x + rw * 0.3} x2={x + rw * 0.7} y1={y + rd} y2={y + rd} stroke={mark} strokeWidth={3} />}
      {sides.includes("back") && <line x1={x + rw * 0.3} x2={x + rw * 0.7} y1={y} y2={y} stroke={mark} strokeWidth={3} />}
      {sides.includes("left") && <line x1={x} x2={x} y1={y + rd * 0.25} y2={y + rd * 0.75} stroke={mark} strokeWidth={3} />}
      {sides.includes("right") && <line x1={x + rw} x2={x + rw} y1={y + rd * 0.25} y2={y + rd * 0.75} stroke={mark} strokeWidth={3} />}
    </svg>
  );
}

export default function CatalogPanel({
  onAdd,
  onStarter,
  empty,
  bedding,
  onRemoveBedding,
  loggedIn,
  myFiles,
  onUploadFile,
  onDeleteFile,
}: {
  onAdd: (a: CageAsset) => void;
  onStarter: () => void;
  empty: boolean;
  /** 깔아 둔 바닥재 (없으면 null) */
  bedding: CageAsset | null;
  onRemoveBedding: () => void;
  loggedIn: boolean;
  /** 내가 올린 파일 (불러오는 중이면 null) */
  myFiles: MarketFile[] | null;
  onUploadFile: (file: File, onProgress: (pct: number) => void) => Promise<void>;
  onDeleteFile: (file: MarketFile) => Promise<void>;
}) {
  const t = useT();
  const [cat, setCat] = useState<AssetCategory | "all" | "mine">("all");
  const list = cat === "mine" ? [] : cat === "all" ? CAGE_ASSETS : CAGE_ASSETS.filter((a) => a.category === cat);
  return (
    <div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("에셋 종류")}>
        {[{ key: "all" as const, label: "전체" }, ...CATEGORIES, { key: "mine" as const, label: "내 파일" }].map((c) => (
          <button
            key={c.key}
            type="button"
            aria-pressed={cat === c.key}
            onClick={() => setCat(c.key)}
            className={`rounded-full border px-3 py-1 text-xs ${
              cat === c.key ? "border-amber-500 bg-amber-100 font-semibold text-amber-900" : "border-stone-300 text-stone-600 hover:bg-stone-50"
            }`}
          >
            {t(c.label)}
          </button>
        ))}
      </div>
      {cat === "mine" && <MyFilesSection loggedIn={loggedIn} files={myFiles} onAdd={onAdd} onUpload={onUploadFile} onDelete={onDeleteFile} />}
      {bedding && (
        <div className="mt-3 flex items-center justify-between gap-2 rounded-xl bg-amber-50/70 px-3 py-2 text-sm">
          <span>
            {t("바닥재:")} <span className="font-semibold">{assetName(bedding, t)}</span>
          </span>
          <button type="button" onClick={onRemoveBedding} className="shrink-0 text-xs font-medium text-amber-800 underline-offset-2 hover:underline">
            {t("바닥재 빼기")}
          </button>
        </div>
      )}
      {empty && cat !== "mine" && (
        <button
          type="button"
          onClick={onStarter}
          className="mt-3 w-full rounded-xl border border-dashed border-amber-400 bg-amber-50 px-3 py-2.5 text-sm font-medium text-amber-900 hover:bg-amber-100"
        >
          {t("기본 구성 한 번에 넣기 (다방 은신처·쳇바퀴·모래목욕통·밥그릇·급수기)")}
        </button>
      )}
      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
        {list.map((a) => {
          const name = assetName(a, t);
          const description = assetDescription(a, t);
          return (
            <li key={a.key}>
              <button
                type="button"
                onClick={() => onAdd(a)}
                aria-label={
                  a.floorLayer
                    ? bedding?.key === a.key
                      ? t("{name} 깔려 있음", { name })
                      : t("{name} 깔기", { name })
                    : t("{name} 추가", { name })
                }
                title={description}
                className="flex w-full items-center gap-2 rounded-xl border border-stone-200 bg-white p-2 text-left transition hover:border-amber-400 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
              >
                <TopView asset={a} />
                <span className="min-w-0">
                  <span className="block text-sm font-semibold leading-tight break-keep">{name}</span>
                  <span className="block text-xs text-stone-500">
                    {a.floorLayer ? t("바닥 전체 · 깊이 {d}cm", { d: cm(a.size[2]) }) : `${cm(a.size[0])}×${cm(a.size[1])}×${cm(a.size[2])}cm`}
                  </span>
                  <span className="block truncate text-[11px] text-stone-400">{description}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-stone-500">
        {t("누르면 비어 있는 자리에 놓여요. 바닥재는 바닥 전체에 깔리고, 다른 바닥재를 누르면 바뀌어요. 치수는 흔히 쓰는 제품 기준 근사치라 실제 제품과 다를 수 있어요. 주황 선은 출입구 방향이에요.")}
      </p>
    </div>
  );
}
