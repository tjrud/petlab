import { Suspense } from "react";

import DesignView from "@/components/DesignView";
import Header from "@/components/Header";

export default function DesignPage({ params }: PageProps<"/designs/[id]">) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-6">
        <Suspense fallback={<div className="py-20 text-center text-stone-500">설계를 불러오는 중…</div>}>
          {params.then(({ id }) => (
            <DesignView id={id} />
          ))}
        </Suspense>
      </main>
    </>
  );
}
