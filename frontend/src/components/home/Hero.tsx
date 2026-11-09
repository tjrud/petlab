import Image from "next/image";
import { Link } from "@/i18n/client";

import { IconArrowRight, IconCheck, IconSearch } from "@/components/home/icons";
import { withLang } from "@/i18n/config";
import { getLang, getT } from "@/i18n/server";
import { TEMPLATE_COLORS } from "@/lib/templates";

const HIGHLIGHTS = ["안전 기준 자동 검증", "3D로 미리 보기", "STL·3MF 파일 내려받기"];

// 오른쪽 그림에 띄우는 구조물 이름표 (위치는 그림 상자 안쪽 비율)
const PARTS = [
  { label: "은신처", color: TEMPLATE_COLORS.hideout, pos: "left-[6%] top-[12%] -rotate-3" },
  { label: "터널", color: TEMPLATE_COLORS.tunnel, pos: "right-[6%] top-[22%] rotate-2" },
  { label: "램프·계단", color: TEMPLATE_COLORS.ramp, pos: "left-[8%] bottom-[18%] rotate-2" },
  { label: "모래목욕통", color: TEMPLATE_COLORS.sand_bath, pos: "right-[5%] bottom-[10%] -rotate-2" },
  { label: "물속 동굴", color: TEMPLATE_COLORS.cave, pos: "left-1/2 top-[1%] -translate-x-1/2 rotate-1" },
];

// 입력창 아래 예시. 누르면 그 문장으로 설계하기 화면이 열린다 (species 가 있으면 그 종을 골라 둔다)
const EXAMPLES: readonly { ko: string; species?: string }[] = [
  { ko: "출입구가 두 개 있는 은신처를 만들어 주세요" },
  { ko: "케이지 한쪽에 놓을 긴 터널이 필요해요" },
  { ko: "완만한 경사로를 하나 만들어 주세요" },
  { ko: "새우가 숨을 수 있는 작은 동굴을 만들어 주세요", species: "aquarium" },
];

const designHref = (prompt: string, species?: string) =>
  `/design?prompt=${encodeURIComponent(prompt)}${species ? `&species=${encodeURIComponent(species)}` : ""}`;

export default async function Hero() {
  const lang = await getLang();
  const t = await getT();
  return (
    <section
      aria-labelledby="hero-title"
      className="overflow-hidden rounded-3xl border border-amber-200 bg-linear-to-br from-amber-50 via-white to-teal-50 px-5 py-8 sm:px-10 sm:py-12"
    >
      <div className="grid grid-cols-1 items-center gap-8 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div>
          <p className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900 sm:text-sm">
            {t("햄스터 케이지·어항 맞춤 구조물")}
          </p>
          <h1 id="hero-title" className="mt-4 text-balance text-[1.75rem] font-bold leading-tight sm:text-4xl lg:text-5xl">
            {t("필요한 구조물을 적어 보세요")}
          </h1>
          <p className="mt-4 max-w-xl text-pretty text-stone-600 sm:text-lg">
            {t(
              "은신처, 터널, 계단, 모래목욕통, 어항에 넣을 물속 동굴. 원하는 구성과 위치를 적으면 케이지나 수조 치수에 맞게 설계하고, 3D 프린팅 파일(STL·3MF)로 받을 수 있어요.",
            )}
          </p>

          {/* 검색창처럼 한 줄로 적고 바로 설계하기로 넘어간다 (자바스크립트 없이도 동작하는 GET 폼).
              좁은 화면에서는 입력칸 아래에 버튼을 꽉 차게 두어 예시 문장이 잘리지 않게 한다 */}
          <form action={withLang("/design", lang)} method="get" role="search" aria-label={t("맞춤 설계 요청")} className="mt-7 max-w-xl">
            <div className="flex flex-col gap-1.5 rounded-2xl border border-stone-300 bg-white p-1.5 shadow-sm transition focus-within:border-amber-400 focus-within:shadow-md focus-within:ring-2 focus-within:ring-amber-200 sm:flex-row sm:items-center sm:gap-2 sm:rounded-full sm:py-1.5 sm:pl-4">
              <div className="flex min-w-0 flex-1 items-center gap-2 px-2.5 sm:px-0">
                <IconSearch className="h-5 w-5 shrink-0 text-stone-400" />
                <input
                  type="search"
                  name="prompt"
                  aria-label={t("원하는 구조물")}
                  placeholder={t("예: 환기구가 있는 은신처")}
                  maxLength={2000}
                  autoComplete="off"
                  enterKeyHint="go"
                  className="w-0 min-w-0 flex-1 bg-transparent py-2 text-base outline-none placeholder:text-stone-400"
                />
              </div>
              <button
                type="submit"
                className="inline-flex shrink-0 items-center justify-center gap-1 rounded-xl bg-amber-500 px-4 py-2.5 font-semibold text-white hover:bg-amber-600 sm:rounded-full sm:px-5"
              >
                {t("설계하기")}
                <IconArrowRight className="h-4 w-4" />
              </button>
            </div>
          </form>
          <div className="mt-3 flex max-w-xl flex-wrap items-center gap-2 text-sm">
            <span className="text-stone-500">{t("예시")}</span>
            {EXAMPLES.map(({ ko, species }) => ({ e: t(ko), species })).map(({ e, species }) => (
              <Link
                key={e}
                href={designHref(e, species)}
                className="rounded-full border border-stone-200 bg-white/80 px-3 py-1 text-stone-700 hover:border-amber-300 hover:bg-amber-50"
              >
                {e}
              </Link>
            ))}
          </div>
          <ul className="mt-6 flex flex-wrap gap-x-4 gap-y-2 text-sm text-stone-600">
            {HIGHLIGHTS.map((h) => (
              <li key={h} className="flex items-center gap-1.5">
                <IconCheck className="h-4 w-4 shrink-0 text-teal-700" />
                {t(h)}
              </li>
            ))}
          </ul>
        </div>

        <div aria-hidden className="relative mx-auto hidden aspect-square w-full max-w-sm md:block">
          <div className="absolute inset-[6%] rotate-6 rounded-[2.5rem] bg-amber-100/80" />
          <div className="absolute inset-[6%] rounded-[2.5rem] border border-amber-200 bg-white/90 shadow-sm" />
          <Image
            src="/logo/logo-symbol.svg"
            alt=""
            width={120}
            height={120}
            unoptimized
            className="absolute left-1/2 top-1/2 h-auto w-[46%] -translate-x-1/2 -translate-y-1/2 drop-shadow-sm"
          />
          {PARTS.map((p) => (
            <span
              key={p.label}
              className={`absolute ${p.pos} flex items-center gap-1.5 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-sm font-medium text-stone-700 shadow-sm`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: p.color }} />
              {t(p.label)}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
