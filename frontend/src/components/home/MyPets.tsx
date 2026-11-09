"use client";

import { Link, useT } from "@/i18n/client";
import { useId } from "react";

import { IconPaw } from "@/components/home/icons";
import { LoadError, Skeleton, useLoad } from "@/components/home/Loadable";
import { api } from "@/lib/api";
import { enclosureSummary, kindOf } from "@/lib/habitatKind";
import type { Pet } from "@/lib/types";
import { ui } from "@/lib/ui";

const loadPets = () => api.pets();
const SHOW = 4; // 메인 화면에는 몇 마리만 보여 주고 나머지는 내 정보에서

function PetRow({ pet }: { pet: Pet }) {
  const t = useT();
  const nameId = useId();
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl border border-stone-200 p-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-amber-100 text-amber-700">
        <IconPaw className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1 basis-32">
        <p id={nameId} className="truncate font-medium">
          {pet.name}
        </p>
        <p className="truncate text-sm text-stone-600">
          {t(pet.species_name_ko)} · {t(pet.size_name_ko)}
          {pet.cage && (
            <>
              {" "}
              ·{" "}
              {enclosureSummary(kindOf(pet), pet.cage, t)}
            </>
          )}
        </p>
      </div>
      {/* 링크 이름은 "이 아이로 설계하기" 로 두고, 어느 아이인지는 설명(이름)으로 함께 읽힌다 */}
      <Link
        href={`/design?pet=${encodeURIComponent(pet.id)}`}
        aria-describedby={nameId}
        className="shrink-0 rounded-lg bg-amber-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600"
      >
        {t("이 아이로 설계하기")}
      </Link>
    </li>
  );
}

/** 메인 화면: 내 반려동물 (등록한 아이로 바로 설계 시작) */
export default function MyPets() {
  const t = useT();
  const { state, retry } = useLoad(loadPets, t("반려동물 정보를 불러오지 못했어요."));

  return (
    <section aria-labelledby="my-pets-title" className={`${ui.card} flex flex-col`}>
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 id="my-pets-title" className={ui.h2}>
          {t("내 반려동물")}
        </h3>
        <Link href="/me#pets" className={`${ui.link} shrink-0 text-sm font-medium`}>
          {t("관리하기")}
        </Link>
      </div>

      {state.kind === "loading" && <Skeleton rows={2} label={t("반려동물 정보를 불러오는 중이에요")} />}
      {state.kind === "error" && <LoadError message={state.message} needsLogin={state.needsLogin} onRetry={retry} />}
      {state.kind === "ok" &&
        (state.data.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center rounded-xl bg-amber-50/70 p-6 text-center">
            <p className="font-medium">{t("등록된 반려동물이 없어요.")}</p>
            <p className="mt-1 text-sm text-stone-600">
              {t("아이와 케이지 정보를 등록해 두면 다음 설계 때 바로 불러올 수 있어요.")}
            </p>
            <Link href="/me#pets" className={`${ui.btnPrimary} mt-4`}>
              {t("반려동물 등록하기")}
            </Link>
          </div>
        ) : (
          <>
            <ul className="space-y-2">
              {state.data.slice(0, SHOW).map((p) => (
                <PetRow key={p.id} pet={p} />
              ))}
            </ul>
            {state.data.length > SHOW && (
              <p className="mt-3 text-sm text-stone-600">
                {t("그 밖에 {n}마리가 더 있어요.", { n: state.data.length - SHOW })}{" "}
                <Link href="/me#pets" className={`${ui.link} font-medium`}>
                  {t("모두 보기")}
                </Link>
              </p>
            )}
          </>
        ))}
    </section>
  );
}
