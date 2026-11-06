// 탐색 공통: 주소, 형식 이름, 크기 표시, 미리보기 자리

import { api } from "@/lib/api";
import type { MarketCategory, MarketFile } from "@/lib/types";

export const MARKET_PATH = "/explore";
export const NEW_MARKET_PATH = "/explore/new";
export const marketHref = (id: string) => `${MARKET_PATH}/${encodeURIComponent(id)}`;

export const MARKET_CATEGORIES: { key: MarketCategory; label: string }[] = [
  { key: "hideout", label: "은신처" },
  { key: "tunnel", label: "터널" },
  { key: "ramp", label: "경사로·계단" },
  { key: "sand_bath", label: "모래목욕통" },
  { key: "cage", label: "케이지 전체" },
  { key: "layout", label: "가상 케이지 배치" },
  { key: "etc", label: "기타" },
];

export const FORMAT_LABEL: Record<string, string> = {
  skp: "SKP",
  "3mf": "3MF",
  stl: "STL",
  nestforge: "NestForge 설계",
  layout: "가상 케이지 배치",
};

export const FORMAT_HINT: Record<string, string> = {
  skp: "SketchUp 모델",
  "3mf": "3D 프린팅용 (슬라이서에서 열기)",
  stl: "3D 프린팅용 메시",
};

export function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`;
  return `${(n / (1024 * 1024)).toFixed(1)}MB`;
}

export const imageSrc = (img: MarketFile) => api.marketUrl(img.view_url ?? img.download_url);

export function FormatChips({ formats, className = "" }: { formats: string[]; className?: string }) {
  return (
    <ul aria-label="파일 형식" className={`flex flex-wrap gap-1 ${className}`}>
      {formats.map((f) => (
        <li
          key={f}
          className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
            f === "nestforge" ? "bg-teal-50 text-teal-800 ring-1 ring-teal-200" : "bg-stone-100 text-stone-700"
          }`}
        >
          {FORMAT_LABEL[f] ?? f.toUpperCase()}
        </li>
      ))}
    </ul>
  );
}

/** 미리보기 이미지가 없을 때: 형식 글자를 크게 */
export function NoPreview({ formats }: { formats: string[] }) {
  const main = formats.find((f) => f !== "nestforge") ?? formats[0] ?? "";
  return (
    <div aria-hidden className="grid h-full w-full place-items-center bg-linear-to-br from-amber-50 to-stone-100">
      <span className="text-2xl font-bold tracking-wide text-stone-400">{FORMAT_LABEL[main] ?? main.toUpperCase()}</span>
    </div>
  );
}
