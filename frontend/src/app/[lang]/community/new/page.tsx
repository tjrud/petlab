import type { Metadata } from "next";
import { Link } from "@/i18n/client";
import { Suspense } from "react";

import NewPostForm, { NewPostPlaceholder } from "@/components/community/NewPostForm";
import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("글쓰기") };
}

export default async function NewPostPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mx-auto max-w-3xl">
          <Link href="/community" className={`${ui.link} text-sm font-medium`}>
            <span aria-hidden>← </span>
            {t("목록으로")}
          </Link>
          <h1 className={`${ui.h1} mb-6 mt-2`}>{t("글쓰기")}</h1>
          <Suspense fallback={<NewPostPlaceholder />}>
            <NewPostForm />
          </Suspense>
        </div>
      </main>
    </>
  );
}
