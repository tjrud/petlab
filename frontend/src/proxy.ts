// 언어별 주소: 한국어는 지금 주소 그대로(/design), 영어는 /en/design.
// 앱 경로는 app/[lang]/... 이므로 접두어 없는 주소는 /ko/... 로 이어 준다(rewrite, 주소창은 그대로).
// 영어를 고른 사람(쿠키 lang=en)이 접두어 없는 주소로 오면 /en/... 으로 보낸다.

import { type NextRequest, NextResponse } from "next/server";

import { LANG_COOKIE } from "@/i18n/config";

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  // /ko/... 를 직접 열면 접두어 없는 주소로 (같은 화면이 두 주소를 갖지 않게)
  if (pathname === "/ko" || pathname.startsWith("/ko/")) {
    const url = request.nextUrl.clone();
    url.pathname = pathname.slice(3) || "/";
    return NextResponse.redirect(url, 308);
  }
  if (pathname === "/en" || pathname.startsWith("/en/")) return NextResponse.next();
  if (request.cookies.get(LANG_COOKIE)?.value === "en") {
    const url = request.nextUrl.clone();
    url.pathname = pathname === "/" ? "/en" : `/en${pathname}`;
    return NextResponse.redirect(url, 307);
  }
  const url = request.nextUrl.clone();
  url.pathname = `/ko${pathname === "/" ? "" : pathname}`;
  url.search = search;
  return NextResponse.rewrite(url);
}

export const config = {
  // Next 내부 파일, API, 확장자가 있는 정적 파일(favicon.svg, logo/*.svg 등)은 건너뛴다
  matcher: ["/((?!_next/|api/|.*\\.[A-Za-z0-9]+$).*)"],
};
