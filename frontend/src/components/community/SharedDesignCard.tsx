import { Link, useT } from "@/i18n/client";

import type { SharedDesign } from "@/lib/types";
import { ui } from "@/lib/ui";

const chip = "rounded-full px-2 py-0.5 text-xs font-medium";

/** 글에 첨부된 설계 (누구나 3D 화면에서 읽기 전용으로 볼 수 있다) */
export default function SharedDesignCard({ design: d }: { design: SharedDesign }) {
  const t = useT();
  const h = d.habitat;
  const href = `/designs/${encodeURIComponent(d.id)}?version=${d.version}`;
  return (
    <section aria-labelledby="shared-design-title" className={`${ui.card} space-y-3`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-semibold text-teal-800">{t("첨부한 설계")}</span>
        <span className={ui.badge}>v{d.version}</span>
        <span className={`${chip} ${d.passed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>
          {d.passed ? t("통과") : t("검증 실패")}
        </span>
      </div>
      <h2 id="shared-design-title" className="break-words text-lg font-semibold leading-snug">
        {d.title || t("제목 없는 설계")}
      </h2>
      {d.summary_ko && <p className="break-words leading-relaxed text-stone-700">{d.summary_ko}</p>}
      {d.item_labels.length > 0 && (
        <ul aria-label={t("구조물")} className="flex flex-wrap gap-1.5">
          {d.item_labels.map((label, i) => (
            <li key={`${i}-${label}`} className={`${chip} bg-stone-100 text-stone-700`}>
              {label}
            </li>
          ))}
        </ul>
      )}
      <p className="text-sm text-stone-600">
        {t("{species} {size} · {n}마리", { species: t(h.species_name_ko), size: t(h.size_name_ko), n: h.count })} ·{" "}
        {t("케이지 {w}×{d}×{h}mm", { w: h.cage.width_mm, d: h.cage.depth_mm, h: h.cage.height_mm })}
      </p>
      <Link href={href} className={`${ui.btnPrimary} w-full sm:w-auto`}>
        {t("3D로 보기")}
      </Link>
    </section>
  );
}
