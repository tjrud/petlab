import Image from "next/image";
import Link from "next/link";

import AuthMenu from "@/components/AuthMenu";

export default function Header() {
  return (
    <header className="border-b border-amber-200/70 bg-white/70 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center" aria-label="NestForge 홈">
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
        <div className="flex items-center gap-4">
          <span className="hidden text-sm text-stone-500 sm:block">햄스터 맞춤 케이지 구조물 설계</span>
          <AuthMenu />
        </div>
      </div>
    </header>
  );
}
