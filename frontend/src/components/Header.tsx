import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";

import AuthMenu from "@/components/AuthMenu";
import { EmailVerifyBanner } from "@/components/EmailVerification";
import NavLinks from "@/components/NavLinks";

export default function Header() {
  return (
    <>
      <header className="sticky top-0 z-20 border-b border-amber-200/70 bg-white/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex shrink-0 items-center" aria-label="NestForge 홈">
              {/* 로고는 글자까지 도형으로 된 SVG (brand/README.md). 비율을 바꾸지 않도록 높이만 지정한다 */}
              <Image
                src="/logo/logo-on-light.svg"
                alt="NestForge"
                width={622}
                height={155}
                priority
                unoptimized
                className="h-8 w-auto sm:h-9"
              />
            </Link>
            <Suspense fallback={null}>
              <NavLinks part="main" className="hidden md:block" />
            </Suspense>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <Suspense fallback={null}>
              <NavLinks part="me" className="hidden md:block" />
            </Suspense>
            <AuthMenu />
          </div>
        </div>
        <Suspense fallback={null}>
          <NavLinks className="border-t border-amber-100 px-2 py-1.5 md:hidden" />
        </Suspense>
      </header>
      {/* 이메일 인증 전인 회원에게만 보이는 안내 (헤더와 달리 따라 내려오지 않는다) */}
      <EmailVerifyBanner />
    </>
  );
}
