import type { Metadata } from "next";
import { Suspense } from "react";

import Header from "@/components/Header";
import SignupForm from "@/components/SignupForm";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "회원가입" };

export default function SignupPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-md px-4 py-8 sm:py-12">
        <h1 className={`${ui.h1} mb-6`}>회원가입</h1>
        <Suspense fallback={null}>
          <SignupForm />
        </Suspense>
      </main>
    </>
  );
}
