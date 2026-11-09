import type { Metadata } from "next";
import { Suspense } from "react";

import Header from "@/components/Header";
import { getT } from "@/i18n/server";
import VerifyEmail, { VerifyEmailPlaceholder } from "@/components/VerifyEmail";
import { ui } from "@/lib/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return {
    title: t("이메일 인증"),
    robots: { index: false },
    // 주소의 인증 토큰이 다른 사이트로 넘어가지 않게 한다
    referrer: "no-referrer",
  };
}

export default async function VerifyEmailPage() {
  const t = await getT();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-md px-4 py-8 sm:py-12">
        <h1 className={`${ui.h1} mb-6`}>{t("이메일 인증")}</h1>
        {/* 주소의 ?token= 을 읽으므로(useSearchParams) Suspense 안에서 그린다 */}
        <Suspense fallback={<VerifyEmailPlaceholder />}>
          <VerifyEmail />
        </Suspense>
      </main>
    </>
  );
}
