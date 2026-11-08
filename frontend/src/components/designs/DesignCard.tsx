import { Link } from "@/i18n/client";

import DeleteDesignButton from "@/components/designs/DeleteDesignButton";
import type { DesignListItem } from "@/lib/types";
import { formatDate, ui } from "@/lib/ui";

const chip = "rounded-full px-2 py-0.5 text-xs font-medium";

/** "내 설계" 목록의 카드 하나 (누르면 설계 화면으로). 오른쪽 아래 '삭제'는 링크 밖에 겹쳐 둔다 (링크 안에 버튼을 넣지 않게) */
export default function DesignCard({ design: d, onDeleted }: { design: DesignListItem; onDeleted: () => void }) {
  const h = d.habitat;
  const c = h.cage;
  return (
    <li className="relative min-w-0">
      <Link
        href={`/designs/${encodeURIComponent(d.id)}`}
        className="flex h-full flex-col rounded-2xl border border-stone-200 bg-white p-4 shadow-sm transition hover:border-amber-300 hover:bg-amber-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={ui.badge}>v{d.latest_version}</span>
          <span className={`${chip} bg-stone-100 text-stone-700`}>버전 {d.version_count}개</span>
          <span className={`${chip} ${d.latest_passed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>
            {d.latest_passed ? "통과" : "검증 실패"}
          </span>
          {d.shared && <span className={`${chip} bg-teal-100 text-teal-800`}>커뮤니티 공유됨</span>}
        </div>

        <h2 className="mt-3 line-clamp-2 break-words font-semibold leading-snug">{d.title || "제목 없는 설계"}</h2>

        <p className="mt-2 text-sm text-stone-600">
          {h.species_name_ko} {h.size_name_ko} · {h.count}마리
        </p>
        <p className="text-sm text-stone-600">
          케이지 {c.width_mm}×{c.depth_mm}×{c.height_mm}mm
        </p>
        {d.pet_name && (
          <p className="mt-2">
            <span className={`${chip} inline-block max-w-full truncate bg-orange-50 text-orange-900 ring-1 ring-orange-200`}>
              {d.pet_name}
            </span>
          </p>
        )}

        <p className="mt-auto pr-16 pt-3 text-xs text-stone-500">{formatDate(d.updated_at)} 수정</p>
      </Link>
      <DeleteDesignButton
        id={d.id}
        title={d.title || "제목 없는 설계"}
        versionCount={d.version_count}
        shared={d.shared}
        onDeleted={onDeleted}
        className="absolute bottom-3 right-3"
      />
    </li>
  );
}
