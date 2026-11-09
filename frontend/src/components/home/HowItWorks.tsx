import { IconChevronRight, IconCube, IconPencil, IconSparkle } from "@/components/home/icons";
import { getT } from "@/i18n/server";

const STEPS = [
  {
    title: "사육 환경 입력",
    body: "종·크기·마릿수와 케이지 내부 치수(어항은 수조 크기와 물 깊이)를 고르고, 원하는 구조물을 적어요.",
    Icon: IconPencil,
  },
  {
    title: "설계·안전 검증",
    body: "적은 내용대로 구조물 치수를 정하고, 출입구 크기·오르는 높이·벽 두께·물속 공기 빠짐 같은 안전·출력 기준을 확인해요.",
    Icon: IconSparkle,
  },
  {
    title: "3D 확인·프린팅 파일(STL·3MF)",
    body: "3D로 돌려 보며 확인하고, 바꿀 부분은 글로 다시 요청해요. 끝나면 STL·3MF 파일로 내려받아요.",
    Icon: IconCube,
  },
];

export default async function HowItWorks() {
  const t = await getT();
  return (
    <section aria-labelledby="how-title" className="mt-12">
      <h2 id="how-title" className="text-xl font-bold sm:text-2xl">
        {t("이렇게 만들어요")}
      </h2>
      <p className="mt-1 text-sm text-stone-600">{t("세 단계로 진행돼요.")}</p>
      <ol className="mt-5 grid gap-3 md:grid-cols-3 md:gap-8">
        {STEPS.map(({ title, body, Icon }, i) => (
          <li key={title} className="relative rounded-2xl border border-amber-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-amber-700">{t("{n}단계", { n: i + 1 })}</span>
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-50 text-teal-800">
                <Icon className="h-5 w-5" />
              </span>
            </div>
            <h3 className="mt-2 font-semibold sm:text-lg">{t(title)}</h3>
            <p className="mt-1 text-sm leading-relaxed text-stone-600">{t(body)}</p>
            {i < STEPS.length - 1 && (
              <IconChevronRight className="absolute -right-6 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-amber-400 md:block" />
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
