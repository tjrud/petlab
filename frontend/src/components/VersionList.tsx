import type { VersionSummary } from "@/lib/types";

export default function VersionList({
  versions,
  current,
  loading,
  onPick,
}: {
  versions: VersionSummary[];
  current: number;
  loading: boolean;
  onPick: (v: number) => void;
}) {
  const latest = versions[versions.length - 1]?.version;
  return (
    <section aria-labelledby="versions-title" className="space-y-2">
      <h2 id="versions-title" className="font-bold">
        설계 버전 ({versions.length})
      </h2>
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
                {v.version === latest && <span className="text-xs text-stone-400">최신</span>}
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
