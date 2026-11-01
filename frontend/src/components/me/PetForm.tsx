"use client";

import { useEffect, useId, useState } from "react";

import { api, ApiError, isAuthError } from "@/lib/api";
import type { Pet, PetInput, PetSex, SpeciesOption } from "@/lib/types";
import { ui } from "@/lib/ui";

import {
  BIRTH_MIN,
  CAGE_DIMS,
  CAGE_LIMITS,
  CAGE_PRESETS,
  charCount,
  describedBy,
  FieldError,
  hasControlChars,
  inputClass,
  SEX_LABEL,
  todayLocal,
} from "./common";

type CageKey = "w" | "d" | "h";
type Values = {
  name: string;
  species: string;
  size: string;
  sex: PetSex;
  birth: string;
  notes: string;
  cage: Record<CageKey, string>;
};
type Key = "name" | "species" | "size" | "birth" | "notes" | "cage" | CageKey;
type Errors = Partial<Record<Key, string>>;

const ORDER: Key[] = ["name", "species", "size", "birth", "notes", "w", "d", "h"];
const NOTES_MAX = 500;
const SEXES: PetSex[] = ["male", "female", "unknown"];
const EMPTY_CAGE = { w: "", d: "", h: "" };

function initialValues(pet: Pet | undefined, species: SpeciesOption[]): Values {
  if (pet) {
    const sp = species.find((s) => s.key === pet.species);
    return {
      name: pet.name,
      species: sp ? pet.species : (species[0]?.key ?? ""),
      size: sp?.sizes.some((z) => z.key === pet.size) ? pet.size : "",
      sex: pet.sex,
      birth: pet.birth_date ?? "",
      notes: pet.notes ?? "",
      cage: pet.cage
        ? { w: String(pet.cage.width_mm), d: String(pet.cage.depth_mm), h: String(pet.cage.height_mm) }
        : EMPTY_CAGE,
    };
  }
  const sp = species.find((s) => s.key === "hamster") ?? species[0];
  return { name: "", species: sp?.key ?? "", size: "", sex: "unknown", birth: "", notes: "", cage: EMPTY_CAGE };
}

/** 서버 검증(PetIn)과 같은 규칙. 최종 판단은 서버가 한다. */
function validate(v: Values, species: SpeciesOption[], today: string): Errors {
  const errors: Errors = {};
  const name = v.name.trim();
  if (!name) errors.name = "이름을 입력해 주세요.";
  else if (hasControlChars(name)) errors.name = "이름에 쓸 수 없는 문자가 있어요.";
  else if (charCount(name) > 40) errors.name = "이름은 40자 이하로 입력해 주세요.";

  const sp = species.find((s) => s.key === v.species);
  if (!sp) errors.species = "종을 골라 주세요.";
  else if (!sp.sizes.some((z) => z.key === v.size)) errors.size = "크기를 골라 주세요.";

  if (v.birth && (!/^\d{4}-\d{2}-\d{2}$/.test(v.birth) || v.birth < BIRTH_MIN || v.birth > today))
    errors.birth = "생일은 1990년 1월 1일부터 오늘 사이로 입력해 주세요.";

  const notes = v.notes.trim();
  if (hasControlChars(notes, true)) errors.notes = "메모에 쓸 수 없는 문자가 있어요.";
  else if (charCount(notes) > NOTES_MAX) errors.notes = `메모는 ${NOTES_MAX}자 이하로 적어 주세요.`;

  const filled = CAGE_DIMS.filter(([k]) => v.cage[k].trim() !== "");
  if (filled.length > 0 && filled.length < 3) {
    errors.cage = "가로·세로·높이를 모두 입력하거나, 치수 비우기를 눌러 주세요.";
    for (const [k] of CAGE_DIMS) if (!v.cage[k].trim()) errors[k] = "입력해 주세요.";
  } else if (filled.length === 3) {
    for (const [k, label] of CAGE_DIMS) {
      const n = Number(v.cage[k]);
      const [lo, hi] = CAGE_LIMITS[k];
      if (!Number.isFinite(n) || n < lo || n > hi) errors[k] = `${label}는 ${lo}~${hi}mm 사이로 입력해 주세요.`;
    }
  }
  return errors;
}

function toInput(v: Values): PetInput {
  const hasCage = CAGE_DIMS.every(([k]) => v.cage[k].trim() !== "");
  return {
    name: v.name.trim(),
    species: v.species,
    size: v.size,
    sex: v.sex,
    birth_date: v.birth || null,
    notes: v.notes.trim() || null,
    cage: hasCage ? { width_mm: Number(v.cage.w), depth_mm: Number(v.cage.d), height_mm: Number(v.cage.h) } : null,
  };
}

/** 서버 입력 검증 오류(422)에서 생일 칸 오류를 알아본다 (서버의 '오늘'이 기기와 하루 다를 수 있다) */
function isBirthDateError(err: ApiError): boolean {
  return (
    err.status === 422 &&
    Array.isArray(err.details) &&
    err.details.some((d) => Array.isArray((d as { loc?: unknown }).loc) && (d as { loc: unknown[] }).loc.includes("birth_date"))
  );
}

/** 반려동물 등록·수정 폼 (목록 안에 펼쳐지는 패널) */
export default function PetForm({
  pet,
  species,
  onSaved,
  onCancel,
  onAuthError,
}: {
  pet?: Pet;
  species: SpeciesOption[];
  onSaved: (pet: Pet) => void;
  onCancel: () => void;
  onAuthError: (e: ApiError) => void;
}) {
  const uid = useId();
  const id = (k: string) => `${uid}-${k}`;
  // 폼은 버튼을 눌러 열 때만 그려지므로(서버 렌더 없음) 여기서 오늘 날짜를 읽어도 된다
  const [today] = useState(todayLocal);
  const [values, setValues] = useState<Values>(() => initialValues(pet, species));
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 폼이 열리면 이름 칸으로 커서를 옮긴다
  const nameId = id("name");
  useEffect(() => {
    const el = document.getElementById(nameId);
    el?.focus({ preventScroll: true });
    el?.closest("form")?.scrollIntoView({ block: "nearest" });
  }, [nameId]);

  const errors = submitted ? validate(values, species, today) : {};
  const sizes = species.find((s) => s.key === values.species)?.sizes ?? [];
  const notesCount = charCount(values.notes.trim());
  const title = pet ? "반려동물 정보 수정" : "반려동물 등록";

  const set = <K extends keyof Values>(k: K, value: Values[K]) => {
    setValues((prev) => ({ ...prev, [k]: value }));
    setError(null);
  };
  const setCage = (cage: Record<CageKey, string>) => set("cage", cage);
  const focus = (k: Key) => document.getElementById(id(k))?.focus();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitted(true);
    const errs = validate(values, species, today);
    const first = ORDER.find((k) => errs[k]);
    if (first) {
      focus(first);
      return;
    }
    setSubmitting(true);
    try {
      const body = toInput(values);
      const saved = pet ? await api.updatePet(pet.id, body) : await api.createPet(body);
      onSaved(saved);
    } catch (err) {
      setSubmitting(false);
      if (isAuthError(err)) return onAuthError(err as ApiError);
      if (err instanceof ApiError && isBirthDateError(err)) {
        setError("생일은 1990년 1월 1일부터 오늘 사이로 입력해 주세요.");
        focus("birth");
      } else {
        setError(err instanceof ApiError ? err.messageKo : "저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
      }
    }
  }

  // 케이지 칸 일부만 채운 경우에는 칸마다가 아니라 치수 묶음 아래에 한 번만 알려 준다
  const errorIdOf = (k: Key) =>
    errors.cage && (k === "w" || k === "d" || k === "h") ? id("cage-error") : errors[k] && id(`${k}-error`);
  const field = (k: Key, hint?: boolean) => ({
    id: id(k),
    "aria-invalid": errors[k] ? true : undefined,
    "aria-describedby": describedBy(errors[k] && errorIdOf(k), hint && id(`${k}-hint`)),
    className: inputClass(!!errors[k]),
  });

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-labelledby={id("title")}
      className="space-y-4 rounded-2xl border border-amber-300 bg-amber-50/40 p-4 sm:p-5"
    >
      <h3 id={id("title")} className="font-semibold">
        {title}
      </h3>

      <div>
        <label htmlFor={id("name")} className={ui.label}>
          이름
        </label>
        <input
          {...field("name")}
          name="pet-name"
          autoComplete="off"
          required
          value={values.name}
          onChange={(e) => set("name", e.target.value)}
        />
        <FieldError id={id("name-error")} message={errors.name} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={id("species")} className={ui.label}>
            종
          </label>
          <select
            {...field("species")}
            value={values.species}
            onChange={(e) => setValues((prev) => ({ ...prev, species: e.target.value, size: "" }))}
          >
            {species.map((s) => (
              <option key={s.key} value={s.key}>
                {s.display_name}
              </option>
            ))}
          </select>
          <FieldError id={id("species-error")} message={errors.species} />
        </div>
        <div>
          <label htmlFor={id("size")} className={ui.label}>
            크기
          </label>
          <select {...field("size")} value={values.size} onChange={(e) => set("size", e.target.value)}>
            <option value="" disabled>
              크기를 골라 주세요
            </option>
            {sizes.map((z) => (
              <option key={z.key} value={z.key}>
                {z.display_name}
              </option>
            ))}
          </select>
          <FieldError id={id("size-error")} message={errors.size} />
        </div>
      </div>

      <fieldset>
        <legend className={ui.label}>성별</legend>
        <div className="flex flex-wrap gap-2">
          {SEXES.map((s) => (
            <label
              key={s}
              className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                values.sex === s ? "border-amber-500 bg-amber-50" : "border-stone-300 bg-white"
              }`}
            >
              <input
                type="radio"
                name={id("sex")}
                value={s}
                checked={values.sex === s}
                onChange={() => set("sex", s)}
                className="accent-amber-500"
              />
              {SEX_LABEL[s]}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <div className="flex items-baseline justify-between gap-2">
          <label htmlFor={id("birth")} className={ui.label}>
            생일
          </label>
          <span className="text-xs text-stone-500">선택</span>
        </div>
        <div className="flex gap-2">
          <input
            {...field("birth")}
            className={`${field("birth").className} min-w-0`}
            type="date"
            min={BIRTH_MIN}
            max={today}
            value={values.birth}
            onChange={(e) => set("birth", e.target.value)}
          />
          {values.birth && (
            <button type="button" onClick={() => set("birth", "")} className={`${ui.btnSecondary} shrink-0`}>
              생일 지우기
            </button>
          )}
        </div>
        <FieldError id={id("birth-error")} message={errors.birth} />
      </div>

      <div>
        <div className="flex items-baseline justify-between gap-2">
          <label htmlFor={id("notes")} className={ui.label}>
            메모
          </label>
          <span className="text-xs text-stone-500">선택</span>
        </div>
        <textarea
          {...field("notes", true)}
          rows={3}
          placeholder="예: 겁이 많아서 은신처를 좋아해요"
          value={values.notes}
          onChange={(e) => set("notes", e.target.value)}
        />
        <FieldError id={id("notes-error")} message={errors.notes} />
        <p
          id={id("notes-hint")}
          className={`mt-1 text-right text-xs ${notesCount > NOTES_MAX ? "font-semibold text-red-700" : "text-stone-500"}`}
        >
          {notesCount}/{NOTES_MAX}
        </p>
      </div>

      <fieldset>
        <legend className={ui.label}>
          케이지 내부 치수 <span className="font-normal text-stone-500">(선택)</span>
        </legend>
        <p className="mb-2 text-xs text-stone-500">
          저장해 두면 설계할 때 자동으로 채워져요. 모르면 비워 두어도 돼요.
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {CAGE_PRESETS.map((p) => {
            const active = Number(values.cage.w) === p.w && Number(values.cage.d) === p.d && Number(values.cage.h) === p.h;
            return (
              <button
                key={p.label}
                type="button"
                aria-pressed={active}
                onClick={() => setCage({ w: String(p.w), d: String(p.d), h: String(p.h) })}
                className={`rounded-full border px-3 py-1 text-sm ${
                  active ? "border-amber-500 bg-amber-100" : "border-stone-300 bg-white hover:bg-stone-50"
                }`}
              >
                {p.label}
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setCage(EMPTY_CAGE)}
            disabled={CAGE_DIMS.every(([k]) => !values.cage[k])}
            className="rounded-full border border-stone-300 bg-white px-3 py-1 text-sm text-stone-600 hover:bg-stone-50 disabled:opacity-50"
          >
            치수 비우기
          </button>
        </div>
        <div className="grid grid-cols-3 gap-2 sm:gap-3">
          {CAGE_DIMS.map(([k, label]) => (
            <div key={k} className="min-w-0">
              <label htmlFor={id(k)} className="mb-1 block text-xs text-stone-600">
                {label} (mm)
              </label>
              <input
                {...field(k)}
                type="number"
                inputMode="decimal"
                min={CAGE_LIMITS[k][0]}
                max={CAGE_LIMITS[k][1]}
                value={values.cage[k]}
                onChange={(e) => setCage({ ...values.cage, [k]: e.target.value })}
              />
              <FieldError id={id(`${k}-error`)} message={errors.cage ? undefined : errors[k]} />
            </div>
          ))}
        </div>
        <FieldError id={id("cage-error")} message={errors.cage} />
      </fieldset>

      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" onClick={onCancel} disabled={submitting} className={ui.btnSecondary}>
          취소
        </button>
        <button type="submit" disabled={submitting} className={ui.btnPrimary}>
          {submitting ? "저장 중…" : "저장"}
        </button>
      </div>
    </form>
  );
}
