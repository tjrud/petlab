// 내 정보 화면에서 함께 쓰는 작은 도우미 (글자 수·날짜·성별 표시·입력 칸 오류 표시)

import type { Cage, PetSex } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 서버(Python)와 같은 기준으로 글자 수를 센다 (이모지 같은 문자도 한 글자) */
export const charCount = (s: string) => Array.from(s).length;

/** 서버가 거부하는 제어 문자 (줄바꿈·탭은 여러 줄 입력에서만 허용) */
export function hasControlChars(s: string, multiline = false): boolean {
  return multiline ? /[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/.test(s) : /[\u0000-\u001f\u007f-\u009f]/.test(s);
}

/** 받침에 맞춰 목적격 조사를 붙인다 ("콩이" → "콩이를", "보리밥" → "보리밥을"). 한글로 끝나지 않으면 "을(를)" */
export function withObjectParticle(word: string): string {
  const last = word.charCodeAt(word.length - 1);
  if (last >= 0xac00 && last <= 0xd7a3) return word + ((last - 0xac00) % 28 ? "을" : "를");
  return `${word}을(를)`;
}

export const SEX_LABEL: Record<PetSex, string> = { male: "수컷", female: "암컷", unknown: "모름" };

/** 케이지 치수 프리셋 (설계하기 화면과 반려동물 등록이 함께 쓴다) */
export const CAGE_PRESETS = [
  { label: "소형 45×30×30cm", w: 450, d: 300, h: 300 },
  { label: "중형 60×40×30cm", w: 600, d: 400, h: 300 },
  { label: "대형 80×50×40cm", w: 800, d: 500, h: 400 },
  { label: "초대형 100×50×50cm", w: 1000, d: 500, h: 500 },
] as const;

/** 케이지 내부 치수 허용 범위 mm (서버 CageIn 과 같다) */
export const CAGE_LIMITS = { w: [200, 2000], d: [200, 2000], h: [100, 1000] } as const;

export const CAGE_DIMS = [
  ["w", "가로"],
  ["d", "세로"],
  ["h", "높이"],
] as const;

export const BIRTH_MIN = "1990-01-01";

/** 사용자 기기 기준 오늘 날짜 "YYYY-MM-DD" (브라우저에서 화면을 그릴 때·이벤트 처리 중에만 부른다) */
export function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "2025-03-01" → "2025. 3. 1." (시간대에 따라 하루가 밀리지 않게 직접 나눈다) */
export function formatYmd(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return `${y}. ${m}. ${d}.`;
}

/** 생일로 나이를 센다: "1개월 미만", "5개월", "1살 2개월" */
export function petAge(ymd: string, today = todayLocal()): string | null {
  const [by, bm, bd] = ymd.split("-").map(Number);
  const [ty, tm, td] = today.split("-").map(Number);
  if (![by, bm, bd, ty, tm, td].every(Number.isFinite)) return null;
  const months = (ty - by) * 12 + (tm - bm) - (td < bd ? 1 : 0);
  if (months < 0) return null;
  if (months < 1) return "1개월 미만";
  if (months < 12) return `${months}개월`;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return rest ? `${years}살 ${rest}개월` : `${years}살`;
}

const mm = (v: number) => String(Math.round(v * 10) / 10);

/** 600×400×300mm */
export const formatCage = (c: Cage) => `${mm(c.width_mm)}×${mm(c.depth_mm)}×${mm(c.height_mm)}mm`;

/** 카드 안에 들어가는 작은 기본 버튼 */
export const btnPrimarySm = ui.btnPrimary.replace("px-5 py-2.5", "px-4 py-2 text-sm");

/** 오류가 있으면 빨간 테두리 */
export const inputClass = (invalid: boolean) => (invalid ? ui.input.replace("border-stone-300", "border-red-400") : ui.input);

/** 입력 칸 아래 오류 문구 (aria-describedby 로 연결한다) */
export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1 text-sm text-red-700">
      {message}
    </p>
  );
}

/** aria-describedby 값 (있는 것만 이어 붙인다) */
export const describedBy = (...ids: (string | false | null | undefined)[]) => ids.filter(Boolean).join(" ") || undefined;
