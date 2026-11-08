// 지원 언어와 주소 규칙. 한국어는 지금 주소 그대로(/design), 영어는 /en 을 붙인다(/en/design).
// 서버·클라이언트·proxy 가 함께 쓴다 (React 를 불러오지 않는다).

export const LANGS = ["ko", "en"] as const;
export type Lang = (typeof LANGS)[number];
export const DEFAULT_LANG: Lang = "ko";
/** 고른 언어를 기억하는 쿠키 (proxy 가 읽어 /en 으로 보낸다) */
export const LANG_COOKIE = "lang";

export function isLang(v: unknown): v is Lang {
  return typeof v === "string" && (LANGS as readonly string[]).includes(v);
}

/** 주소 앞의 /en 을 뗀 경로와 언어 ("/en/design?x=1" → ["en", "/design?x=1"]) */
export function splitLang(path: string): [Lang, string] {
  if (path === "/en" || path.startsWith("/en/") || path.startsWith("/en?") || path.startsWith("/en#")) {
    const rest = path.slice(3);
    return ["en", rest === "" || rest[0] !== "/" ? `/${rest}` : rest];
  }
  return ["ko", path];
}

/** 경로에서 언어 접두어를 뗀다 (활성 메뉴 비교 등) */
export function stripLang(path: string): string {
  return splitLang(path)[1];
}

/**
 * 사이트 안 경로에 언어 접두어를 붙인다. 바깥 주소·API·파일·#·? 로 시작하는 주소는 그대로 둔다.
 * 이미 /en 이 붙은 경로는 언어에 맞게 바꾼다.
 */
export function withLang(href: string, lang: Lang): string {
  if (!href.startsWith("/") || href.startsWith("//") || href.startsWith("/api/") || href === "/api") return href;
  const bare = stripLang(href);
  if (lang === DEFAULT_LANG) return bare;
  return bare === "/" ? "/en" : bare.startsWith("/?") || bare.startsWith("/#") ? `/en${bare.slice(1)}` : `/en${bare}`;
}

/** 날짜·숫자 형식에 쓰는 로캘 */
export const INTL_LOCALE: Record<Lang, string> = { ko: "ko-KR", en: "en-US" };
