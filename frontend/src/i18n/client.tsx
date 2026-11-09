"use client";

// 클라이언트 컴포넌트용: 지금 언어·번역 함수·언어를 붙이는 Link·router·pathname.
// 언어는 app/[lang]/layout.tsx 의 LangProvider 가 내려 준다.

import NextLink from "next/link";
import { usePathname as useNextPathname, useRouter as useNextRouter } from "next/navigation";
import { type ComponentProps, createContext, useContext, useMemo } from "react";

import { DEFAULT_LANG, INTL_LOCALE, type Lang, stripLang, withLang } from "@/i18n/config";
import { makeT, type TFunction } from "@/i18n/translate";

const LangContext = createContext<Lang>(DEFAULT_LANG);

export function LangProvider({ lang, children }: { lang: Lang; children: React.ReactNode }) {
  return <LangContext.Provider value={lang}>{children}</LangContext.Provider>;
}

export function useLang(): Lang {
  return useContext(LangContext);
}

/** 번역 함수 t(한국어 원문, 자리표시 값) */
export function useT(): TFunction {
  const lang = useLang();
  return useMemo(() => makeT(lang), [lang]);
}

/** 날짜·숫자 형식용 로캘 ("ko-KR" / "en-US") */
export function useLocale(): string {
  return INTL_LOCALE[useLang()];
}

/** 사이트 안 경로에 지금 언어 접두어를 붙인다 */
export function useHref(): (href: string) => string {
  const lang = useLang();
  return useMemo(() => (href: string) => withLang(href, lang), [lang]);
}

type LinkProps = ComponentProps<typeof NextLink>;

/** next/link 대신 쓴다: 문자열 href 와 { pathname } 객체에 지금 언어 접두어를 붙인다 */
export function Link({ href, ...rest }: LinkProps) {
  const lang = useLang();
  const localized =
    typeof href === "string"
      ? withLang(href, lang)
      : href.pathname
        ? { ...href, pathname: withLang(href.pathname, lang) }
        : href;
  return <NextLink href={localized} {...rest} />;
}

/** next/navigation 의 useRouter 대신: push·replace·prefetch 에 언어 접두어를 붙인다 */
export function useRouter() {
  const router = useNextRouter();
  const lang = useLang();
  return useMemo(
    () => ({
      ...router,
      push: (href: string, opts?: Parameters<typeof router.push>[1]) => router.push(withLang(href, lang), opts),
      replace: (href: string, opts?: Parameters<typeof router.replace>[1]) => router.replace(withLang(href, lang), opts),
      prefetch: (href: string, opts?: Parameters<typeof router.prefetch>[1]) => router.prefetch(withLang(href, lang), opts),
    }),
    [router, lang],
  );
}

/** 언어 접두어를 뗀 지금 경로 (/en/design → /design) */
export function usePathname(): string {
  return stripLang(useNextPathname() ?? "/");
}
