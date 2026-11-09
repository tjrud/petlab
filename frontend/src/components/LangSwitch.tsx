"use client";

// 언어를 바꾸는 이동이라 언어 접두어를 다시 붙이는 @/i18n/client 의 router 가 아니라 next 의 router 를 쓴다
import { useRouter } from "next/navigation";

import { LANG_COOKIE, type Lang, stripLang, withLang } from "@/i18n/config";
import { useLang, useT } from "@/i18n/client";

/** 헤더의 언어 바꾸기 (한국어 ↔ English). 고른 언어는 쿠키로 기억해 다음에 열 때도 그 언어로 보인다 */
export default function LangSwitch() {
  const lang = useLang();
  const t = useT();
  const router = useRouter();
  const next: Lang = lang === "ko" ? "en" : "ko";

  function change() {
    document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    // 주소는 누를 때 읽는다 (usePathname 은 미리 그리는 화면을 막는다)
    const { pathname, search, hash } = window.location;
    router.push(withLang(stripLang(pathname), next) + search + hash);
  }

  return (
    <button
      type="button"
      onClick={change}
      lang={next}
      title={next === "en" ? "View in English" : "한국어로 보기"}
      aria-label={next === "en" ? t("영어로 보기") : t("한국어로 보기")}
      className="shrink-0 whitespace-nowrap rounded-lg border border-stone-200 px-2 py-1.5 text-xs font-semibold text-stone-600 hover:bg-stone-100"
    >
      {next === "en" ? "EN" : "한국어"}
    </button>
  );
}
