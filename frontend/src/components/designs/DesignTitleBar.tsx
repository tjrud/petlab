import Link from "next/link";

import DeleteDesignButton from "@/components/designs/DeleteDesignButton";
import type { Design } from "@/lib/types";
import { ui } from "@/lib/ui";

/**
 * 공유되지 않은 버전까지 받았는지. 소유자가 아닌데 이렇다면 모든 버전을 볼 수 있는 관리자 보기다
 * (다른 회원·방문자에게는 공유된 버전만 온다).
 */
export function seesUnsharedVersions(design: Design): boolean {
  return design.versions.some((v) => !design.shared_versions.includes(v.version));
}

/** 설계 화면 상단: 제목·버전·사육 환경, 소유자는 커뮤니티 공유·삭제, 다른 회원은 읽기 전용 안내 */
export default function DesignTitleBar({ design, onDeleted }: { design: Design; onDeleted?: () => void }) {
  const cur = design.current;
  const h = design.habitat;
  const shareHref = `/community/new?design=${encodeURIComponent(design.id)}&version=${cur.version}`;
  const owner = design.owner_nickname ?? "회원";
  const curShared = design.shared_versions.includes(cur.version);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
          <h1 className="min-w-0 break-words text-2xl font-bold leading-snug">{design.title || "맞춤 설계"}</h1>
          <span data-testid="design-version" className={`${ui.badge} text-sm`}>
            v{cur.version}
          </span>
          {/* 지금 보고 있는 버전이 커뮤니티 글에 첨부되어 누구나 볼 수 있는 경우 */}
          {curShared && (
            <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-teal-800">
              커뮤니티에 공유됨
            </span>
          )}
          {cur.provider === "mock" && (
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-800">개발용 모의 해석기</span>
          )}
        </div>
        {design.is_owner && (
          <div className="flex shrink-0 items-start gap-2">
            <Link href={shareHref} className={ui.btnSecondary}>
              커뮤니티에 공유
            </Link>
            {onDeleted && (
              <DeleteDesignButton
                id={design.id}
                title={design.title || "맞춤 설계"}
                versionCount={design.versions.length}
                shared={design.shared_versions.length > 0}
                onDeleted={onDeleted}
                className="self-stretch [&>button]:h-full [&>button]:px-3 [&>button]:text-sm"
              />
            )}
          </div>
        )}
      </div>
      <p className="text-sm text-stone-500">
        {h.species_name_ko} {h.size_name_ko} · {h.count}마리 · 케이지 {h.cage.width_mm}×{h.cage.depth_mm}×
        {h.cage.height_mm}mm
      </p>
      {!design.is_owner && (
        <p role="note" className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
          {/* 관리자 보기(공유되지 않은 버전도 받음)는 공유한 설계라고 하지 않고, 지금 버전이 공개인지 알려 준다 */}
          {seesUnsharedVersions(design)
            ? `${owner}님의 설계예요 (관리자 보기, 읽기 전용). ${
                curShared
                  ? `지금 보는 v${cur.version}은 커뮤니티에 공유된 버전이에요.`
                  : "공유되지 않은 버전은 다른 사람에게 보이지 않아요."
              }`
            : design.shared_versions.length > 0
              ? `${owner}님이 커뮤니티에 공유한 설계예요. 공유된 버전만 볼 수 있고, 읽기 전용이에요.`
              : `${owner}님의 설계예요. 읽기 전용이에요.`}
        </p>
      )}
    </div>
  );
}
