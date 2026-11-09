// 커뮤니티 화면 공통: 입력 한도, 주소, 작성자 표시, 글자 수, 자리 표시.
// 작성자 표시·글자 수는 번역 훅(useT)을 쓰므로 클라이언트 컴포넌트 안에서만 그린다.

import { useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { withNext } from "@/lib/safeNext";
import type { Author } from "@/lib/types";

/** 백엔드(app/schemas.py)와 같은 한도. 최종 판단은 서버가 한다 */
export const LIMITS = { title: 100, body: 5000, comment: 1000 } as const;

export const COMMUNITY_PATH = "/community";
export const NEW_POST_PATH = "/community/new";

export const postHref = (id: string) => `${COMMUNITY_PATH}/${encodeURIComponent(id)}`;
export const loginHref = (next: string) => withNext("/login", next);

/** 사용자에게 보여 줄 오류 문구 (lib/api 로 옮겼다. 이 파일에서 가져다 쓰는 곳을 위해 다시 내보낸다) */
export { errorText } from "@/lib/api";

/** 제목은 한 줄: 붙여 넣은 줄바꿈·탭은 공백으로 바꾼다 */
export const oneLine = (v: string) => v.replace(/[\t\r\n]+/g, " ");

/** 글 제목·내용 확인 (앞뒤 공백은 서버가 지우므로 같은 기준으로 본다) */
export function checkPost(title: string, body: string, t: TFunction): string | null {
  const ti = title.trim();
  const b = body.trim();
  if (!ti) return t("제목을 입력해 주세요.");
  if (ti.length > LIMITS.title) return t("제목은 {n}자까지 쓸 수 있어요.", { n: LIMITS.title });
  if (!b) return t("내용을 입력해 주세요.");
  if (b.length > LIMITS.body) return t("내용은 {n}자까지 쓸 수 있어요.", { n: LIMITS.body });
  return null;
}

/** 작성 후 1분이 넘어서 고친 글이면 "(수정됨)" 을 붙인다 */
export function wasEdited(createdAt: string, updatedAt: string): boolean {
  return new Date(updatedAt).getTime() - new Date(createdAt).getTime() > 60_000;
}

/** 작성자 닉네임 (관리자는 배지). 닉네임은 일반 텍스트로만 보여 준다 */
export function AuthorName({ author, className = "" }: { author: Author; className?: string }) {
  const t = useT();
  return (
    <span className={`inline-flex min-w-0 items-center gap-1 ${className}`}>
      {author.role === "admin" && (
        <span className="shrink-0 rounded bg-stone-800 px-1.5 py-0.5 text-xs font-medium text-white">{t("관리자")}</span>
      )}
      <span className="min-w-0 max-w-[12rem] truncate font-medium text-stone-700">{author.nickname}</span>
    </span>
  );
}

/** 입력 글자 수 (예: 12/1000). 한도에 가까우면 색으로 알린다 */
export function CharCount({ id, length, max }: { id: string; length: number; max: number }) {
  const t = useT();
  const near = length > max * 0.9;
  return (
    <p id={id} className={`text-right text-xs tabular-nums ${near ? "text-amber-700" : "text-stone-500"}`}>
      <span className="sr-only">{t("입력한 글자 수")} </span>
      {length}/{max}
    </p>
  );
}

/** 불러오는 동안의 자리 표시 (화면 낭독기에는 안내 문구만 읽힌다). label 은 부르는 쪽에서 번역해 넘긴다 */
export function Placeholder({ rows = 4, label, rowClassName = "h-20" }: { rows?: number; label: string; rowClassName?: string }) {
  return (
    <div role="status">
      <span className="sr-only">{label}</span>
      <ul aria-hidden className="space-y-3">
        {Array.from({ length: rows }, (_, i) => (
          <li key={i} className={`animate-pulse rounded-2xl bg-stone-100 ${rowClassName}`} />
        ))}
      </ul>
    </div>
  );
}
