import type { Metadata } from "next";
import { Suspense } from "react";

import Header from "@/components/Header";
import LoginForm from "@/components/LoginForm";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "로그인" };

export default function LoginPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-md px-4 py-8 sm:py-12">
        <h1 className={`${ui.h1} mb-6`}>로그인</h1>
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </main>
    </>
  );
}
