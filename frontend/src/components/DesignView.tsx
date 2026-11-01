"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";

import DownloadPanel from "@/components/DownloadPanel";
import ItemList from "@/components/ItemList";
import ValidationPanel from "@/components/ValidationPanel";
import { api, ApiError } from "@/lib/api";
import type { Design } from "@/lib/types";

const CageViewer = dynamic(() => import("@/components/CageViewer"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-stone-500">3D 뷰어 준비 중…</div>,
});

export default function DesignView({ id }: { id: string }) {
  const [design, setDesign] = useState<Design | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getDesign(id)
      .then((d) => {
        if (alive) setDesign(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof ApiError ? e.messageKo : "설계를 불러오지 못했어요.");
      });
    return () => {
      alive = false;
    };
  }, [id]);

  const errorItems = new Set<number>(
    (design?.current.validation.issues ?? [])
      .filter((i) => i.severity === "error" && !i.auto_fixed && i.item_index !== null)
      .map((i) => i.item_index as number),
  );

  if (error && !design) {
    return (
      <div className="mx-auto max-w-xl rounded-2xl bg-red-50 p-6 text-red-800">
        <p>{error}</p>
        <Link href="/" className="mt-3 inline-block underline">
          처음으로
        </Link>
      </div>
    );
  }
  if (!design) {
    return <div className="py-20 text-center text-stone-500">설계를 불러오는 중…</div>;
  }

  const cur = design.current;
  const h = design.habitat;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-2xl font-bold">맞춤 설계 v{cur.version}</h1>
          <span className="text-sm text-stone-500">
            {h.species_name_ko} {h.size_name_ko} · {h.count}마리 · 케이지 {h.cage.width_mm}×{h.cage.depth_mm}×
            {h.cage.height_mm}mm
          </span>
          {cur.provider === "mock" && (
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-800">개발용 모의 해석기</span>
          )}
        </div>
        <div
          data-testid="viewer"
          className="h-[420px] overflow-hidden rounded-2xl border border-amber-200 bg-white sm:h-[560px]"
        >
          <CageViewer
            cage={h.cage}
            items={cur.items}
            selected={selected}
            errorItems={errorItems}
            onSelect={setSelected}
          />
        </div>
        <p className="text-xs text-stone-500">드래그로 회전, 휠로 확대·축소, 구조물을 누르면 상세 정보를 볼 수 있어요.</p>
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <p className="text-xs font-medium text-stone-500">요청</p>
          <p className="mt-1">{cur.prompt}</p>
          <p className="mt-3 text-xs font-medium text-stone-500">설계 설명</p>
          <p className="mt-1 leading-relaxed">{cur.summary_ko}</p>
          {cur.notes_ko.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm text-stone-600">
              {cur.notes_ko.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <aside className="space-y-6 rounded-2xl border border-stone-200 bg-white p-4">
        <ValidationPanel validation={cur.validation} items={cur.items} onSelect={setSelected} />
        <ItemList items={cur.items} selected={selected} errorItems={errorItems} onSelect={setSelected} />
        <DownloadPanel
          designId={design.id}
          version={cur.version}
          allowed={cur.export_allowed}
          partCount={cur.items.length}
        />
      </aside>
    </div>
  );
}
