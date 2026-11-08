import { Suspense } from "react";

import Header from "@/components/Header";
import WaitlistForm from "@/components/WaitlistForm";
import { getT } from "@/i18n/server";

export default async function OrderPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-xl px-4 py-10">
        <h1 className="mb-6 text-2xl font-bold">{t("제작·배송 신청")}</h1>
        <Suspense fallback={null}>
          <WaitlistForm />
        </Suspense>
      </main>
    </>
  );
}
