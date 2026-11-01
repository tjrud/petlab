// 화면 공통 스타일 (Tailwind 클래스). 새 화면은 이 값을 써서 모양을 맞춘다.

export const ui = {
  card: "rounded-2xl border border-amber-200 bg-white p-5 shadow-sm sm:p-6",
  cardPlain: "rounded-2xl border border-stone-200 bg-white p-4",
  h1: "text-2xl font-bold sm:text-3xl",
  h2: "text-lg font-semibold",
  muted: "text-sm text-stone-500",
  label: "mb-1 block text-sm font-medium",
  input:
    "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200",
  btnPrimary:
    "inline-flex items-center justify-center rounded-xl bg-amber-500 px-5 py-2.5 font-semibold text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300",
  btnSecondary:
    "inline-flex items-center justify-center rounded-xl border border-stone-300 bg-white px-4 py-2 text-sm font-medium hover:bg-stone-50 disabled:opacity-50",
  btnDanger:
    "inline-flex items-center justify-center rounded-xl border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50",
  error: "rounded-lg bg-red-50 p-3 text-sm text-red-700",
  success: "rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800",
  badge: "rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900",
  link: "text-amber-700 underline-offset-2 hover:underline",
} as const;

/** "2026-11-01T12:00:00Z" → "2026. 11. 1." (한국어 날짜) */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ko-KR", { year: "numeric", month: "numeric", day: "numeric" });
}

/** 날짜와 시각 ("2026. 11. 1. 오후 9:30") */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
