"use client";

import Link from "next/link";

import { LoadError, Skeleton, useLoad } from "@/components/home/Loadable";
import { api } from "@/lib/api";
import type { DesignListItem } from "@/lib/types";
import { formatDate, ui } from "@/lib/ui";

const loadRecent = () => api.listDesigns(1, 3);

function DesignRow({ d }: { d: DesignListItem }) {
  const { cage } = d.habitat;
  return (
    <li>
      <Link
        href={`/designs/${encodeURIComponent(d.id)}`}
        className="block rounded-xl border border-stone-200 p-3 transition hover:border-amber-300 hover:bg-amber-50/60"
      >
        <div className="flex items-start justify-between gap-2">
          <p className="min-w-0 truncate font-medium">{d.title || "제목 없는 설계"}</p>
          <span className={`${ui.badge} shrink-0`}>v{d.latest_version}</span>
        </div>
        <p className="mt-1 truncate text-sm text-stone-600">
          {d.habitat.species_name_ko} · {d.habitat.size_name_ko}
          {d.pet_name && <> · {d.pet_name}</>} · {cage.width_mm}×{cage.depth_mm}×{cage.height_mm}mm
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-stone-500">
          <span>{formatDate(d.updated_at)} 수정</span>
          <span className={d.latest_passed ? "text-emerald-700" : "text-amber-800"}>
            {d.latest_passed ? "검증 통과" : "검증 문제 있음"}
          </span>
          {d.shared && <span className="text-teal-700">커뮤니티 공유됨</span>}
        </p>
      </Link>
    </li>
  );
}

/** 메인 화면: 최근 내 설계 3개 */
export default function RecentDesigns() {
  const { state, retry } = useLoad(loadRecent, "설계 내역을 불러오지 못했어요.");

  return (
    <section aria-labelledby="recent-designs-title" className={`${ui.card} flex flex-col`}>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-baseline gap-2">
          <h3 id="recent-designs-title" className={ui.h2}>
            최근 내 설계
          </h3>
          {state.kind === "ok" && state.data.total > 0 && (
            <span className="text-sm text-stone-500">총 {state.data.total}개</span>
          )}
        </div>
        <Link href="/designs" className={`${ui.link} shrink-0 text-sm font-medium`}>
          전체 내역
        </Link>
      </div>

      {state.kind === "loading" && <Skeleton rows={3} label="최근 설계를 불러오는 중이에요" />}
      {state.kind === "error" && <LoadError message={state.message} needsLogin={state.needsLogin} onRetry={retry} />}
      {state.kind === "ok" &&
        (state.data.items.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center rounded-xl bg-amber-50/70 p-6 text-center">
            <p className="font-medium">아직 만든 설계가 없어요.</p>
            <p className="mt-1 text-sm text-stone-600">케이지 크기와 원하는 구조물을 적으면 설계를 시작할 수 있어요.</p>
            <Link href="/design" className={`${ui.btnPrimary} mt-4`}>
              첫 설계 시작하기
            </Link>
          </div>
        ) : (
          <ul className="space-y-2">
            {state.data.items.map((d) => (
              <DesignRow key={d.id} d={d} />
            ))}
          </ul>
        ))}
    </section>
  );
}
