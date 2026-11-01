import { formatParam, PARAM_LABELS, TEMPLATE_COLORS } from "@/lib/templates";
import type { Item } from "@/lib/types";

export default function ItemList({
  items,
  selected,
  errorItems,
  onSelect,
}: {
  items: Item[];
  selected: number | null;
  errorItems: Set<number>;
  onSelect: (i: number | null) => void;
}) {
  return (
    <section aria-labelledby="items-title" className="space-y-2">
      <h2 id="items-title" className="font-bold">
        구조물 ({items.length})
      </h2>
      <ul className="space-y-2">
        {items.map((it) => {
          const active = selected === it.index;
          return (
            <li key={it.index}>
              <button
                type="button"
                onClick={() => onSelect(active ? null : it.index)}
                aria-pressed={active}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  active ? "border-amber-500 bg-amber-50" : "border-stone-200 hover:bg-stone-50"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="h-3 w-3 rounded-full"
                    style={{ background: errorItems.has(it.index) ? "#e05252" : TEMPLATE_COLORS[it.template] }}
                  />
                  <span className="font-semibold">{it.label_ko}</span>
                  <span className="ml-auto text-xs text-stone-500">
                    {it.placement ? `${it.size_mm.map((v) => Math.round(v)).join("×")}mm` : "배치 실패"}
                  </span>
                </div>
                {active && (
                  <div className="mt-2 space-y-2 text-sm">
                    <p className="text-stone-600">{it.reason_ko}</p>
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                      {Object.entries(it.params).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2">
                          <dt className="text-stone-500">{PARAM_LABELS[k] ?? k}</dt>
                          <dd className="font-medium">{formatParam(k, v)}</dd>
                        </div>
                      ))}
                    </dl>
                    <p className="text-xs text-stone-500">
                      출력 크기 {it.print_size_mm.map((v) => Math.round(v)).join("×")}mm (서포트 없이 출력하는 자세 기준)
                    </p>
                  </div>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
