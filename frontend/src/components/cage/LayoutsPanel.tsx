"use client";

import { useT } from "@/i18n/client";
import type { CageLayoutSummary } from "@/lib/types";
import { formatDateTime, ui } from "@/lib/ui";

/** 계정에 저장한 배치안 목록 */
export default function LayoutsPanel({
  layouts,
  currentId,
  error,
  busy,
  onOpen,
  onDelete,
}: {
  layouts: CageLayoutSummary[] | null;
  currentId: string | null;
  error: string | null;
  busy: boolean;
  onOpen: (id: string) => void;
  onDelete: (l: CageLayoutSummary) => void;
}) {
  const t = useT();
  if (error) return <p className={ui.error}>{error}</p>;
  if (!layouts) return <p className="text-sm text-stone-500">{t("불러오는 중…")}</p>;
  if (layouts.length === 0) return <p className="text-sm text-stone-500">{t("아직 저장한 배치안이 없어요. 배치를 만들고 저장하면 여기에 보여요.")}</p>;
  return (
    <ul className="space-y-2">
      {layouts.map((l) => (
        <li
          key={l.id}
          className={`rounded-xl border p-3 ${l.id === currentId ? "border-amber-400 bg-amber-50" : "border-stone-200 bg-white"}`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{l.name}</p>
              <p className="text-xs text-stone-500">
                {l.cage.width_mm}×{l.cage.depth_mm}×{l.cage.height_mm}mm · {t("구조물 {n}개", { n: l.item_count })} · {t(l.size_name_ko)}
              </p>
              <p className="text-[11px] text-stone-400">{t("{date} 저장", { date: formatDateTime(l.updated_at) })}</p>
            </div>
            <div className="flex shrink-0 gap-1">
              <button type="button" disabled={busy || l.id === currentId} onClick={() => onOpen(l.id)} className={ui.btnSecondary}>
                {l.id === currentId ? t("열려 있음") : t("열기")}
              </button>
              <button type="button" disabled={busy} onClick={() => onDelete(l)} className={ui.btnDanger} aria-label={t("{name} 삭제", { name: l.name })}>
                {t("삭제")}
              </button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
