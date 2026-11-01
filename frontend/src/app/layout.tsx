import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "꼬물공방 – 햄스터 맞춤 케이지 구조물 설계",
  description:
    "사육 환경과 요구사항을 입력하면 AI가 케이지 구조물을 맞춤 설계하고 3D 프린팅 파일(STL·3MF)을 만들어 드립니다.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
