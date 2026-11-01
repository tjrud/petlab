import { Suspense } from "react";

import DesignView from "@/components/DesignView";
import Header from "@/components/Header";

/** ?version=N 이 있으면 그 버전부터 연다 (커뮤니티 글에 첨부된 버전 등). 잘못된 값은 무시하고 최신 버전 */
function parseVersion(raw: string | string[] | undefined): number | undefined {
  const n = Number(Array.isArray(raw) ? raw[0] : raw);
  return Number.isInteger(n) && n >= 1 && n <= 2 ** 31 - 1 ? n : undefined;
}

export default function DesignPage({ params, searchParams }: PageProps<"/designs/[id]">) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-6">
        <Suspense fallback={<div className="py-20 text-center text-stone-500">설계를 불러오는 중…</div>}>
          {Promise.all([params, searchParams]).then(([{ id }, sp]) => (
            <DesignView id={id} initialVersion={parseVersion(sp.version)} />
          ))}
        </Suspense>
      </main>
    </>
  );
}
