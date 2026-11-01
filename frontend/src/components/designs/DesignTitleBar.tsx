import Link from "next/link";

import type { Design } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 설계 화면 상단: 제목·버전·사육 환경, 소유자는 커뮤니티 공유, 다른 회원은 읽기 전용 안내 */
export default function DesignTitleBar({ design }: { design: Design }) {
  const cur = design.current;
  const h = design.habitat;
  const shareHref = `/community/new?design=${encodeURIComponent(design.id)}&version=${cur.version}`;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
          <h1 className="min-w-0 break-words text-2xl font-bold leading-snug">{design.title || "맞춤 설계"}</h1>
          <span data-testid="design-version" className={`${ui.badge} text-sm`}>
            v{cur.version}
          </span>
          {design.shared && (
            <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-teal-800">
              커뮤니티에 공유됨
            </span>
          )}
          {cur.provider === "mock" && (
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-800">개발용 모의 해석기</span>
          )}
        </div>
        {design.is_owner && (
          <Link href={shareHref} className={`${ui.btnSecondary} shrink-0`}>
            커뮤니티에 공유
          </Link>
        )}
      </div>
      <p className="text-sm text-stone-500">
        {h.species_name_ko} {h.size_name_ko} · {h.count}마리 · 케이지 {h.cage.width_mm}×{h.cage.depth_mm}×
        {h.cage.height_mm}mm
      </p>
      {!design.is_owner && (
        <p role="note" className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
          {design.owner_nickname ?? "회원"}님이 커뮤니티에 공유한 설계예요. 읽기 전용이에요.
        </p>
      )}
    </div>
  );
}
