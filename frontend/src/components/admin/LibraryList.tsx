"use client";

import RetryAlert from "@/components/RetryAlert";
import { useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import type { LibraryEntry, LibraryList as LibraryListData, LibraryRole, LibraryStatus } from "@/lib/types";
import { formatDateTime, ui } from "@/lib/ui";

// 관리자 화면의 부품 라이브러리 (읽기 전용, GET /admin/library).
// 게시·폐기·차단은 개발 도구(python -m app.library)로만 하고, 여기서는 무엇이 있는지와 마지막 검증 결과를 본다.

export type LibraryState = { kind: "ok"; data: LibraryListData } | { kind: "error"; message: string } | null;

export function roleLabel(t: TFunction, role: LibraryRole): string {
  switch (role) {
    case "host":
      return t("받침 부품");
    case "room_host":
      return t("방 부품");
    case "accessory":
      return t("붙이는 부품");
    default:
      return t("단독 부품");
  }
}

export function libraryStatusLabel(t: TFunction, status: LibraryStatus): string {
  return status === "active" ? t("쓰는 중") : status === "retired" ? t("새 설계에 쓰지 않음") : t("내려받기 막음");
}

const STATUS_BADGE: Record<LibraryStatus, string> = {
  active: "bg-emerald-100 text-emerald-900",
  retired: "bg-stone-200 text-stone-700",
  blocked: "bg-red-100 text-red-800",
};

/** 마지막 검증: 결과·날짜·검사 수, 스키마 예산을 넘는 종 */
function ReportCell({ entry }: { entry: LibraryEntry }) {
  const t = useT();
  const r = entry.report;
  if (!r) return <span className="text-stone-400">{t("검증 기록 없음")}</span>;
  const over = Object.entries(r.gate_ok)
    .filter(([, ok]) => !ok)
    .map(([sp]) => sp);
  return (
    <div className="space-y-0.5 text-xs text-stone-600">
      <p>
        <span
          className={`mr-1 rounded-full px-2 py-0.5 font-medium ${
            r.result === "pass" ? "bg-emerald-100 text-emerald-900" : "bg-red-100 text-red-800"
          }`}
        >
          {r.result === "pass" ? t("통과") : t("실패")}
        </span>
        {r.profile === "full" ? t("전체 검증") : r.profile === "quick" ? t("빠른 검증") : r.profile}
      </p>
      {r.started_at && <p>{formatDateTime(r.started_at)}</p>}
      {r.checks !== null && <p>{t("검사 {n}개 · 실패 {f}개", { n: r.checks, f: r.failed ?? 0 })}</p>}
      {over.length > 0 && <p className="text-amber-800">{t("스키마 예산 초과: {species}", { species: over.join(", ") })}</p>}
    </div>
  );
}

export default function LibraryList({
  state,
  onRetry,
  speciesLabel,
}: {
  state: LibraryState;
  onRetry: () => void;
  speciesLabel: (key: string) => string;
}) {
  const t = useT();
  let body: React.ReactNode;
  if (!state) {
    body = (
      <p role="status" className={ui.muted}>
        {t("부품 라이브러리를 불러오는 중…")}
      </p>
    );
  } else if (state.kind === "error") {
    body = <RetryAlert message={state.message} onRetry={onRetry} />;
  } else {
    const { parts, problems } = state.data;
    body = (
      <>
        {problems.length > 0 && (
          <div role="alert" className={`${ui.error} mb-3`}>
            <p className="font-medium">{t("색인과 파일이 맞지 않는 곳이 있어요. audit 으로 확인해 주세요.")}</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {problems.map((p) => (
                <li key={p} className="break-words">
                  {p}
                </li>
              ))}
            </ul>
          </div>
        )}
        {parts.length === 0 ? (
          <div className={`${ui.card} text-center`}>
            <p className="font-medium">{t("게시한 부품이 아직 없어요.")}</p>
          </div>
        ) : (
          <div className="relative overflow-x-auto rounded-2xl border border-stone-200 bg-white">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead className="border-b border-stone-200 bg-stone-50 text-xs text-stone-500">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">{t("부품")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("역할")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("공개 상태")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("검증한 종·크기")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("채우는 요청")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("게시일")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("마지막 검증")}</th>
                </tr>
              </thead>
              <tbody>
                {parts.map((p) => {
                  const sizes = Object.entries(p.verified_for).flatMap(([sp, list]) => list.map((sz) => `${sp}/${sz}`));
                  return (
                    <tr key={p.key} className="border-b border-stone-100 align-top last:border-b-0">
                      <th scope="row" className="px-3 py-3 font-medium">
                        <span className="block">{p.name_ko}</span>
                        <span className="block font-mono text-xs font-normal text-stone-500">{p.key}</span>
                      </th>
                      <td className="whitespace-nowrap px-3 py-3 text-stone-700">{roleLabel(t, p.role)}</td>
                      <td className="px-3 py-3">
                        <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[p.status]}`}>
                          {libraryStatusLabel(t, p.status)}
                        </span>
                        {p.reason_ko && <span className="mt-1 block max-w-[14rem] break-words text-xs text-stone-500">{p.reason_ko}</span>}
                        {p.superseded_by && (
                          <span className="mt-1 block text-xs text-stone-500">
                            {t("새 판: {key}", { key: p.superseded_by })}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        {sizes.length > 0 ? (
                          <ul className="flex flex-wrap gap-1">
                            {sizes.map((k) => (
                              <li key={k} className="whitespace-nowrap rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-700">
                                {speciesLabel(k)}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-stone-400">—</span>
                        )}
                      </td>
                      <td className="max-w-[14rem] px-3 py-3 text-xs text-stone-600">
                        {p.fulfills.length > 0 ? p.fulfills.join(", ") : <span className="text-stone-400">—</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-xs text-stone-600">{p.published_at}</td>
                      <td className="min-w-[11rem] px-3 py-3">
                        <ReportCell entry={p} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }
  return (
    <section aria-labelledby="library-title" className="space-y-3 border-t border-stone-200 pt-6">
      <div>
        <h2 id="library-title" className="text-lg font-bold">
          {t("부품 라이브러리")}
        </h2>
        <p className={`${ui.muted} mt-1`}>
          {t("게시한 부품이에요. 게시·폐기·차단은 개발 도구로만 하고, 여기서는 보기만 해요.")}
        </p>
      </div>
      {body}
    </section>
  );
}
