import Link from "next/link";

import { IconArrowRight, IconCage, IconChat, IconFolder, IconPaw, IconPencil } from "@/components/home/icons";

const AREAS = [
  {
    href: "/design",
    title: "설계하기",
    body: "케이지 치수와 원하는 구조물을 적으면 치수에 맞춘 설계와 3D 프린팅 파일이 나와요.",
    Icon: IconPencil,
    tone: "bg-amber-100 text-amber-800",
  },
  {
    href: "/cage",
    title: "가상 케이지 시뮬레이션",
    body: "케이지 치수를 등록하고 은신처·쳇바퀴·모래목욕통을 놓아 보며 겹침과 끼임 틈을 미리 확인해요.",
    Icon: IconCage,
    tone: "bg-sky-50 text-sky-800",
  },
  {
    href: "/market",
    title: "둥지마당",
    body: "보호자들이 만든 SKP·3MF·STL 파일과 NestForge 설계를 내려받고, 내가 만든 구조물을 올릴 수 있어요.",
    Icon: IconFolder,
    tone: "bg-lime-50 text-lime-800",
  },
  {
    href: "/designs",
    title: "내 설계 내역",
    body: "지금까지 만든 설계와 버전을 한곳에서 보고, 이어서 고치거나 다시 내려받을 수 있어요.",
    Icon: IconFolder,
    tone: "bg-teal-50 text-teal-800",
  },
  {
    href: "/community",
    title: "커뮤니티",
    body: "다른 보호자의 설계와 사육 이야기를 보고, 내 설계를 공유할 수 있어요.",
    Icon: IconChat,
    tone: "bg-orange-100 text-orange-800",
  },
  {
    href: "/me",
    title: "내 정보·반려동물",
    body: "반려동물과 케이지 정보를 등록해 두면 다음 설계 때 바로 불러올 수 있어요.",
    Icon: IconPaw,
    tone: "bg-rose-50 text-rose-700",
  },
] as const;

export default function SectionCards() {
  return (
    <section aria-labelledby="areas-title" className="mt-12">
      <h2 id="areas-title" className="text-xl font-bold sm:text-2xl">
        주요 기능
      </h2>
      <ul className="mt-5 grid gap-4 sm:grid-cols-2">
        {AREAS.map(({ href, title, body, Icon, tone }) => (
          <li key={href}>
            <Link
              href={href}
              className="group flex h-full gap-4 rounded-2xl border border-amber-200 bg-white p-5 shadow-sm transition hover:border-amber-400 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 sm:p-6"
            >
              <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${tone}`}>
                <Icon className="h-6 w-6" />
              </span>
              <div className="min-w-0">
                <h3 className="text-lg font-semibold">{title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-stone-600">{body}</p>
                <span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-amber-700">
                  바로 가기
                  <IconArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
