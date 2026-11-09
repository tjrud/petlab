import type { Metadata } from "next";
import { notFound } from "next/navigation";
import "../globals.css";

import { AuthProvider } from "@/components/AuthProvider";
import { isLang, LANGS } from "@/i18n/config";
import { LangProvider } from "@/i18n/client";
import { getLang, getT } from "@/i18n/server";

// 한국어(/...)·영어(/en/...) 두 벌을 미리 만든다. 한국어 주소는 proxy 가 /ko/... 로 이어 준다
export async function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

export async function generateMetadata(): Promise<Metadata> {
  const lang = await getLang();
  const t = await getT();
  const description = t("햄스터 케이지 치수에 맞춘 은신처·터널·경사로·모래목욕통 설계와 3D 프린팅 파일(STL·3MF).");
  return {
    title: { default: t("NestForge – 햄스터 맞춤 케이지 구조물 설계"), template: "%s · NestForge" },
    description,
    applicationName: "NestForge",
    icons: {
      icon: [
        { url: "/favicon.svg", type: "image/svg+xml" },
        { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      ],
      apple: "/apple-touch-icon.png",
    },
    // 공유 미리보기 이미지는 app/[lang]/opengraph-image.png (Next 파일 규칙)
    openGraph: {
      siteName: "NestForge",
      title: "NestForge",
      description,
      locale: lang === "en" ? "en_US" : "ko_KR",
      type: "website",
    },
    twitter: { card: "summary_large_image" },
    alternates: { languages: { ko: "/", en: "/en" } },
  };
}

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return (
    <html lang={lang} className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <LangProvider lang={lang}>
          <AuthProvider>{children}</AuthProvider>
        </LangProvider>
      </body>
    </html>
  );
}
