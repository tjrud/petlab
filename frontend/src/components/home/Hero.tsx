import Image from "next/image";
import Link from "next/link";

import { IconCheck } from "@/components/home/icons";
import { TEMPLATE_COLORS } from "@/lib/templates";

const HIGHLIGHTS = ["안전 기준 자동 검증", "3D로 미리 보기", "STL·3MF 파일 내려받기"];

// 오른쪽 그림에 띄우는 구조물 이름표 (위치는 그림 상자 안쪽 비율)
const PARTS = [
  { label: "은신처", color: TEMPLATE_COLORS.hideout, pos: "left-[6%] top-[12%] -rotate-3" },
  { label: "터널", color: TEMPLATE_COLORS.tunnel, pos: "right-[6%] top-[22%] rotate-2" },
  { label: "램프·계단", color: TEMPLATE_COLORS.ramp, pos: "left-[8%] bottom-[18%] rotate-2" },
  { label: "모래목욕통", color: TEMPLATE_COLORS.sand_bath, pos: "right-[5%] bottom-[10%] -rotate-2" },
];

const cta = "inline-flex w-full items-center justify-center rounded-xl px-6 py-3 font-semibold sm:w-auto";

export default function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="overflow-hidden rounded-3xl border border-amber-200 bg-linear-to-br from-amber-50 via-white to-teal-50 px-5 py-8 sm:px-10 sm:py-12"
    >
      <div className="grid items-center gap-8 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div>
          <p className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900 sm:text-sm">
            햄스터 케이지 맞춤 구조물 · AI 설계
          </p>
          <h1 id="hero-title" className="mt-4 text-balance text-3xl font-bold leading-tight sm:text-4xl lg:text-5xl">
            우리 아이 케이지에 꼭 맞는 구조물을 설계해 드려요
          </h1>
          <p className="mt-4 max-w-xl text-pretty text-stone-600 sm:text-lg">
            케이지 크기와 원하는 구성을 알려 주시면 AI가 은신처·터널 같은 구조물을 맞춤 설계하고, 3D 프린팅
            파일(STL·3MF)까지 만들어 드려요.
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <Link href="/design" className={`${cta} bg-amber-500 text-white shadow-sm hover:bg-amber-600`}>
              맞춤 설계 시작하기
            </Link>
            <Link href="/community" className={`${cta} border border-stone-300 bg-white hover:bg-stone-50`}>
              커뮤니티 둘러보기
            </Link>
          </div>
          <ul className="mt-6 flex flex-wrap gap-x-4 gap-y-2 text-sm text-stone-600">
            {HIGHLIGHTS.map((h) => (
              <li key={h} className="flex items-center gap-1.5">
                <IconCheck className="h-4 w-4 shrink-0 text-teal-700" />
                {h}
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
              {p.label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
