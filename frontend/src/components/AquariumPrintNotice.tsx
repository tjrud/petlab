"use client";

import { useId } from "react";

import { Link, useT } from "@/i18n/client";
import { AQUARIUM_PRINT_POST_HREF } from "@/lib/habitatKind";

/**
 * 어항에 넣을 출력물 안전 안내: 종 규칙의 print_notes_ko (첫 줄은 머리말, 나머지는 조건 목록) + 근거를 정리한 커뮤니티 글.
 * 안내 문구는 서버가 화면 언어로 보내 준다 (영어 화면이면 항목마다 번역). 옛 서버 응답처럼 목록이 비어도 글 링크는 보인다.
 * 글은 새 탭으로 열어 쓰던 입력을 잃지 않게 한다.
 */
export default function AquariumPrintNotice({ notes, className = "" }: { notes: readonly string[]; className?: string }) {
  const t = useT();
  const titleId = useId();
  const [lead, ...rest] = notes;
  return (
    <section
      aria-labelledby={titleId}
      data-testid="aquarium-print-notice"
      className={`rounded-xl border border-sky-200 bg-sky-50/70 p-4 text-sm text-sky-950 ${className}`}
    >
      <h3 id={titleId} className="font-semibold">
        {t("어항에 넣을 출력물 안전 안내")}
      </h3>
      {lead ? (
        <p className="mt-1">{lead}</p>
      ) : (
        <p className="mt-1">{t("소재·노즐·채움·세척 조건을 지켜야 어항에 넣어도 위험이 낮아요. 아래 글에서 확인해 주세요.")}</p>
      )}
      {rest.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 leading-relaxed">
          {rest.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <p className="mt-3">
        <Link
          href={AQUARIUM_PRINT_POST_HREF}
          target="_blank"
          rel="noopener"
          className="font-medium text-sky-800 underline underline-offset-2 hover:text-sky-950"
        >
          {t("근거와 자세한 설명: 커뮤니티 글 「어항에 3D 출력물, 수질 면에서 써도 될까요」")}
        </Link>
      </p>
    </section>
  );
}
