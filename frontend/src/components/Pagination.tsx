import { Link, useT } from "@/i18n/client";

import { ui } from "@/lib/ui";

/** 목록의 이전/다음 페이지 이동 (페이지 번호는 주소의 ?page= 에 남는다) */
export default function Pagination({
  page,
  totalPages,
  hrefFor,
}: {
  page: number;
  totalPages: number;
  hrefFor: (page: number) => string;
}) {
  const t = useT();
  const disabled = `${ui.btnSecondary} cursor-not-allowed`;
  return (
    <nav aria-label={t("페이지 이동")} className="mt-8 flex items-center justify-center gap-3">
      {page > 1 ? (
        <Link href={hrefFor(page - 1)} rel="prev" className={ui.btnSecondary}>
          {t("이전")}
        </Link>
      ) : (
        <button type="button" disabled className={disabled}>
          {t("이전")}
        </button>
      )}
      <span className="text-sm tabular-nums text-stone-600">
        {t("{page} / {total} 페이지", { page, total: totalPages })}
      </span>
      {page < totalPages ? (
        <Link href={hrefFor(page + 1)} rel="next" className={ui.btnSecondary}>
          {t("다음")}
        </Link>
      ) : (
        <button type="button" disabled className={disabled}>
          {t("다음")}
        </button>
      )}
    </nav>
  );
}
