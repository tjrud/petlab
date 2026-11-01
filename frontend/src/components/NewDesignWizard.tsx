"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import LoginRequired from "@/components/LoginRequired";
import { CAGE_LIMITS, CAGE_PRESETS } from "@/components/me/common";
import { api, ApiError, isAuthError } from "@/lib/api";
import type { Me, Pet, SpeciesResponse } from "@/lib/types";

const EXAMPLE_PROMPTS = [
  "은신처와 터널을 한쪽에 몰아서 넣고 싶어요",
  "은신처를 오른쪽 구석에 넣고, 환기구는 넉넉하게 해 주세요",
  "모래목욕통과 계단을 넣고 가운데는 넓게 비워 주세요",
];

const LIMITS = { ...CAGE_LIMITS, count: [1, 10] } as const;

const LOGIN_MESSAGE = "로그인하고 맞춤 설계를 시작해 보세요";
const LOGIN_DESCRIPTION = "회원이 되면 설계 내역이 저장되고 커뮤니티에 공유할 수 있어요.";

type Step = 1 | 2;
type Quota = Me["design_quota"];

/** 로그인 상태를 확인하는 동안(그리고 페이지의 Suspense 대기 중) 보여 주는 자리 */
export function WizardSkeleton() {
  return (
    <div className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm sm:p-8">
      <p role="status" className="py-10 text-center text-sm text-stone-500">
        설계 화면을 준비하고 있어요…
      </p>
    </div>
  );
}

/** 최근 24시간 설계 횟수를 모두 쓴 경우의 안내 */
function QuotaExhausted({ limit }: { limit: number | null }) {
  return (
    <p role="status" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
      최근 24시간 동안 쓸 수 있는 설계 횟수{limit !== null ? `(${limit}회)` : ""}를 모두 썼어요. 시간이 조금 지나면 다시
      설계할 수 있어요.
    </p>
  );
}

export default function NewDesignWizard() {
  const router = useRouter();
  const { status, user } = useAuth();
  const userId = user?.id ?? null;
  // /design?pet={id}: 내 정보의 "이 아이로 설계하기"에서 들어온 경우 그 반려동물로 미리 채운다
  const wantedPet = useSearchParams().get("pet");
  const petSelectId = useId();
  const [meta, setMeta] = useState<SpeciesResponse | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>(1);

  const [species, setSpecies] = useState("hamster");
  const [size, setSize] = useState("syrian");
  const [count, setCount] = useState(1);
  const [cage, setCage] = useState({ w: 600, d: 400, h: 300 });
  const [prompt, setPrompt] = useState("");

  const [habitatId, setHabitatId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [pets, setPets] = useState<Pet[] | null>(null);
  /** 값을 채워 온 반려동물 (종·크기를 고쳐도 그대로 두고, "직접 입력"을 고르면 지운다) */
  const [petId, setPetId] = useState<string | null>(null);
  const [petNotice, setPetNotice] = useState<string | null>(null);
  const [quota, setQuota] = useState<Quota | null>(null);
  // 주소의 ?pet= 은 한 번만 적용한다 (뒤로 가기로 돌아와 다시 불러올 때 고친 값을 덮어쓰지 않게)
  const appliedPetParam = useRef<string | null>(null);

  // 종 목록은 누구나 볼 수 있다
  useEffect(() => {
    let alive = true;
    api
      .species()
      .then((m) => alive && setMeta(m))
      .catch((e: unknown) => {
        if (!alive) return;
        if (isAuthError(e)) setAuthError(e as ApiError);
        else setMetaError(e instanceof ApiError ? e.messageKo : "정보를 불러오지 못했어요.");
      });
    return () => {
      alive = false;
    };
  }, []);

  const applyPet = useCallback((p: Pet) => {
    setPetId(p.id);
    setPetNotice(null);
    setSpecies(p.species);
    setSize(p.size);
    if (p.cage) setCage({ w: p.cage.width_mm, d: p.cage.depth_mm, h: p.cage.height_mm });
    setHabitatId(null);
  }, []);

  // 로그인한 경우: 내 반려동물(미리 채우기)과 남은 설계 횟수
  useEffect(() => {
    if (!userId) return;
    let alive = true;
    api
      .pets()
      .then((list) => {
        if (!alive) return;
        setPets(list);
        if (wantedPet && appliedPetParam.current !== wantedPet) {
          appliedPetParam.current = wantedPet;
          const p = list.find((x) => x.id === wantedPet);
          if (p) applyPet(p);
          else setPetNotice("선택한 반려동물 정보를 찾지 못했어요. 직접 입력해 주세요.");
        }
      })
      .catch((e: unknown) => {
        if (alive && isAuthError(e)) setAuthError(e as ApiError); // 세션이 만료된 경우
        // 그 밖의 오류는 미리 채우기만 건너뛴다 (직접 입력은 그대로 할 수 있다)
      });
    api
      .me()
      .then((m) => alive && setQuota(m.design_quota))
      .catch(() => {
        /* 남은 횟수 표시만 건너뛴다 (서버가 최종 판단) */
      });
    return () => {
      alive = false;
    };
  }, [userId, wantedPet, applyPet]);

  const speciesOpt = meta?.species.find((s) => s.key === species);
  const sizeOpt = speciesOpt?.sizes.find((s) => s.key === size);
  const selectedPet = pets?.find((p) => p.id === petId) ?? null;
  const quotaExhausted = quota?.remaining === 0;

  const habitatErrors = useMemo(() => {
    const errs: string[] = [];
    const check = (v: number, [lo, hi]: readonly [number, number], name: string) => {
      if (!Number.isFinite(v) || v < lo || v > hi) errs.push(`${name}는 ${lo}~${hi}mm 사이로 입력해 주세요.`);
    };
    check(cage.w, LIMITS.w, "가로");
    check(cage.d, LIMITS.d, "세로");
    check(cage.h, LIMITS.h, "높이");
    if (!Number.isInteger(count) || count < LIMITS.count[0] || count > LIMITS.count[1])
      errs.push("마릿수는 1~10 사이로 입력해 주세요.");
    return errs;
  }, [cage, count]);

  // 사육 환경이 바뀌면 이전에 등록한 환경을 다시 쓰지 않는다
  const resetHabitat = () => setHabitatId(null);

  async function submit() {
    setError(null);
    if (!prompt.trim()) {
      setError("원하는 구조물이나 배치를 적어 주세요.");
      return;
    }
    setSubmitting(true);
    try {
      let hid = habitatId;
      if (!hid) {
        const h = await api.createHabitat({
          species,
          size,
          count,
          cage: { width_mm: cage.w, depth_mm: cage.d, height_mm: cage.h },
          pet_id: petId,
        });
        hid = h.id;
        setHabitatId(hid);
      }
      const design = await api.createDesign(hid, prompt.trim());
      router.push(`/designs/${design.id}`);
      // 이전 화면은 숨김 상태로 유지되므로(뒤로 가기 시 복원) 진행 상태를 풀어 둔다
      setSubmitting(false);
    } catch (e) {
      if (isAuthError(e)) setAuthError(e as ApiError); // 사용 중 세션이 만료된 경우
      else if (e instanceof ApiError && e.code === "design_quota_exceeded" && quota && quota.limit !== null)
        setQuota({ ...quota, used: Math.max(quota.used, quota.limit), remaining: 0 }); // 아래 안내로 알려 준다
      else setError(e instanceof ApiError ? e.messageKo : "설계 중 문제가 생겼어요. 다시 시도해 주세요.");
      setSubmitting(false);
    }
  }

  if (authError) {
    return (
      <LoginRequired
        unavailable={authError.code === "auth_unavailable"}
        message={LOGIN_MESSAGE}
        description={LOGIN_DESCRIPTION}
      />
    );
  }
  if (!status) return <WizardSkeleton />;
  if (!user) return <LoginRequired message={LOGIN_MESSAGE} description={LOGIN_DESCRIPTION} />;

  return (
    <div className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm sm:p-8">
      <ol className="mb-6 flex items-center gap-3 text-sm" aria-label="진행 단계">
        {(["사육 환경", "요구사항"] as const).map((label, i) => {
          const n = (i + 1) as Step;
          const active = step === n;
          return (
            <li key={label} className="flex items-center gap-2">
              <span
                className={`grid h-7 w-7 place-items-center rounded-full font-semibold ${
                  active ? "bg-amber-500 text-white" : step > n ? "bg-amber-200 text-amber-900" : "bg-stone-200 text-stone-500"
                }`}
              >
                {n}
              </span>
              <span className={active ? "font-semibold" : "text-stone-500"}>{label}</span>
              {i === 0 && <span className="mx-1 h-px w-8 bg-stone-300" aria-hidden />}
            </li>
          );
        })}
        {meta?.llm_provider === "mock" && (
          <li className="ml-auto rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-800">
            개발용 모의 해석기
          </li>
        )}
      </ol>

      {metaError && <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{metaError}</p>}
      {meta && !meta.storage_persistent && (
        <p role="status" className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          ⚠️ 지금은 임시 저장소로 운영 중이에요. 만든 설계가 잠시 뒤 사라지거나 다시 열리지 않을 수 있으니, 필요한 파일은 바로
          내려받아 주세요.
        </p>
      )}

      {step === 1 && (
        <section aria-labelledby="habitat-title" className="space-y-6">
          <h2 id="habitat-title" className="text-xl font-bold">
            사육 환경을 알려 주세요
          </h2>

          {pets && pets.length > 0 && (
            <div className="rounded-xl bg-amber-50 p-4">
              <label htmlFor={petSelectId} className="mb-1 block text-sm font-medium">
                내 반려동물
              </label>
              <select
                id={petSelectId}
                className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2"
                value={petId ?? ""}
                onChange={(e) => {
                  const p = pets.find((x) => x.id === e.target.value);
                  if (p) applyPet(p);
                  else {
                    setPetId(null); // 직접 입력: 지금 값은 그대로 두고 반려동물 연결만 끊는다
                    resetHabitat();
                  }
                }}
              >
                <option value="">직접 입력</option>
                {pets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {`${p.name} · ${p.size_name_ko}`}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-stone-600">
                {selectedPet && !selectedPet.cage
                  ? "등록된 케이지 치수가 없어서 종·크기만 채웠어요. 아래 치수를 확인해 주세요."
                  : "고르면 종·크기와 케이지 치수를 채워 드려요. 채운 뒤에도 고칠 수 있어요."}
              </p>
            </div>
          )}
          {pets && pets.length === 0 && (
            <p className="text-sm">
              <span aria-hidden>💡 </span>
              <Link href="/me#pets" className="text-amber-700 underline-offset-2 hover:underline">
                내 정보에서 반려동물을 등록하면 다음부터 자동으로 채워져요
              </Link>
            </p>
          )}
          {petNotice && (
            <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              {petNotice}
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium">종</span>
              <select
                className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2"
                value={species}
                onChange={(e) => {
                  setSpecies(e.target.value);
                  resetHabitat();
                }}
              >
                {(meta?.species ?? [{ key: "hamster", display_name: "햄스터", sizes: [] }]).map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium">마릿수</span>
              <input
                type="number"
                min={1}
                max={10}
                className="w-full rounded-lg border border-stone-300 px-3 py-2"
                value={count}
                onChange={(e) => {
                  setCount(Number(e.target.value));
                  resetHabitat();
                }}
              />
            </label>
          </div>

          <fieldset>
            <legend className="mb-2 text-sm font-medium">크기</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {(speciesOpt?.sizes ?? []).map((s) => (
                <label
                  key={s.key}
                  className={`cursor-pointer rounded-xl border p-4 ${
                    size === s.key ? "border-amber-500 bg-amber-50 ring-2 ring-amber-200" : "border-stone-300"
                  }`}
                >
                  <input
                    type="radio"
                    name="size"
                    value={s.key}
                    checked={size === s.key}
                    onChange={() => {
                      setSize(s.key);
                      resetHabitat();
                    }}
                    className="sr-only"
                  />
                  <span className="font-semibold">{s.display_name}</span>
                </label>
              ))}
            </div>
            {sizeOpt && count > sizeOpt.max_recommended_count && (
              <p className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">⚠️ {sizeOpt.count_warning_ko}</p>
            )}
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium">케이지 내부 치수 (mm)</legend>
            <div className="mb-3 flex flex-wrap gap-2">
              {CAGE_PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => {
                    setCage({ w: p.w, d: p.d, h: p.h });
                    resetHabitat();
                  }}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    cage.w === p.w && cage.d === p.d && cage.h === p.h
                      ? "border-amber-500 bg-amber-100"
                      : "border-stone-300 hover:bg-stone-50"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-3">
              {(
                [
                  ["w", "가로"],
                  ["d", "세로"],
                  ["h", "높이"],
                ] as const
              ).map(([k, label]) => (
                <label key={k} className="block">
                  <span className="mb-1 block text-xs text-stone-500">{label}</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    aria-label={`케이지 ${label} (mm)`}
                    className="w-full rounded-lg border border-stone-300 px-3 py-2"
                    value={cage[k]}
                    onChange={(e) => {
                      setCage({ ...cage, [k]: Number(e.target.value) });
                      resetHabitat();
                    }}
                  />
                </label>
              ))}
            </div>
            <p className="mt-2 text-xs text-stone-500">바닥재를 깐 상태의 내부 공간 기준으로 재 주세요.</p>
          </fieldset>

          {habitatErrors.length > 0 && (
            <ul className="space-y-1 text-sm text-red-700">
              {habitatErrors.map((e) => (
                <li key={e}>• {e}</li>
              ))}
            </ul>
          )}

          {quotaExhausted && <QuotaExhausted limit={quota.limit} />}

          <div className="flex justify-end">
            <button
              type="button"
              disabled={habitatErrors.length > 0 || !meta}
              onClick={() => setStep(2)}
              className="rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-stone-300"
            >
              다음
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section aria-labelledby="prompt-title" className="space-y-5">
          <h2 id="prompt-title" className="text-xl font-bold">
            어떤 구조물을 원하세요?
          </h2>
          <p className="break-words text-sm text-stone-600">
            {selectedPet && <span className="font-medium text-stone-800">{selectedPet.name} · </span>}
            {speciesOpt?.display_name} {sizeOpt?.display_name} · {count}마리 · 케이지 {cage.w}×{cage.d}×{cage.h}mm
          </p>
          <textarea
            aria-label="요구사항"
            rows={5}
            maxLength={2000}
            placeholder="예: 은신처와 터널을 한쪽에 몰아서 넣고 싶어요"
            className="w-full rounded-xl border border-stone-300 p-4 leading-relaxed"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPrompt(p)}
                className="rounded-full bg-stone-100 px-3 py-1 text-sm text-stone-700 hover:bg-stone-200"
              >
                {p}
              </button>
            ))}
          </div>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </p>
          )}
          {quotaExhausted && <QuotaExhausted limit={quota.limit} />}

          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setStep(1)}
              disabled={submitting}
              className="rounded-xl border border-stone-300 px-5 py-3 font-medium hover:bg-stone-50"
            >
              이전
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={submitting || quotaExhausted}
              className={`rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600 disabled:bg-amber-300 ${
                submitting ? "disabled:cursor-wait" : "disabled:cursor-not-allowed"
              }`}
            >
              {submitting ? "AI가 설계하고 있어요…" : "맞춤 설계 받기"}
            </button>
          </div>
          {quota && quota.remaining !== null && !submitting && (
            <p className={`text-right text-xs ${quotaExhausted ? "font-medium text-red-700" : "text-stone-500"}`}>
              최근 24시간 남은 설계 횟수: {quota.remaining}회
            </p>
          )}
          {submitting && (
            <p className="text-right text-xs text-stone-500">요구사항 해석 → 구조물 생성 → 안전 검증까지 최대 1분 정도 걸려요.</p>
          )}
        </section>
      )}
    </div>
  );
}
