"use client";

import { Link, useT } from "@/i18n/client";

import { IconPaw } from "@/components/home/icons";
import type { Me, User } from "@/lib/types";
import { formatDate, ui } from "@/lib/ui";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <>
      <span className="block text-xs text-stone-500">{label}</span>
      <span className="mt-0.5 block text-lg font-bold text-stone-900">{value}</span>
    </>
  );
}

const tile = "block rounded-xl bg-amber-50/70 px-2 py-3 text-center";

/** 프로필 요약: 닉네임·아이디·가입일, 반려동물·설계·글 수, 최근 24시간 설계 사용량 */
export default function ProfileCard({
  user,
  me,
  meError,
  petCount,
}: {
  user: User;
  me: Me | null;
  meError: string | null;
  petCount: number | null;
}) {
  const t = useT();
  const isAdmin = user.role === "admin";
  const quota = me?.design_quota;
  const pets = petCount ?? me?.stats.pets;
  const percent = quota && quota.limit ? Math.min(100, Math.round((quota.used / quota.limit) * 100)) : 0;

  return (
    <section aria-labelledby="profile-title" className={ui.card}>
      <div className="flex items-start gap-3">
        <span aria-hidden className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-amber-100">
          <IconPaw className="h-6 w-6 text-amber-800" />
        </span>
        <div className="min-w-0">
          <h2 id="profile-title" className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            <span className="break-all">{user.nickname}</span>
            {isAdmin && <span className="rounded bg-stone-800 px-1.5 py-0.5 text-xs font-medium text-white">{t("관리자")}</span>}
          </h2>
          <dl className="mt-1 space-y-0.5 text-sm text-stone-600">
            <div className="flex gap-2">
              <dt className="shrink-0 text-stone-500">{t("아이디")}</dt>
              <dd className="min-w-0 break-all">{user.username}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="shrink-0 text-stone-500">{t("가입일")}</dt>
              <dd>{formatDate(user.created_at)}</dd>
            </div>
          </dl>
        </div>
      </div>

      <ul className="mt-5 grid grid-cols-3 gap-2" aria-label={t("활동 요약")}>
        <li>
          <a href="#pets" className={`${tile} hover:bg-amber-100`}>
            <Stat label={t("반려동물")} value={pets === undefined ? "–" : t("{n}마리", { n: pets })} />
          </a>
        </li>
        <li>
          <Link href="/designs" className={`${tile} hover:bg-amber-100`}>
            <Stat label={t("내 설계")} value={me ? t("{n}개", { n: me.stats.designs }) : "–"} />
          </Link>
        </li>
        <li className={tile}>
          <Stat label={t("커뮤니티 글")} value={me ? t("{n}개", { n: me.stats.posts }) : "–"} />
        </li>
      </ul>

      <div className="mt-5 rounded-xl border border-stone-200 p-3">
        {quota ? (
          isAdmin || quota.limit === null ? (
            <p className="text-sm">
              <span className="font-medium">{t("최근 24시간 설계")}</span>{" "}
              <span className="text-stone-600">{t("관리자는 제한 없음")}</span>
            </p>
          ) : (
            <>
              <p className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">{t("최근 24시간 설계")}</span>{" "}
                <span className={quota.remaining === 0 ? "font-semibold text-red-700" : "text-stone-700"}>
                  {t("{used}/{limit}회", { used: quota.used, limit: quota.limit ?? "" })}
                </span>
              </p>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100" aria-hidden>
                <div
                  className={`h-full rounded-full ${quota.remaining === 0 ? "bg-red-400" : "bg-amber-400"}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-stone-500">
                {quota.remaining === 0
                  ? t("최근 24시간 동안 쓸 수 있는 설계 횟수를 모두 썼어요. 시간이 지나면 다시 설계할 수 있어요.")
                  : t("설계 만들기와 수정 요청을 합쳐 {n}회 더 할 수 있어요. 실패한 요청도 횟수에 포함돼요.", {
                      n: quota.remaining ?? "",
                    })}
              </p>
            </>
          )
        ) : (
          <p className={ui.muted}>{meError ?? t("사용량을 불러오는 중…")}</p>
        )}
      </div>
    </section>
  );
}
