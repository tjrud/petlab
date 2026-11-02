"use client";

import type { LayoutReport } from "@/lib/cageLayout";

/** 배치 검토 결과: 오류·경고 수, 바닥 사용 비율, 문제 목록 (누르면 그 구조물을 선택해요) */
export default function ReviewPanel({
  report,
  itemCount,
  rulesLoaded,
  rulesReviewed,
  onPick,
}: {
  report: LayoutReport;
  itemCount: number;
  rulesLoaded: boolean;
  rulesReviewed: boolean;
  onPick: (id: string) => void;
}) {
  const errors = report.issues.filter((i) => i.severity === "error").length;
  const warnings = report.issues.length - errors;
  const pct = Math.round(report.coverage * 100);
  return (
    <section aria-labelledby="review-title" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="review-title" className="text-base font-semibold">
          배치 검토
        </h2>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${errors ? "bg-red-100 text-red-800" : "bg-stone-100 text-stone-600"}`}>
          오류 {errors}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${warnings ? "bg-amber-100 text-amber-900" : "bg-stone-100 text-stone-600"}`}>
          경고 {warnings}
        </span>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-600" title="구조물이 차지한 바닥 면적 ÷ 케이지 바닥 면적">
          바닥 사용 {pct}%
        </span>
      </div>

      {itemCount === 0 ? (
        <p className="text-sm text-stone-500">카탈로그에서 구조물을 골라 케이지에 놓아 보세요. 놓는 대로 겹침·끼임 틈·출입구 공간을 확인해 드려요.</p>
      ) : report.issues.length === 0 ? (
        <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          ✅ 겹치거나 케이지 밖으로 나간 구조물이 없고, 끼임 틈·출입구 공간도 기준에 맞아요.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {report.issues.map((i) => (
            <li key={i.key}>
              <button
                type="button"
                onClick={() => i.itemIds[0] && onPick(i.itemIds[0])}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                  i.severity === "error" ? "bg-red-50 text-red-800 hover:bg-red-100" : "bg-amber-50 text-amber-900 hover:bg-amber-100"
                }`}
              >
                {i.severity === "error" ? "⛔ " : "⚠️ "}
                {i.message}
              </button>
            </li>
          ))}
        </ul>
      )}

      {report.unknownAssets.length > 0 && (
        <p className="text-xs text-stone-500">카탈로그에서 빠진 구조물 {report.unknownAssets.length}개는 화면에 표시하지 않았어요.</p>
      )}
      <p className="text-xs text-stone-500">
        {rulesLoaded
          ? `끼임 틈·출입구·높이 기준은 선택한 종·크기의 규칙을 따라요.${rulesReviewed ? "" : " 규칙은 아직 전문가 검수 전 임시값이에요."}`
          : "종별 기준을 불러오지 못해 겹침·케이지 밖·높이만 확인했어요."}{" "}
        3D 프린팅용 구조물 설계는 AI 맞춤 설계에서 할 수 있어요.
      </p>
    </section>
  );
}
