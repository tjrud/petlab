"use client";

import { Link } from "@/i18n/client";

import type { Meta } from "@/lib/cagePlannerDoc";
import { withNext } from "@/lib/safeNext";
import type { SpeciesResponse } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 상단 줄: 배치안 이름·검토 기준 종·크기, 저장하지 않은 변경 표시, 새로 만들기·저장 (로그인 전에는 로그인 안내) */
export default function PlannerHeader({
  meta,
  onMetaChange,
  species,
  dirty,
  busy,
  loggedIn,
  needsLogin,
  onNew,
  onSave,
  shareHref,
}: {
  meta: Meta;
  onMetaChange: (patch: Partial<Meta>) => void;
  species: SpeciesResponse | null;
  dirty: boolean;
  busy: boolean;
  loggedIn: boolean;
  needsLogin: boolean;
  onNew: () => void;
  onSave: (asNew: boolean) => void;
  /** 저장한 배치안을 탐색에 공유하는 주소 (저장하지 않은 변경이 있으면 null) */
  shareHref: string | null;
}) {
  return (
    <div className={`${ui.card} flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between`}>
      <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
        <label className="block">
          <span className={ui.label}>배치안 이름</span>
          <input
            className={ui.input}
            value={meta.name}
            maxLength={40}
            onChange={(e) => onMetaChange({ name: e.target.value })}
          />
        </label>
        <label className="block">
          <span className={ui.label}>반려동물 종·크기 (검토 기준)</span>
          <select
            className={ui.input}
            value={`${meta.species}/${meta.size}`}
            disabled={!species}
            onChange={(e) => {
              const [s, z] = e.target.value.split("/");
              onMetaChange({ species: s, size: z });
            }}
          >
            {species ? (
              species.species.flatMap((sp) =>
                sp.sizes.map((z) => (
                  <option key={`${sp.key}/${z.key}`} value={`${sp.key}/${z.key}`}>
                    {sp.display_name} · {z.display_name}
                  </option>
                )),
              )
            ) : (
              <option value={`${meta.species}/${meta.size}`}>불러오는 중…</option>
            )}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {dirty && <span className="text-xs text-amber-700">저장하지 않은 변경</span>}
        <button type="button" className={ui.btnSecondary} onClick={onNew} disabled={busy}>
          새로 만들기
        </button>
        {loggedIn ? (
          <>
            {meta.layoutId && (
              <button type="button" className={ui.btnSecondary} onClick={() => onSave(true)} disabled={busy}>
                새 배치안으로 저장
              </button>
            )}
            {shareHref && (
              <Link href={shareHref} className={ui.btnSecondary}>
                탐색에 공유
              </Link>
            )}
            <button type="button" className={ui.btnPrimary} onClick={() => onSave(false)} disabled={busy || (!dirty && !!meta.layoutId)}>
              {busy ? "저장 중…" : "저장"}
            </button>
          </>
        ) : needsLogin ? (
          <Link href={withNext("/login", "/cage")} className={ui.btnPrimary}>
            로그인하고 저장
          </Link>
        ) : null}
      </div>
    </div>
  );
}
