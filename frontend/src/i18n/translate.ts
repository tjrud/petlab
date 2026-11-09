// 번역: 한국어 원문을 열쇠로 영어 사전(en/*.ts)에서 찾는다. 없으면 한국어 그대로.
// 원문에 {name} 자리표시를 두고 vars 로 채운다: t("총 {n}개", { n: 3 }) → "Total 3" / "총 3개".

import type { Lang } from "@/i18n/config";
import { EN } from "@/i18n/en";

export type Vars = Record<string, string | number>;
export type TFunction = (ko: string, vars?: Vars) => string;

function fill(s: string, vars?: Vars): string {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

export function translate(lang: Lang, ko: string, vars?: Vars): string {
  if (lang === "ko") return fill(ko, vars);
  const en = EN[ko];
  if (en === undefined && process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
    // 개발 중에 빠진 번역을 찾기 쉽게 (프로덕션에서는 조용히 한국어를 보인다)
    console.warn(`[i18n] 영어 번역 없음: ${ko}`);
  }
  return fill(en ?? ko, vars);
}

export function makeT(lang: Lang): TFunction {
  return (ko, vars) => translate(lang, ko, vars);
}
