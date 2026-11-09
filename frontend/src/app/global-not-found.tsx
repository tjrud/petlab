// 어떤 경로에도 맞지 않는 주소의 404 (뿌리 레이아웃이 app/[lang] 안에 있어 따로 둔다: next.config experimental.globalNotFound).
// 언어를 알 수 없으므로 한국어·영어를 함께 보인다.
import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "페이지를 찾을 수 없어요 · Page not found · NestForge",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default function GlobalNotFound() {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="flex min-h-full flex-col items-center justify-center gap-6 px-4 py-16 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element -- 404 는 이미지 최적화 없이 가볍게 */}
        <img src="/logo/logo-on-light.svg" alt="NestForge" width={180} height={45} />
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">페이지를 찾을 수 없어요</h1>
          <p className="text-stone-600">주소가 바뀌었거나 없는 페이지예요.</p>
        </div>
        <div className="space-y-2" lang="en">
          <h2 className="text-xl font-semibold">Page not found</h2>
          <p className="text-stone-600">This page doesn&apos;t exist or has moved.</p>
        </div>
        <div className="flex gap-3">
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- 뿌리 레이아웃 밖이라 일반 링크 */}
          <a href="/" className="rounded-xl bg-amber-500 px-5 py-2.5 font-semibold text-white hover:bg-amber-600">
            홈으로
          </a>
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a href="/en" lang="en" className="rounded-xl border border-stone-300 bg-white px-5 py-2.5 font-semibold hover:bg-stone-50">
            Go home
          </a>
        </div>
      </body>
    </html>
  );
}
