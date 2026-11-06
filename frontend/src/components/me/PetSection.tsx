"use client";

import { useState } from "react";

import type { ApiError } from "@/lib/api";
import { josa } from "@/lib/josa";
import type { Pet, SpeciesOption } from "@/lib/types";
import { ui } from "@/lib/ui";

import { btnPrimarySm } from "./common";
import PetCard from "./PetCard";
import PetForm from "./PetForm";

const MAX_PETS = 20; // 서버(app/api/me.py MAX_PETS)와 같다

/** 내 반려동물 목록과 등록·수정·삭제. 한 번에 폼 하나만 연다. */
export default function PetSection({
  pets,
  petsError,
  species,
  speciesError,
  onPetsChange,
  onAuthError,
}: {
  pets: Pet[] | null;
  petsError: string | null;
  species: SpeciesOption[] | null;
  speciesError: string | null;
  onPetsChange: (pets: Pet[]) => void;
  onAuthError: (e: ApiError) => void;
}) {
  /** null: 닫힘 · "new": 새로 등록 · 그 외: 수정 중인 반려동물 id */
  const [editing, setEditing] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const full = (pets?.length ?? 0) >= MAX_PETS;
  const canOpen = !!species && species.length > 0 && !!pets;

  const open = (target: string) => {
    setNotice(null);
    setEditing(target);
  };

  const saved = (pet: Pet) => {
    const list = pets ?? [];
    const exists = list.some((p) => p.id === pet.id);
    onPetsChange(exists ? list.map((p) => (p.id === pet.id ? pet : p)) : [...list, pet]);
    setNotice(exists ? `${pet.name} 정보를 고쳤어요.` : `${josa(pet.name, "을를")} 등록했어요.`);
    setEditing(null);
  };

  const deleted = (id: string) => {
    const gone = pets?.find((p) => p.id === id);
    onPetsChange((pets ?? []).filter((p) => p.id !== id));
    setNotice(gone ? `${gone.name} 정보를 삭제했어요.` : "삭제했어요.");
    if (editing === id) setEditing(null);
  };

  return (
    <section id="pets" aria-labelledby="pets-title" className={`${ui.card} scroll-mt-32`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h2 id="pets-title" className={ui.h2}>
              내 반려동물
            </h2>
            {pets && pets.length > 0 && <span className="text-sm text-stone-500">{pets.length}마리</span>}
          </div>
          <p className="mt-1 text-sm text-stone-600">
            등록해 두면 설계할 때 종·크기·케이지 치수가 자동으로 채워져요.
          </p>
        </div>
        {editing !== "new" && (
          <button
            type="button"
            onClick={() => open("new")}
            disabled={!canOpen || full || editing !== null}
            className={btnPrimarySm}
          >
            반려동물 등록
          </button>
        )}
      </div>

      {full && editing !== "new" && (
        <p className={`${ui.muted} mt-2`}>반려동물은 {MAX_PETS}마리까지 등록할 수 있어요.</p>
      )}
      {speciesError && (
        <p role="alert" className={`${ui.error} mt-3`}>
          종 목록을 불러오지 못해 지금은 등록·수정할 수 없어요. {speciesError}
        </p>
      )}
      {notice && (
        <p role="status" className={`${ui.success} mt-3`}>
          {notice}
        </p>
      )}

      {editing === "new" && species && (
        <div className="mt-4">
          <PetForm species={species} onSaved={saved} onCancel={() => setEditing(null)} onAuthError={onAuthError} />
        </div>
      )}

      <div className="mt-4">
        {petsError ? (
          <p role="alert" className={ui.error}>
            {petsError}
          </p>
        ) : !pets ? (
          <p role="status" className={ui.muted}>
            반려동물 정보를 불러오는 중…
          </p>
        ) : pets.length === 0 ? (
          editing !== "new" && (
            <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50/50 p-6 text-center">
              <p className="mt-2 font-medium">아직 등록한 반려동물이 없어요</p>
              <p className="mt-1 text-sm text-stone-600">
                이름·종·크기·케이지 치수를 저장해 두면 다음 설계 때 자동으로 채워져요.
              </p>
            </div>
          )
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {pets.map((pet) => (
              <li key={pet.id} className={editing === pet.id ? "md:col-span-2" : undefined}>
                {editing === pet.id && species ? (
                  <PetForm
                    pet={pet}
                    species={species}
                    onSaved={saved}
                    onCancel={() => setEditing(null)}
                    onAuthError={onAuthError}
                  />
                ) : (
                  <PetCard
                    pet={pet}
                    onEdit={canOpen ? () => open(pet.id) : undefined}
                    onDeleted={deleted}
                    onAuthError={onAuthError}
                    disabled={editing !== null}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
