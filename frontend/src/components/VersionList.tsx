import type { VersionSummary } from "@/lib/types";

export default function VersionList({
  versions,
  current,
  loading,
  onPick,
  isOwner,
  sharedVersions,
}: {
  versions: VersionSummary[];
  current: number;
  loading: boolean;
  onPick: (v: number) => void;
  /** 소유자에게는 모든 버전, 다른 사람에게는 커뮤니티에 공유된 버전만 온다 */
  isOwner: boolean;
  /** 커뮤니티 글에 첨부된 버전 (소유자 화면에 "공유됨"으로 표시) */
  sharedVersions: number[];
}) {
  const latest = versions[versions.length - 1]?.version;
  const shared = new Set(sharedVersions);
  return (
    <section aria-labelledby="versions-title" className="space-y-2">
      <h2 id="versions-title" className="font-bold">
        {isOwner ? "설계 버전" : "공유된 설계 버전"} ({versions.length})
      </h2>
      {!isOwner && <p className="text-xs text-stone-500">커뮤니티 글에 첨부된 버전만 볼 수 있어요.</p>}
      <ol className="space-y-1.5">
        {[...versions].reverse().map((v) => {
          const active = v.version === current;
          return (
            <li key={v.version}>
              <button
                type="button"
                disabled={loading || active}
                onClick={() => onPick(v.version)}
                aria-current={active ? "true" : undefined}
                className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm ${
                  active ? "border-amber-500 bg-amber-50" : "border-stone-200 hover:bg-stone-50"
                }`}
              >
                <span className="font-semibold">v{v.version}</span>
                <span className="min-w-0 flex-1 truncate text-stone-600">{v.prompt}</span>
                {isOwner && shared.has(v.version) && (
                  <span className="shrink-0 rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-teal-800">
                    공유됨
                  </span>
                )}
                {isOwner && v.version === latest && <span className="shrink-0 text-xs text-stone-400">최신</span>}
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${v.passed ? "bg-emerald-500" : "bg-red-500"}`}
                  title={v.passed ? "검증 통과" : "검증 문제 있음"}
                />
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
