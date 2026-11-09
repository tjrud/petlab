import type { Metadata } from "next";

import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import MyInfo from "@/components/me/MyInfo";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("내 정보") };
}

export default async function MePage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <h1 className={`${ui.h1} mb-6`}>{t("내 정보")}</h1>
        <MyInfo />
      </main>
    </>
  );
}
