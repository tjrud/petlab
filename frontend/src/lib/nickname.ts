// 닉네임 규칙 (서버 backend/app/names.py 와 같은 기준). 최종 판단은 서버가 한다.
// 안내·오류 문구는 한국어 원문이다. 보여 줄 때 t(문구) 로 번역한다 (사전: i18n/en/auth.ts).

/** 회원가입·닉네임 변경 칸 아래 안내 */
export const NICKNAME_HINT = "커뮤니티에 보이는 이름이에요. 2~20자, 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.";

// 한글 채움 문자(보이지 않는 글자)는 허용 범위(ㄱ-ㆎ) 근처에 있으므로 따로 막는다
const FILLERS = /[ㅤᅟᅠﾠ]/;
const ALLOWED = /^[가-힣ㄱ-ㆎA-Za-z0-9 _.-]+$/;

// 한글 낱자(ㅋㅋ 등)는 NFKC 가 조합용 자모로 바꿔 버리므로 그대로 둔다 (서버 _nfkc_keep_jamo 와 같음)
const COMPAT_JAMO = /([ㄱ-ㆎ]+)/;

/** 서버와 같이 정리한다: 호환 문자 정규화(NFKC, 전각 → 반각 등), 이어진 공백은 하나로, 앞뒤 공백은 지운다 */
export function normalizeNickname(raw: string): string {
  return raw
    .split(COMPAT_JAMO)
    .map((seg) => (/^[ㄱ-ㆎ]+$/.test(seg) ? seg : seg.normalize("NFKC")))
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

/** 닉네임 입력 확인 (문제없으면 undefined). 글자 수는 정리한 뒤 서버(Python)와 같은 기준으로 센다 */
export function nicknameError(raw: string): string | undefined {
  const v = normalizeNickname(raw);
  if (!v) return "닉네임을 입력해 주세요.";
  if (FILLERS.test(v) || !ALLOWED.test(v)) return "닉네임은 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.";
  const n = Array.from(v).length;
  if (n < 2 || n > 20) return "닉네임은 2~20자로 정해 주세요.";
  return undefined;
}
