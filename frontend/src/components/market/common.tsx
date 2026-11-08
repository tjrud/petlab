// 탐색 공통: 주소, 형식 이름, 크기 표시, 미리보기 자리

import { useT } from "@/i18n/client";
import type { Lang } from "@/i18n/config";
import type { TFunction } from "@/i18n/translate";
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

/** 형식 이름 (번역해서) */
export const formatLabel = (f: string, t: TFunction) => (FORMAT_LABEL[f] ? t(FORMAT_LABEL[f]) : f.toUpperCase());

/** 추천한 까닭 (서버가 한국어로 보낸다): 영어 화면에서는 알려진 문구를 번역한다 */
export function reasonText(reason: string, lang: Lang, t: TFunction): string {
  if (lang === "ko") return reason;
  const cat = (name: string) => t(name);
  let m = /^내 설계에 (.+) 구조물이 있어요$/.exec(reason);
  if (m) return t("내 설계에 {name} 구조물이 있어요", { name: cat(m[1]) });
  m = /^내 배치안에 (.+)[이가] 있어요$/.exec(reason);
  if (m) return t("내 배치안에 {name} 있어요", { name: cat(m[1]) });
  m = /^자주 본 (.+) 분류예요$/.exec(reason);
  if (m) return t("자주 본 {name} 분류예요", { name: cat(m[1]) });
  return t(reason);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`;
  return `${(n / (1024 * 1024)).toFixed(1)}MB`;
}

export const imageSrc = (img: MarketFile) => api.marketUrl(img.view_url ?? img.download_url);

export function FormatChips({ formats, className = "" }: { formats: string[]; className?: string }) {
  const t = useT();
  return (
    <ul aria-label={t("파일 형식")} className={`flex flex-wrap gap-1 ${className}`}>
      {formats.map((f) => (
        <li
          key={f}
          className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
            f === "nestforge" ? "bg-teal-50 text-teal-800 ring-1 ring-teal-200" : "bg-stone-100 text-stone-700"
          }`}
        >
          {formatLabel(f, t)}
        </li>
      ))}
    </ul>
  );
}

/** 미리보기 이미지가 없을 때: 형식 글자를 크게 */
export function NoPreview({ formats }: { formats: string[] }) {
  const t = useT();
  const main = formats.find((f) => f !== "nestforge") ?? formats[0] ?? "";
  return (
    <div aria-hidden className="grid h-full w-full place-items-center bg-linear-to-br from-amber-50 to-stone-100">
      <span className="text-2xl font-bold tracking-wide text-stone-400">{formatLabel(main, t)}</span>
    </div>
  );
}
