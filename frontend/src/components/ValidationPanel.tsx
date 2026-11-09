import { useT } from "@/i18n/client";
import type { HabitatKind, Issue, Item, Validation } from "@/lib/types";

const GROUPS = [
  { key: "error", title: "해결이 필요한 문제", tone: "border-red-200 bg-red-50 text-red-800" },
  { key: "warning", title: "주의", tone: "border-amber-200 bg-amber-50 text-amber-900" },
  { key: "fixed", title: "자동 보정한 내용", tone: "border-sky-200 bg-sky-50 text-sky-900" },
  // 보정이 아닌 참고 안내 (어항: 물속 무게, 터널 공기 빼기). 케이지 설계에는 나오지 않는다
  { key: "note", title: "참고", tone: "border-stone-200 bg-stone-50 text-stone-800" },
] as const;

/** 고칠 것도 보정한 것도 아닌 참고 안내 */
const isNote = (i: Issue) => i.severity === "info" && !i.auto_fixed;

function groupOf(i: Issue): (typeof GROUPS)[number]["key"] {
  if (i.auto_fixed) return "fixed";
  return i.severity === "error" ? "error" : i.severity === "warning" ? "warning" : "note";
}

export default function ValidationPanel({
  validation,
  items,
  onSelect,
  kind = "cage",
}: {
  validation: Validation;
  items: Item[];
  onSelect: (i: number | null) => void;
  /** 사육 환경 종류 (어항이면 수조 기준으로 확인한 항목을 알린다). 없으면 케이지 */
  kind?: HabitatKind;
}) {
  const t = useT();
  const labelOf = (idx: number | null) => items.find((it) => it.index === idx)?.label_ko;
  // 참고 안내만 있으면 문제·보정이 없는 것과 같다 (어항 설계는 물속 무게 안내가 늘 붙는다)
  const clean = validation.issues.every(isNote);
  return (
    <section aria-labelledby="validation-title" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="validation-title" className="font-bold">
          {t("안전·출력 검증")}
        </h2>
        {validation.passed ? (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">{t("통과")}</span>
        ) : (
          <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-800">
            {t("문제 {n}건", { n: validation.summary.errors })}
          </span>
        )}
      </div>
      {clean && (
        <p className="text-sm text-stone-600">
          {kind === "aquarium"
            ? t("수조 적합, 물 깊이, 겹침, 끼임 틈새, 벽 두께, 넘어짐, 서포트 없는 출력을 모두 확인했어요.")
            : t("케이지 적합, 겹침, 끼임 틈새, 벽 두께, 서포트 없는 출력을 모두 확인했어요.")}
        </p>
      )}
      {GROUPS.map((g) => {
        const list = validation.issues.filter((i) => groupOf(i) === g.key);
        if (!list.length) return null;
        return (
          <div key={g.key} className={`rounded-xl border p-3 ${g.tone}`}>
            <h3 className="mb-2 text-sm font-semibold">
              {t(g.title)} ({list.length})
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
