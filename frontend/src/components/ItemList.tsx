import { useLang, useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { isLibraryKey } from "@/lib/libraryDisplay";
import { useLibraryDisplay } from "@/lib/useLibraryDisplay";
import {
  describeDecor,
  describeJoin,
  flattenParams,
  formatParam,
  itemColor,
  type ParamValue,
  paramLabel,
  partNoticeTag,
  templateColor,
} from "@/lib/templates";
import type { AssemblyItem, Issue, Item } from "@/lib/types";

/** 파라미터 이름·값 표 (집 템플릿의 중첩 값은 점 표기로 펼친다). template: 라이브러리 부품의 이름을 찾는 키 */
function ParamGrid({ params, t, template }: { params: Record<string, ParamValue>; t: TFunction; template: string }) {
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
      {flattenParams(params).map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2">
          <dt className="text-stone-500">{paramLabel(k, t, template)}</dt>
          <dd className="font-medium">{formatParam(k, v, t, template)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * 조립 항목: 부품마다 색 점·이름·파라미터, 그 부품에 붙은 안내(info, details.part),
 * 그리고 결합마다 한 줄 ("그릇 받침 → 은신처 오른쪽 · 슬라이드 끼움").
 */
function AssemblyDetails({ item, issues, t }: { item: AssemblyItem; issues: Issue[]; t: TFunction }) {
  const { parts, joins } = item.assembly;
  const names = Object.fromEntries(parts.map((p) => [p.id, p.name_ko]));
  const notices = issues.filter((i) => i.item_index === item.index && i.severity === "info");
  return (
    <div className="space-y-2" data-testid="assembly-parts">
      <p className="text-xs font-medium text-stone-500">{t("부품 {n}개", { n: parts.length })}</p>
      {parts.map((part) => {
        const notes = notices.filter((i) => i.details?.part === part.id);
        return (
          <div key={part.id} className="rounded-lg border border-stone-200 p-2" data-testid={`assembly-part-${part.id}`}>
            <p className="mb-1 flex items-center gap-2 font-medium">
              <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: templateColor(part.template) }} />
              {part.name_ko}
            </p>
            <ParamGrid params={item.params[part.id] ?? {}} t={t} template={part.template} />
            {notes.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-xs text-sky-900">
                {notes.map((i, n) => {
                  const tag = partNoticeTag(i.code, t);
                  return (
                    <li key={`${i.code}-${n}`}>
                      {tag && <span className="mr-1 rounded bg-sky-100 px-1 font-medium">{tag}</span>}
                      {i.message_ko}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
      {joins.length > 0 && (
        <div className="text-xs text-stone-600" data-testid="assembly-joins">
          <p className="font-medium text-stone-500">{t("연결")}</p>
          <ul className="mt-0.5 list-disc pl-4">
            {joins.map((j) => (
              <li key={`${j.part}-${j.to}`}>{describeJoin(j, names, t)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ItemList({
  items,
  selected,
  errorItems,
  onSelect,
  issues = [],
}: {
  items: Item[];
  selected: number | null;
  errorItems: Set<number>;
  onSelect: (i: number | null) => void;
  /** 검증 이슈 (조립 항목의 부품 안내를 그 부품 옆에 보인다). 없으면 보이지 않는다 */
  issues?: Issue[];
}) {
  const t = useT();
  const lang = useLang();
  // 라이브러리 부품이 있으면 표시 정보(이름·색)를 받아 다시 그린다
  useLibraryDisplay(
    items.some((it) => isLibraryKey(it.template) || !!it.assembly?.parts.some((p) => isLibraryKey(p.template))),
    lang,
  );
  return (
    <section aria-labelledby="items-title" className="space-y-2">
      <h2 id="items-title" className="font-bold">
        {t("구조물 ({n})", { n: items.length })}
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
                    style={{ background: errorItems.has(it.index) ? "#e05252" : itemColor(it) }}
                  />
                  <span className="font-semibold">{it.label_ko}</span>
                  <span className="ml-auto text-xs text-stone-500">
                    {it.placement ? `${it.size_mm.map((v) => Math.round(v)).join("×")}mm` : t("배치 실패")}
                  </span>
                </div>
                {active && (
                  <div className="mt-2 space-y-2 text-sm">
                    <p className="text-stone-600">{it.reason_ko}</p>
                    {it.decor && (
                      <p className="rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-900" data-testid="decor-summary">
                        {t("장식")}: {describeDecor(it.decor, t)}
                      </p>
                    )}
                    {it.assembly ? (
                      <AssemblyDetails item={it} issues={issues} t={t} />
                    ) : (
                      <ParamGrid params={it.params} t={t} template={it.template} />
                    )}
                    {(it.parts?.length ?? 1) > 1 ? (
                      <div className="text-xs text-stone-500">
                        <p>{t("출력 파트 {n}개 (서포트 없이 출력하는 자세 기준)", { n: it.parts!.length })}</p>
                        <ul className="mt-0.5 list-disc pl-4">
                          {it.parts!.map((part) => (
                            <li key={part.key}>
                              {t(part.name_ko)} {part.size_mm.map((v) => Math.round(v)).join("×")}mm
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <p className="text-xs text-stone-500">
                        {t("출력 크기 {size}mm (서포트 없이 출력하는 자세 기준)", {
                          size: it.print_size_mm.map((v) => Math.round(v)).join("×"),
                        })}
                      </p>
                    )}
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
