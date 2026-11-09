// 서버 컴포넌트·generateMetadata 용: 지금 주소의 언어(app/[lang])와 번역 함수.

import { lang as rootLang } from "next/root-params";

import { DEFAULT_LANG, isLang, type Lang } from "@/i18n/config";
import { makeT, type TFunction } from "@/i18n/translate";

export async function getLang(): Promise<Lang> {
  const l = await rootLang();
  return isLang(l) ? l : DEFAULT_LANG;
}

export async function getT(): Promise<TFunction> {
  return makeT(await getLang());
}
