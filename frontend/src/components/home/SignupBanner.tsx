import { Link, useT } from "@/i18n/client";

import { IconCheck } from "@/components/home/icons";

const BENEFITS = [
  "만든 설계가 저장돼서 언제든 다시 보고 고칠 수 있어요",
  "반려동물 정보를 등록해 두면 케이지 치수를 다시 입력하지 않아도 돼요",
  "커뮤니티에 글과 댓글을 남기고 내 설계를 공유할 수 있어요",
];

/** 로그인하지 않은 방문자에게 보여 주는 가입 안내 */
export default function SignupBanner({ signupEnabled, emailRequired }: { signupEnabled: boolean; emailRequired: boolean }) {
  const t = useT();
  return (
    <section
      aria-labelledby="join-title"
      className="mt-12 overflow-hidden rounded-3xl bg-[#12302F] px-5 py-8 text-white sm:px-10 sm:py-10"
    >
      <div className="grid gap-6 md:grid-cols-[minmax(0,1.4fr)_auto] md:items-center">
        <div>
          <h2 id="join-title" className="text-balance text-xl font-bold sm:text-2xl">
            {signupEnabled ? t("가입하면 설계를 저장하고 공유할 수 있어요") : t("로그인하면 설계를 저장하고 공유할 수 있어요")}
          </h2>
          <p className="mt-2 text-sm text-teal-50/90 sm:text-base">
            {t("설계 만들기는 회원만 할 수 있어요.")}
            {signupEnabled &&
              (emailRequired
                ? ` ${t("가입은 무료이고, 아이디·닉네임·이메일만 있으면 돼요.")}`
                : ` ${t("가입은 무료이고, 아이디와 닉네임만 있으면 돼요.")}`)}
          </p>
          <ul className="mt-5 space-y-2 text-sm text-teal-50">
            {BENEFITS.map((b) => (
              <li key={b} className="flex items-start gap-2">
                <IconCheck className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
                {t(b)}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row md:flex-col">
          {signupEnabled && (
            <Link
              href="/signup"
              className="inline-flex items-center justify-center rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600"
            >
              {t("회원가입")}
            </Link>
          )}
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-xl border border-white/40 px-6 py-3 font-semibold text-white hover:bg-white/10"
          >
            {t("로그인")}
          </Link>
        </div>
      </div>
    </section>
  );
}
