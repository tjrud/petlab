"use client";

import { useState } from "react";

import { CAGE_LIMITS, cageDimError } from "@/components/me/common";
import type { Cage, Pet } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 케이지 크기 프리셋 (내부 치수 mm) */
export const PLANNER_PRESETS = [
  { label: "소형 45×30×30", w: 450, d: 300, h: 300 },
  { label: "중형 60×40×30", w: 600, d: 400, h: 300 },
  { label: "대형 80×50×40", w: 800, d: 500, h: 400 },
  { label: "초대형 100×50×50", w: 1000, d: 500, h: 500 },
  { label: "와이드 120×60×50", w: 1200, d: 600, h: 500 },
] as const;

const DIMS = [
  ["w", "가로", "width_mm"],
  ["d", "세로(깊이)", "depth_mm"],
  ["h", "높이", "height_mm"],
] as const;

type Draft = { w: string; d: string; h: string };

const toDraft = (c: Cage): Draft => ({ w: String(c.width_mm), d: String(c.depth_mm), h: String(c.height_mm) });

/** 입력 오류 목록 (서버 CageIn 과 같은 범위) */
function errorsOf(draft: Draft): string[] {
  const errs: string[] = [];
  for (const [k, label] of DIMS) {
    const v = Number(draft[k]);
    if (draft[k].trim() === "" || !Number.isFinite(v)) errs.push(`${label}를 숫자로 입력해 주세요.`);
    else {
      const e = cageDimError(k, v, label);
      if (e) errs.push(e);
    }
  }
  return errs;
}

export default function CageSizePanel({
  cage,
  onApply,
  pets,
  onPickPet,
  outsideCount,
  onPullInside,
}: {
  cage: Cage;
  onApply: (c: Cage) => void;
  pets: Pet[] | null;
  onPickPet: (p: Pet) => void;
  outsideCount: number;
  onPullInside: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(cage));
  // 되돌리기·불러오기·프리셋 등으로 바깥에서 케이지가 바뀌면 입력 칸도 맞춰요 (렌더 중 이전 값과 비교)
  const [shown, setShown] = useState(cage);
  if (shown !== cage) {
    setShown(cage);
    setDraft(toDraft(cage));
  }
  const errors = errorsOf(draft);
  const changed = draft.w !== String(cage.width_mm) || draft.d !== String(cage.depth_mm) || draft.h !== String(cage.height_mm);
  const apply = () => {
    if (errors.length) return;
    onApply({ width_mm: Number(draft.w), depth_mm: Number(draft.d), height_mm: Number(draft.h) });
  };
  const petCages = (pets ?? []).filter((p) => p.cage);

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-sm font-medium">자주 쓰는 크기 (cm)</p>
        <div className="flex flex-wrap gap-1.5">
          {PLANNER_PRESETS.map((p) => {
            const on = cage.width_mm === p.w && cage.depth_mm === p.d && cage.height_mm === p.h;
            return (
              <button
                key={p.label}
                type="button"
                aria-pressed={on}
                onClick={() => onApply({ width_mm: p.w, depth_mm: p.d, height_mm: p.h })}
                className={`rounded-full border px-3 py-1 text-xs ${on ? "border-amber-500 bg-amber-100 font-semibold" : "border-stone-300 hover:bg-stone-50"}`}
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </div>

      {petCages.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium">내 반려동물 케이지</p>
          <div className="flex flex-wrap gap-1.5">
            {petCages.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => onPickPet(p)}
                className="rounded-full border border-teal-300 bg-teal-50 px-3 py-1 text-xs text-teal-900 hover:bg-teal-100"
              >
                {p.name} · {p.cage!.width_mm}×{p.cage!.depth_mm}×{p.cage!.height_mm}mm
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          apply();
        }}
      >
        <p className="mb-2 text-sm font-medium">직접 입력 (내부 치수, mm)</p>
        <div className="grid grid-cols-3 gap-2">
          {DIMS.map(([k, label]) => (
            <label key={k} className="block">
              <span className="mb-1 block text-xs text-stone-500">{label}</span>
              <input
                type="number"
                inputMode="numeric"
                min={CAGE_LIMITS[k][0]}
                max={CAGE_LIMITS[k][1]}
                step={1}
                aria-label={`케이지 ${label} (mm)`}
                className={ui.input}
                value={draft[k]}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              />
            </label>
          ))}
        </div>
        {errors.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-xs text-red-700">
            {errors.map((e) => (
              <li key={e}>• {e}</li>
            ))}
          </ul>
        )}
        <div className="mt-3 flex items-center gap-2">
          <button type="submit" disabled={!changed || errors.length > 0} className={ui.btnSecondary}>
            크기 적용
          </button>
          {changed && errors.length === 0 && <span className="text-xs text-stone-500">적용하면 3D 화면이 바뀌어요.</span>}
        </div>
        <p className="mt-2 text-xs text-stone-500">바닥재를 깐 상태의 안쪽 공간을 재 주세요. 가로·세로 200~2000mm, 높이 100~1000mm.</p>
      </form>

      {outsideCount > 0 && (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <p>구조물 {outsideCount}개가 케이지 밖으로 나가 있어요.</p>
          <button type="button" onClick={onPullInside} className="mt-2 font-semibold text-amber-800 underline-offset-2 hover:underline">
            벽 안쪽으로 모두 옮기기
          </button>
        </div>
      )}
    </div>
  );
}
