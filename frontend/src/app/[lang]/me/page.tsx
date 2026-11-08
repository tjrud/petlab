import type { Metadata } from "next";

import Header from "@/components/Header";
import MyInfo from "@/components/me/MyInfo";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "내 정보" };

export default function MePage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <h1 className={`${ui.h1} mb-6`}>내 정보</h1>
        <MyInfo />
      </main>
    </>
  );
}
