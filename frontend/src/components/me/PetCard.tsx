"use client";

import Link from "next/link";
import { useId, useState } from "react";

import { api, ApiError, isAuthError } from "@/lib/api";
import type { Pet } from "@/lib/types";
import { ui } from "@/lib/ui";

import { btnPrimarySm, formatCage, formatYmd, petAge, SEX_LABEL } from "./common";

/** 반려동물 한 마리 카드: 정보, 이 아이로 설계하기·수정·삭제(한 번 더 확인) */
export default function PetCard({
  pet,
  onEdit,
  onDeleted,
  onAuthError,
  disabled = false,
}: {
  pet: Pet;
  /** 없으면 수정 버튼을 막는다 (종 목록을 불러오지 못한 경우) */
  onEdit?: () => void;
  onDeleted: (id: string) => void;
  onAuthError: (e: ApiError) => void;
  /** 다른 반려동물의 폼이 열려 있는 동안에는 수정·삭제를 잠시 막는다 */
  disabled?: boolean;
}) {
  const uid = useId();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const age = pet.birth_date ? petAge(pet.birth_date) : null;

  async function remove() {
    setDeleting(true);
    setError(null);
    try {
      await api.deletePet(pet.id);
      onDeleted(pet.id);
    } catch (err) {
      setDeleting(false);
      if (isAuthError(err)) onAuthError(err as ApiError);
      else if (err instanceof ApiError && err.status === 404) onDeleted(pet.id); // 이미 지워진 경우
      else setError(err instanceof ApiError ? err.messageKo : "삭제하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
    }
  }

  return (
    <article aria-labelledby={`${uid}-name`} className="flex h-full flex-col rounded-2xl border border-stone-200 bg-white p-4">
      <div className="flex items-start gap-3">
        <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-amber-100 text-xl">
          🐹
        </span>
        <div className="min-w-0">
          <h3 id={`${uid}-name`} className="break-words text-lg font-semibold">
            {pet.name}
          </h3>
          <p className="mt-0.5 text-sm text-stone-600">
            {pet.species_name_ko} · {pet.size_name_ko}
          </p>
        </div>
      </div>

      <dl className="mt-3 space-y-1 text-sm">
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-stone-500">성별</dt>
          <dd>{SEX_LABEL[pet.sex] ?? "모름"}</dd>
        </div>
        {pet.birth_date && (
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-stone-500">생일</dt>
            <dd>
              {formatYmd(pet.birth_date)}
              {age && <span className="text-stone-500"> ({age})</span>}
            </dd>
          </div>
        )}
        {pet.cage && (
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-stone-500">케이지</dt>
            <dd>{formatCage(pet.cage)}</dd>
          </div>
        )}
      </dl>
      {pet.notes && (
        <p className="mt-3 whitespace-pre-wrap break-words rounded-lg bg-stone-50 p-3 text-sm text-stone-700">{pet.notes}</p>
      )}

      {error && (
        <p role="alert" className={`${ui.error} mt-3`}>
          {error}
        </p>
      )}

      <div className="mt-auto pt-4">
        {confirming ? (
          <div role="group" aria-label="삭제 확인" className="rounded-xl border border-red-200 bg-red-50 p-3">
            <p className="text-sm text-red-800">
              <span className="break-words font-semibold">{pet.name}</span> 정보를 삭제할까요? 이 아이로 만든 설계는
              그대로 남아요.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={remove}
                disabled={deleting}
                className="inline-flex items-center justify-center rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deleting ? "삭제하는 중…" : "네, 삭제할게요"}
              </button>
              <button type="button" onClick={() => setConfirming(false)} disabled={deleting} className={ui.btnSecondary}>
                아니요
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/design?pet=${encodeURIComponent(pet.id)}`} className={btnPrimarySm}>
              이 아이로 설계하기
            </Link>
            <button type="button" onClick={onEdit} disabled={disabled || !onEdit} className={ui.btnSecondary}>
              수정
            </button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setConfirming(true);
              }}
              disabled={disabled}
              className={ui.btnDanger}
            >
              삭제
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
