import { Suspense } from "react";

import Header from "@/components/Header";
import LoginForm from "@/components/LoginForm";

export default function LoginPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-md px-4 py-12">
        <h1 className="mb-6 text-2xl font-bold">관리자 로그인</h1>
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </main>
    </>
  );
}
