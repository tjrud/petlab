// 라이브러리 부품을 그리는 클라이언트 컴포넌트의 훅 (lib/libraryDisplay.ts 는 서버 컴포넌트에서도 쓰여 훅을 두지 않는다)

import { useEffect, useSyncExternalStore } from "react";

import type { Lang } from "@/i18n/config";
import { libraryDisplayVersion, loadLibraryDisplay, subscribeLibraryDisplay } from "@/lib/libraryDisplay";

/**
 * enabled 이면 표시 정보(이름·색)를 받고, 받으면 다시 그린다. 이 컴포넌트는 lib/templates.ts 의
 * templateColor·paramLabel·formatParam 으로 라이브러리 부품을 그린다.
 * 돌려주는 값은 바뀔 때마다 커지는 수 (메모의 의존성으로 쓸 수 있다).
 */
export function useLibraryDisplay(enabled: boolean, lang: Lang): number {
  const v = useSyncExternalStore(subscribeLibraryDisplay, libraryDisplayVersion, () => 0);
  useEffect(() => {
    if (!enabled) return;
    loadLibraryDisplay(lang).catch(() => {
      /* 표시 정보 없이 키 그대로 보인다 */
    });
  }, [enabled, lang]);
  return v;
}
