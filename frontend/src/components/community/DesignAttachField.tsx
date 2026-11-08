"use client";

import { Link, useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { useEffect, useState } from "react";

import { errorText } from "@/components/community/common";
import { api, isAuthError } from "@/lib/api";
import type { Design, DesignListItem, Habitat } from "@/lib/types";
import { ui } from "@/lib/ui";

/** 글에 첨부할 수 있는 내 설계 (첨부할 버전까지) */
export type AttachOption = {
  id: string;
  title: string;
  version: number;
  /** 첨부할 버전의 검증 결과 (모르면 null) */
  passed: boolean | null;
  habitat: Habitat;
};

export type AttachState =
  | { kind: "loading" }
  | { kind: "ok"; options: AttachOption[]; preselect: string | null; missing: boolean }
  | { kind: "error"; message: string; authCode: string | null };

const LIST_SIZE = 50; // 백엔드 최대 page_size

const fromListItem = (d: DesignListItem): AttachOption => ({
  id: d.id,
  title: d.title,
  version: d.latest_version,
  passed: d.latest_passed,
  habitat: d.habitat,
});

const fromDesign = (d: Design): AttachOption => ({
  id: d.id,
  title: d.title,
  version: d.current.version,
  passed: d.current.validation.passed,
  habitat: d.habitat,
});

export const optionLabel = (o: AttachOption, t: TFunction) => `${o.title || t("제목 없는 설계")} · v${o.version}`;

/**
 * 첨부할 수 있는 내 설계 목록을 불러온다 (최근 50개).
 * 설계 화면의 "커뮤니티에 공유"로 들어오면(?design=&version=) 그 설계·버전을 미리 고른다.
 * 목록에 없는 오래된 설계여도 따로 불러와 앞에 넣는다.
 */
export function useAttachOptions(userId: string | null, preId: string | null, preVersion: number | undefined) {
  const t = useT();
  const key = `${userId}|${preId}|${preVersion}`;
  const [result, setResult] = useState<{ key: string; state: AttachState } | null>(null);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    const pre: Promise<AttachOption | null> = preId
      ? api.getDesign(preId, preVersion).then(
          (d) => (d.is_owner ? fromDesign(d) : null), // 남의 공유 설계는 첨부할 수 없다
          (e: unknown) => (isAuthError(e) ? Promise.reject(e) : null),
        )
      : Promise.resolve(null);
    Promise.all([api.listDesigns(1, LIST_SIZE), pre]).then(
      ([list, preOpt]) => {
        if (!alive) return;
        const options = list.items.map(fromListItem);
        let preselect: string | null = null;
        if (preOpt) {
          const i = options.findIndex((o) => o.id === preOpt.id);
          if (i >= 0) options[i] = preOpt;
          else options.unshift(preOpt);
          preselect = preOpt.id;
        } else if (preId && options.some((o) => o.id === preId)) {
          preselect = preId; // 요청한 버전을 찾지 못하면 최신 버전으로
        }
        setResult({ key, state: { kind: "ok", options, preselect, missing: preId !== null && preselect === null } });
      },
      (e: unknown) => {
        if (!alive) return;
        setResult({
          key,
          state: {
            kind: "error",
            message: errorText(e, t("내 설계 목록을 불러오지 못했어요.")),
            authCode: isAuthError(e) ? (e.code ?? null) : null,
          },
        });
      },
    );
    return () => {
      alive = false;
    };
  }, [userId, preId, preVersion, key, t]);

  // 로그인이 풀린 경우에는 마지막으로 불러온 목록을 그대로 둔다 (쓰던 글을 지키려고 폼을 남겨 둘 때)
  if (result && (result.key === key || userId === null)) return result.state;
  return { kind: "loading" } as const;
}

/** "설계 첨부" 선택 + 고른 설계 미리 보기 */
export default function DesignAttachField({
  state,
  value,
  onChange,
  disabled = false,
}: {
  state: AttachState;
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const t = useT();
  const options = state.kind === "ok" ? state.options : [];
  const picked = options.find((o) => o.id === value) ?? null;
  const h = picked?.habitat;

  return (
    <div>
      <label htmlFor="post-design" className={ui.label}>
        {t("설계 첨부")}
      </label>
      <select
        id="post-design"
        className={ui.input}
        value={picked ? picked.id : ""}
        disabled={disabled || state.kind === "loading"}
        aria-describedby="post-design-help"
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{t("첨부하지 않음")}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {optionLabel(o, t)}
          </option>
        ))}
      </select>

      <div id="post-design-help" className="mt-2 space-y-2 text-sm">
        {state.kind === "loading" && <p className="text-stone-500">{t("내 설계를 불러오는 중이에요…")}</p>}
        {state.kind === "error" && (
          <p role="alert" className={ui.error}>
            {state.message} {t("설계 없이 글을 올릴 수는 있어요.")}
          </p>
        )}
        {state.kind === "ok" && state.missing && (
          <p role="status" className="rounded-lg bg-amber-50 p-3 text-amber-900">
            {t("공유하려던 설계를 찾지 못해 첨부하지 않았어요. 목록에서 다시 골라 주세요.")}
          </p>
        )}
        {state.kind === "ok" && options.length === 0 && (
          <p className="text-stone-500">
            {t("아직 첨부할 설계가 없어요.")}{" "}
            <Link href="/design" className={ui.link}>
              {t("설계를 만들면")}
            </Link>{" "}
            {t("글에 첨부해서 보여 줄 수 있어요.")}
          </p>
        )}
        {picked && h && (
          <div className="rounded-xl border border-teal-200 bg-teal-50 p-3 text-teal-900">
            <p className="break-words">
              <span className="font-medium">v{picked.version}</span> ·{" "}
              {t("{species} {size} · {n}마리", { species: t(h.species_name_ko), size: t(h.size_name_ko), n: h.count })} ·{" "}
              {t("케이지 {w}×{d}×{h}mm", { w: h.cage.width_mm, d: h.cage.depth_mm, h: h.cage.height_mm })}
              {picked.passed !== null && <> · {picked.passed ? t("통과") : t("검증 실패")}</>}
            </p>
            <p className="mt-1 text-xs">
              {t(
                "선택한 버전(v{v})만 누구나 볼 수 있게 공개돼요. 나중에 고친 버전은 따로 공유하기 전까지 나만 볼 수 있어요.",
                { v: picked.version },
              )}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
