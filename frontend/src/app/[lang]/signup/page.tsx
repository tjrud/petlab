import type { Metadata } from "next";
import { Suspense } from "react";

import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import SignupForm from "@/components/SignupForm";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("회원가입") };
}

export default async function SignupPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-md px-4 py-8 sm:py-12">
        <h1 className={`${ui.h1} mb-6`}>{t("회원가입")}</h1>
        <Suspense fallback={null}>
          <SignupForm />
        </Suspense>
      </main>
    </>
  );
}
