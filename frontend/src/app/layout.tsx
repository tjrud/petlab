import type { Metadata } from "next";
import "./globals.css";

import { AuthProvider } from "@/components/AuthProvider";

const DESCRIPTION =
  "사육 환경과 요구사항을 입력하면 AI가 케이지 구조물을 맞춤 설계하고 3D 프린팅 파일(STL·3MF)을 만들어 드립니다.";

export const metadata: Metadata = {
  title: { default: "NestForge – 햄스터 맞춤 케이지 구조물 설계", template: "%s · NestForge" },
  description: DESCRIPTION,
  applicationName: "NestForge",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  // 공유 미리보기 이미지는 app/opengraph-image.png (Next 파일 규칙)
  openGraph: { siteName: "NestForge", title: "NestForge", description: DESCRIPTION, locale: "ko_KR", type: "website" },
  twitter: { card: "summary_large_image" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
