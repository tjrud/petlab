import Link from "next/link";

import type { SharedDesign } from "@/lib/types";
import { ui } from "@/lib/ui";

const chip = "rounded-full px-2 py-0.5 text-xs font-medium";

/** 글에 첨부된 설계 (누구나 3D 화면에서 읽기 전용으로 볼 수 있다) */
export default function SharedDesignCard({ design: d }: { design: SharedDesign }) {
  const h = d.habitat;
  const href = `/designs/${encodeURIComponent(d.id)}?version=${d.version}`;
  return (
    <section aria-labelledby="shared-design-title" className={`${ui.card} space-y-3`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-semibold text-teal-800">첨부한 설계</span>
        <span className={ui.badge}>v{d.version}</span>
        <span className={`${chip} ${d.passed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>
          {d.passed ? "통과" : "검증 실패"}
        </span>
      </div>
      <h2 id="shared-design-title" className="break-words text-lg font-semibold leading-snug">
        {d.title || "제목 없는 설계"}
      </h2>
      {d.summary_ko && <p className="break-words leading-relaxed text-stone-700">{d.summary_ko}</p>}
      {d.item_labels.length > 0 && (
        <ul aria-label="구조물" className="flex flex-wrap gap-1.5">
          {d.item_labels.map((label, i) => (
            <li key={`${i}-${label}`} className={`${chip} bg-stone-100 text-stone-700`}>
              {label}
            </li>
          ))}
        </ul>
      )}
      <p className="text-sm text-stone-600">
        {h.species_name_ko} {h.size_name_ko} · {h.count}마리 · 케이지 {h.cage.width_mm}×{h.cage.depth_mm}×
        {h.cage.height_mm}mm
      </p>
      <Link href={href} className={`${ui.btnPrimary} w-full sm:w-auto`}>
        3D로 보기
      </Link>
    </section>
  );
}
