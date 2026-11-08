"use client";

import type { Ref } from "react";

import { useT } from "@/i18n/client";
import { CharCount, LIMITS, oneLine } from "@/components/community/common";
import { ui } from "@/lib/ui";

/** 글쓰기·글 수정에서 함께 쓰는 "제목"·"내용" 입력 */
export default function PostFields({
  idPrefix,
  title,
  body,
  onTitle,
  onBody,
  disabled = false,
  invalid = false,
  titleRef,
}: {
  idPrefix: string;
  title: string;
  body: string;
  onTitle: (v: string) => void;
  onBody: (v: string) => void;
  disabled?: boolean;
  invalid?: boolean;
  titleRef?: Ref<HTMLInputElement>;
}) {
  const t = useT();
  const titleId = `${idPrefix}-title`;
  const bodyId = `${idPrefix}-body`;
  const countId = `${idPrefix}-body-count`;
  return (
    <>
      <div>
        <label htmlFor={titleId} className={ui.label}>
          {t("제목")}
        </label>
        <input
          ref={titleRef}
          id={titleId}
          type="text"
          className={ui.input}
          value={title}
          maxLength={LIMITS.title}
          autoComplete="off"
          enterKeyHint="next"
          disabled={disabled}
          aria-invalid={invalid && !title.trim() ? true : undefined}
          onChange={(e) => onTitle(oneLine(e.target.value))}
          onKeyDown={(e) => {
            // 제목에서 Enter 를 누르면 글을 바로 올리지 않고 내용 입력으로 넘어간다 (한글 조합 중인 Enter 는 그대로)
            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
              e.preventDefault();
              document.getElementById(bodyId)?.focus();
            }
          }}
        />
      </div>
      <div>
        <label htmlFor={bodyId} className={ui.label}>
          {t("내용")}
        </label>
        <textarea
          id={bodyId}
          rows={10}
          className={`${ui.input} min-h-[12rem] resize-y leading-relaxed`}
          value={body}
          maxLength={LIMITS.body}
          disabled={disabled}
          aria-describedby={countId}
          aria-invalid={invalid && !body.trim() ? true : undefined}
          onChange={(e) => onBody(e.target.value)}
        />
        <CharCount id={countId} length={body.length} max={LIMITS.body} />
      </div>
    </>
  );
}
