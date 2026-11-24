// 라이브러리 부품(family@vN)의 표시 정보: 이름·색·파라미터 이름·선택지 이름 (GET /library/display).
// 코드 부품은 lib/templates.ts 의 정적 표를 쓰고, 라이브러리 부품만 여기서 채운다.
// 언어마다 한 번만 받는다 (모듈 전역 약속 캐시). 서버가 이름을 요청 언어로 바꿔 주므로 t() 를 거치지 않는다.
// lib/templates.ts 가 서버 컴포넌트에서도 쓰이므로 이 모듈은 React 훅을 쓰지 않는다 (훅은 lib/useLibraryDisplay.ts).

import type { Lang } from "@/i18n/config";
import { api, currentLang } from "@/lib/api";
import type { LibraryDisplay, LibraryPartDisplay } from "@/lib/types";

/** 라이브러리 부품 키인지 ("tunnel_junction@v1"). 코드 부품 키에는 "@" 가 없다 */
export function isLibraryKey(template: string): boolean {
  return template.includes("@");
}

const loaded = new Map<Lang, LibraryDisplay>();
const pending = new Map<Lang, Promise<LibraryDisplay>>();
const listeners = new Set<() => void>();
let version = 0;

function notify() {
  version += 1;
  for (const l of listeners) l();
}

/** 표시 정보를 받는다 (언어별로 한 번). 실패하면 다음에 부를 때 다시 받는다 */
export function loadLibraryDisplay(lang: Lang = currentLang()): Promise<LibraryDisplay> {
  const done = loaded.get(lang);
  if (done) return Promise.resolve(done);
  let p = pending.get(lang);
  if (!p) {
    p = api.libraryDisplay(lang).then(
      (r) => {
        loaded.set(lang, r.parts);
        pending.delete(lang);
        notify();
        return r.parts;
      },
      (e: unknown) => {
        pending.delete(lang);
        throw e;
      },
    );
    pending.set(lang, p);
  }
  return p;
}

/** 지금 화면 언어로 받아 둔 부품 표시 정보 (아직 없으면 undefined: 부르는 쪽이 키 그대로 보인다) */
export function libraryPart(template: string): LibraryPartDisplay | undefined {
  return loaded.get(currentLang())?.[template];
}

/** 받아 둔 부품 중 이 파라미터 이름을 가진 첫 부품 (어느 부품의 값인지 모를 때) */
export function libraryPartWithParam(field: string): LibraryPartDisplay | undefined {
  const parts = loaded.get(currentLang());
  if (!parts) return undefined;
  return Object.values(parts).find((p) => field in p.params);
}

/** 표시 정보를 새로 받으면 부른다 (useSyncExternalStore 용). 해지 함수를 돌려준다 */
export function subscribeLibraryDisplay(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

/** 받은 표시 정보가 바뀔 때마다 커지는 수 */
export function libraryDisplayVersion(): number {
  return version;
}
