// 영어 사전. 화면 묶음마다 파일을 나눠 두고 여기서 합친다 (열쇠 = 한국어 원문, 값 = 영어).
// 같은 원문이 여러 파일에 있으면 뒤의 것이 이긴다. 번역이 갈린 원문은 overrides.ts 에서 정한다.

import auth from "@/i18n/en/auth";
import cage_a from "@/i18n/en/cage_a";
import cage_b from "@/i18n/en/cage_b";
import catalog from "@/i18n/en/catalog";
import common from "@/i18n/en/common";
import design from "@/i18n/en/design";
import designs_community from "@/i18n/en/designs_community";
import market from "@/i18n/en/market";
import me from "@/i18n/en/me";
import overrides from "@/i18n/en/overrides";
import pages from "@/i18n/en/pages";

export const EN: Record<string, string> = {
  ...common,
  ...pages,
  ...auth,
  ...design,
  ...designs_community,
  ...cage_a,
  ...cage_b,
  ...catalog,
  ...market,
  ...me,
  ...overrides,
};
