import type { Issue, Item, Validation } from "@/lib/types";

const GROUPS = [
  { key: "error", title: "해결이 필요한 문제", tone: "border-red-200 bg-red-50 text-red-800" },
  { key: "warning", title: "주의", tone: "border-amber-200 bg-amber-50 text-amber-900" },
  { key: "fixed", title: "자동 보정한 내용", tone: "border-sky-200 bg-sky-50 text-sky-900" },
] as const;

function groupOf(i: Issue): (typeof GROUPS)[number]["key"] {
  if (i.auto_fixed) return "fixed";
  return i.severity === "error" ? "error" : i.severity === "warning" ? "warning" : "fixed";
}

export default function ValidationPanel({
  validation,
  items,
  onSelect,
}: {
  validation: Validation;
  items: Item[];
  onSelect: (i: number | null) => void;
}) {
  const labelOf = (idx: number | null) => items.find((it) => it.index === idx)?.label_ko;
  return (
    <section aria-labelledby="validation-title" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="validation-title" className="font-bold">
          안전·출력 검증
        </h2>
        {validation.passed ? (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">통과</span>
        ) : (
          <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-800">
            문제 {validation.summary.errors}건
          </span>
        )}
      </div>
      {validation.issues.length === 0 && (
        <p className="text-sm text-stone-600">케이지 적합, 겹침, 끼임 틈새, 벽 두께, 서포트 없는 출력을 모두 확인했어요.</p>
      )}
      {GROUPS.map((g) => {
        const list = validation.issues.filter((i) => groupOf(i) === g.key);
        if (!list.length) return null;
        return (
          <div key={g.key} className={`rounded-xl border p-3 ${g.tone}`}>
            <h3 className="mb-2 text-sm font-semibold">
              {g.title} ({list.length})
            </h3>
            <ul className="space-y-1.5 text-sm">
              {list.map((i, n) => (
                <li key={`${i.code}-${n}`}>
                  {i.item_index !== null && labelOf(i.item_index) ? (
                    <button type="button" className="text-left hover:underline" onClick={() => onSelect(i.item_index)}>
                      {i.message_ko}
                    </button>
                  ) : (
                    i.message_ko
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
