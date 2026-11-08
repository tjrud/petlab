// 영어 사전. 화면 묶음마다 파일을 나눠 두고 여기서 합친다 (열쇠 = 한국어 원문, 값 = 영어).
// 같은 원문이 여러 파일에 있으면 뒤의 것이 이긴다 (같은 번역이어야 한다).

import common from "@/i18n/en/common";

export const EN: Record<string, string> = {
  ...common,
};
