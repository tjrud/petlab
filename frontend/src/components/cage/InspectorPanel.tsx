"use client";

import { useState } from "react";

import { assetDescription, assetName } from "@/components/cage/CatalogPanel";
import { useLang, useT } from "@/i18n/client";
import { CATEGORIES, type CageAsset } from "@/lib/cageAssets";
import { footprint, rotatedExtent, round1, TOL, wallGaps, type LayoutIssue } from "@/lib/cageLayout";
import type { Cage, LayoutItem } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 숫자 입력 칸: 입력 중에는 글자 그대로 두고, 칸을 떠나거나 Enter 를 누를 때 반영해요 */
function NumField({
  label,
  value,
  unit,
  onCommit,
}: {
  label: string;
  value: number;
  unit: string;
  onCommit: (v: number) => void;
}) {
  const [text, setText] = useState(String(round1(value)));
  const [shown, setShown] = useState(value);
  if (shown !== value) {
    setShown(value);
    setText(String(round1(value)));
  }
  const commit = () => {
    const v = Number(text);
    if (text.trim() !== "" && Number.isFinite(v)) onCommit(v);
    else setText(String(round1(value)));
  };
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-stone-500">
        {label} ({unit})
      </span>
      <input
        type="number"
        inputMode="decimal"
        aria-label={`${label} (${unit})`}
        className={ui.input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
      />
    </label>
  );
}

export default function InspectorPanel({
  item,
  asset,
  cage,
  issues,
  onMove,
  onRotate,
  onRotateTo,
  onDuplicate,
  onRemove,
}: {
  item: LayoutItem;
  asset: CageAsset;
  cage: Cage;
  issues: LayoutIssue[];
  onMove: (x: number, y: number) => void;
  onRotate: (delta: number) => void;
  onRotateTo: (deg: number) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const gaps = wallGaps(footprint(item, asset), cage);
  const ext = rotatedExtent(asset, item.rotation_deg);
  const categoryKo = CATEGORIES.find((c) => c.key === asset.category)?.label;
  const category = categoryKo && t(categoryKo);
  const gap = (v: number) =>
    v < -TOL ? <span className="text-red-600">{t("밖으로 {n}", { n: Math.round(-v) })}</span> : Math.round(Math.max(0, v));
  return (
    <section aria-label={t("선택한 구조물")} className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs text-stone-500">{category}</p>
          <h3 className="text-base font-semibold">{assetName(asset, t)}</h3>
          <p className="text-xs text-stone-500">
            {asset.size[0]}×{asset.size[1]}×{asset.size[2]}mm · {t("바닥 {w}×{d}mm", { w: Math.round(ext.w), d: Math.round(ext.d) })}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <button type="button" onClick={onDuplicate} className={ui.btnSecondary} title={t("복제 (Ctrl+D)")}>
            {t("복제")}
          </button>
          <button type="button" onClick={onRemove} className={ui.btnDanger} title={t("삭제 (Delete)")}>
            {t("삭제")}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <NumField label={t("가로 위치")} unit="mm" value={item.x_mm} onCommit={(v) => onMove(v, item.y_mm)} />
        <NumField label={t("세로 위치")} unit="mm" value={item.y_mm} onCommit={(v) => onMove(item.x_mm, v)} />
      </div>

      <div>
        <div className="flex items-end gap-2">
          <div className="w-24">
            <NumField label={t("회전")} unit="°" value={item.rotation_deg} onCommit={onRotateTo} />
          </div>
          <div className="flex flex-wrap gap-1">
            {/* 회전 각도는 위에서 볼 때 반시계 방향이 + */}
            <button type="button" className={ui.btnSecondary} onClick={() => onRotate(15)} title={t("반시계 15° (Q)")} aria-label={t("반시계 방향으로 15° 돌리기")}>
              ⟲ 15°
            </button>
            <button type="button" className={ui.btnSecondary} onClick={() => onRotate(-15)} title={t("시계 15° (E)")} aria-label={t("시계 방향으로 15° 돌리기")}>
              ⟳ 15°
            </button>
            <button type="button" className={ui.btnSecondary} onClick={() => onRotate(90)} title="R">
              {t("90° 돌리기")}
            </button>
          </div>
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-stone-600">{t("벽까지 거리 (mm)")}</p>
        <dl className="grid grid-cols-4 gap-1 text-center text-xs">
          {(
            [
              ["왼쪽", gaps.left],
              ["오른쪽", gaps.right],
              ["앞", gaps.front],
              ["뒤", gaps.back],
            ] as const
          ).map(([k, v]) => (
            <div key={k} className="rounded-lg bg-stone-50 px-1 py-1.5">
              <dt className="text-stone-500">{t(k)}</dt>
              <dd className="font-semibold tabular-nums">{gap(v)}</dd>
            </div>
          ))}
        </dl>
      </div>

      {issues.length > 0 && (
        <ul className="space-y-1 text-xs">
          {issues.map((i) => (
            <li key={i.key} className={i.severity === "error" ? "text-red-700" : "text-amber-800"}>
              <span className="mr-1 font-semibold">{i.severity === "error" ? t("오류") : t("경고")}</span>
              {i.text(t, lang)}
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-stone-400">{assetDescription(asset, t)}</p>
    </section>
  );
}
