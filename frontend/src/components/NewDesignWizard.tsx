"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, useTransition } from "react";

import AquariumPrintNotice from "@/components/AquariumPrintNotice";
import { useAuth } from "@/components/AuthProvider";
import { clearDraft, ReloginNotice, useDraftBackup } from "@/components/DraftRelogin";
import { EmailUnverifiedNotice, useEmailBlocked } from "@/components/EmailVerification";
import LoginRequired from "@/components/LoginRequired";
import { CAGE_LIMITS, cageDimError, presetsFor } from "@/components/me/common";
import { Link, useRouter, useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { api, ApiError, errorText, isAuthError, isEmailUnverified } from "@/lib/api";
import {
  capCount,
  countWarning,
  DEFAULT_MAX_COUNT,
  DIM_LABELS,
  dimInputLabel,
  floorShortfall,
  glassOf,
  kindOf,
  maxCountOf,
  speciesKind,
  TANK_PRESET_GLASS_MM,
  tankVolumeShortfall,
} from "@/lib/habitatKind";
import type { HabitatKind, Me, Pet, SpeciesResponse } from "@/lib/types";

// 구조물 하나를 요청하는 예시 (템플릿마다 하나)
const CAGE_EXAMPLE_PROMPTS: readonly string[] = [
  "출입구가 두 개 있는 은신처를 만들어 주세요",
  "케이지 한쪽에 놓을 긴 터널이 필요해요",
  "둥근 원통형 터널을 만들어 주세요",
  "완만한 경사로를 하나 만들어 주세요",
  "모래 목욕용 통을 하나 만들고 싶어요",
];

// 어항 예시는 고른 크기 구분에 맞춘다. 설계는 고른 크기 구분의 틈·구멍 기준을 따르므로, 예시에 다른 크기 구분의 동물이
// 나오면(새우 기준에 코리도라스 등) 그 동물이 끼는 크기로 설계되고도 검증을 통과한다. 그래서 크기 구분마다 그 구분에 드는
// 동물만 이름을 들고, 모르는 크기 구분이면 동물 이름이 없는 예시만 보인다. 어항은 동굴·터널만 만들 수 있다
const AQUARIUM_NEUTRAL_EXAMPLES: readonly string[] = [
  "앞뒤가 뚫린 동굴을 하나 만들어 주세요",
  "터널 하나와 동굴 하나를 만들어 주세요",
];
const AQUARIUM_EXAMPLE_PROMPTS = new Map<string, readonly string[]>([
  ["shrimp", ["새우가 숨을 수 있는 작은 동굴을 만들어 주세요", ...AQUARIUM_NEUTRAL_EXAMPLES]],
  ["nano_fish", ["네온 테트라 무리가 지나갈 터널과 동굴을 만들어 주세요", "앞뒤가 뚫린 동굴을 하나 만들어 주세요"]],
  ["small_fish", ["코리도라스용으로 앞뒤가 뚫린 동굴 두 개", "터널 하나와 동굴 하나를 만들어 주세요"]],
  ["community", ["새우와 작은 물고기가 함께 숨을 수 있는 동굴을 만들어 주세요", ...AQUARIUM_NEUTRAL_EXAMPLES]],
]);

/** 요구사항 단계의 예시 요청 (케이지는 템플릿마다 하나, 어항은 고른 크기 구분의 예시) */
function examplePromptsFor(kind: HabitatKind, size: string): readonly string[] {
  return kind === "aquarium" ? (AQUARIUM_EXAMPLE_PROMPTS.get(size) ?? AQUARIUM_NEUTRAL_EXAMPLES) : CAGE_EXAMPLE_PROMPTS;
}

/** 처음 열 때 고르는 종·크기. 주소로 받은 요청(?prompt=)에 종이 없으면 이 종의 요청으로 본다 */
const DEFAULT_SPECIES = "hamster";
const DEFAULT_SIZE = "syrian";

const COUNT_MIN = 1;

const LOGIN_MESSAGE = "로그인하면 설계를 만들 수 있어요";
const LOGIN_DESCRIPTION = "회원이 되면 설계 내역이 저장되고 커뮤니티에 공유할 수 있어요.";

type Step = 1 | 2;
type Quota = Me["design_quota"];
type Cage = { w: number; d: number; h: number };
/** 로그인이 풀린 동안 맡겨 두는 입력 (다시 로그인하고 돌아오면 되살린다) */
type WizardDraft = { species: string; size: string; count: number; cage: Cage; prompt: string; petId: string | null };

const DRAFT_KEY = "design:new";

/** 로그인 상태를 확인하는 동안(그리고 페이지의 Suspense 대기 중) 보여 주는 자리 */
export function WizardSkeleton() {
  const t = useT();
  return (
    <div className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm sm:p-8">
      <p role="status" className="py-10 text-center text-sm text-stone-500">
        {t("설계 화면을 준비하고 있어요…")}
      </p>
    </div>
  );
}

/** 사육 환경 입력 오류: 가로·세로·높이(어항은 물 깊이) 순서로 확인한 뒤 마릿수를 본다 (안내 순서도 같다) */
function habitatErrorsOf(cage: Cage, count: number, kind: HabitatKind, maxCount: number, t: TFunction): string[] {
  const errs: string[] = [];
  for (const [k, label] of DIM_LABELS[kind]) {
    // 안내 문구는 cageDimError 와 같은 원문을 번역해 보인다 (한국어는 그대로)
    if (cageDimError(k, cage[k], label))
      errs.push(t("{label}는 {lo}~{hi}mm 사이로 입력해 주세요.", { label: t(label), lo: CAGE_LIMITS[k][0], hi: CAGE_LIMITS[k][1] }));
  }
  if (!Number.isInteger(count) || count < COUNT_MIN || count > maxCount)
    errs.push(t("마릿수는 {min}~{max} 사이로 입력해 주세요.", { min: COUNT_MIN, max: maxCount }));
  return errs;
}

/** 최근 24시간 설계 횟수를 모두 쓴 경우의 안내 */
function QuotaExhausted({ limit }: { limit: number | null }) {
  const t = useT();
  return (
    <p role="status" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
      {limit !== null
        ? t("최근 24시간 동안 쓸 수 있는 설계 횟수({limit}회)를 모두 썼어요. 시간이 조금 지나면 다시 설계할 수 있어요.", {
            limit,
          })
        : t("최근 24시간 동안 쓸 수 있는 설계 횟수를 모두 썼어요. 시간이 조금 지나면 다시 설계할 수 있어요.")}
    </p>
  );
}

export default function NewDesignWizard() {
  const t = useT();
  const router = useRouter();
  // 링크·router.push 로 새로 들어올 때마다 바뀌고, 뒤로·앞으로 가기로 돌아오면 그대로인 값
  const { bfcacheId } = router;
  const { status, user, refresh, emailUnverified } = useAuth();
  const userId = user?.id ?? null;
  const searchParams = useSearchParams();
  // /design?pet={id}: 내 정보의 "이 아이로 설계하기"에서 들어온 경우 그 반려동물로 미리 채운다
  const wantedPet = searchParams.get("pet");
  // /design?prompt=...: 메인 화면 입력창에 적은 요청. 요구사항 칸에 미리 채운다
  const wantedPrompt = searchParams.get("prompt")?.trim().slice(0, 2000) || null;
  // /design?species=aquarium: 메인 화면의 예시처럼 종을 골라 두고 들어온 경우 (?pet= 이 있으면 반려동물이 정한다).
  // 종 없이 요청(?prompt=)만 받으면 기본 종의 요청으로 본다: 이 화면은 숨김 상태로 남아 있어, 그러지 않으면 전에 고른
  // 어항이 남아 햄스터 요청을 어항으로 설계한다 (새로 고침으로 열 때처럼 기본 종으로 연다)
  const wantedSpecies = searchParams.get("species") ?? (wantedPrompt && !wantedPet ? DEFAULT_SPECIES : null);
  // /design?species=aquarium&size=shrimp: 예시 문장에 나온 동물의 크기 구분까지 골라 두고 들어온 경우 (?species= 와 함께만 쓴다)
  const wantedSize = searchParams.get("size");
  const petSelectId = useId();
  const [meta, setMeta] = useState<SpeciesResponse | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>(1);

  const [species, setSpecies] = useState(DEFAULT_SPECIES);
  const [size, setSize] = useState(DEFAULT_SIZE);
  const [count, setCount] = useState(1);
  const [cage, setCage] = useState<Cage>({ w: 600, d: 400, h: 300 });
  const [prompt, setPrompt] = useState("");
  /** 메인 화면에서 적어 온 요청 (사육 환경 단계에서 보여 준다) */
  const [carriedPrompt, setCarriedPrompt] = useState<string | null>(null);

  const [habitatId, setHabitatId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 서버가 이메일 인증 전이라고 거절했다 (쓴 내용은 그대로 두고 안내한다) */
  const [emailBlocked, setEmailBlocked] = useEmailBlocked();

  const [pets, setPets] = useState<Pet[] | null>(null);
  /**
   * 값을 채워 온 반려동물. 크기·치수·마릿수를 고쳐도 그대로 두고, "직접 입력"을 고르거나 다른 종으로 바꾸면 지운다
   * (서버는 종이 다른 반려동물로 사육 환경을 만들지 않는다)
   */
  const [petId, setPetId] = useState<string | null>(null);
  const [petNotice, setPetNotice] = useState<string | null>(null);
  const [quota, setQuota] = useState<Quota | null>(null);
  // 주소의 ?pet= 은 들어올 때마다 한 번 적용한다. 이 화면은 숨김 상태로 남아 있으므로 bfcacheId 로 구분해,
  // "이 아이로 설계하기"로 다시 들어오면 최신 정보로 다시 채우고, 뒤로 가기로 돌아오면 고친 값을 덮어쓰지 않는다
  const appliedPetParam = useRef<string | null>(null);
  // 불러온 목록과 비교하기 위한 지금 고른 반려동물 (렌더 중에는 읽지 않는다)
  const petIdRef = useRef<string | null>(null);
  useEffect(() => {
    petIdRef.current = petId;
  }, [petId]);
  // 종을 바꿀 때 고른 반려동물의 종을 보려고 읽는 목록과, 주소의 ?species= 가 지금 종과 같은지 보려고 읽는 종 (렌더 중에는 읽지 않는다)
  const petsRef = useRef<Pet[] | null>(null);
  useEffect(() => {
    petsRef.current = pets;
  }, [pets]);
  const speciesRef = useRef(species);
  useEffect(() => {
    speciesRef.current = species;
  }, [species]);

  /**
   * 다른 종으로 바꿀 때: 고른 반려동물이 그 종이 아니면 연결을 끊고 알린다. 입력해 둔 값은 그대로 둔다.
   * (종이 다른 반려동물을 그대로 보내면 서버가 사육 환경을 만들지 않는다)
   */
  const unlinkPetOfOtherSpecies = useCallback(
    (nextSpecies: string) => {
      const id = petIdRef.current;
      if (!id || petsRef.current?.find((p) => p.id === id)?.species === nextSpecies) return;
      setPetId(null);
      setPetNotice(t("종을 바꿔서 반려동물 연결을 해제했어요. 아래 값을 확인해 주세요."));
    },
    [t],
  );

  // 설계를 만든 뒤 결과 화면으로 이동하는 동안 true. router.push 를 이 transition 안에서 부르므로
  // 이동이 끝나면 저절로 false 가 된다 (다른 이동에 밀려 이 화면에 그대로 남는 경우도)
  const [opening, startOpening] = useTransition();
  // 설계 요청이 두 번 나가지 않게 막는다 (버튼 상태보다 먼저 바뀐다). 결과 화면으로의 이동까지 끝나면 푼다
  const submittingRef = useRef(false);
  useEffect(() => {
    if (!submitting && !opening) submittingRef.current = false;
  }, [submitting, opening]);

  // 로그인이 풀려도 쓰던 요구사항은 지운 것처럼 보이지 않게 폼을 두고, 다시 로그인하고 돌아오면 되살린다
  // 주소(?prompt=)로 받아 온 그대로인 요청은 "쓰던 내용"으로 보지 않는다: 로그인 전이면 보통 로그인 안내를 보여 주고,
  // 로그인 후 같은 주소로 돌아오면 다시 채운다
  const dirty = prompt.trim() !== "" && prompt.trim() !== carriedPrompt;
  const needsLogin = status !== null && (!user || authError !== null);
  useDraftBackup<WizardDraft>(
    DRAFT_KEY,
    dirty ? { species, size, count, cage, prompt, petId } : null,
    needsLogin,
    (d) => {
      setSpecies(d.species);
      setSize(d.size);
      setCount(d.count);
      setCage(d.cage);
      setPrompt(d.prompt);
      // 종이 다른 반려동물은 다시 연결하지 않는다 (서버가 받지 않는다. 목록을 아직 못 받았으면 설계할 때 한 번 더 거른다)
      const pet = d.petId ? petsRef.current?.find((p) => p.id === d.petId) : undefined;
      setPetId(pet && pet.species !== d.species ? null : d.petId);
      setHabitatId(null);
      setStep(2);
    },
  );

  // 주소의 ?prompt= 은 들어올 때마다 한 번 적용한다 (?pet= 과 같이 bfcacheId 로 구분: 뒤로 가기로 돌아오면 고친 요구사항을 덮지 않는다).
  // 사육 환경을 먼저 확인해야 하므로 1단계에 머문다
  const appliedPromptParam = useRef<string | null>(null);
  useEffect(() => {
    if (!wantedPrompt) return;
    const key = `${bfcacheId}|${wantedPrompt}`;
    if (appliedPromptParam.current === key) return;
    appliedPromptParam.current = key;
    setPrompt(wantedPrompt);
    setCarriedPrompt(wantedPrompt);
    setStep(1);
  }, [wantedPrompt, bfcacheId]);

  // 종 목록은 누구나 볼 수 있다
  useEffect(() => {
    let alive = true;
    api
      .species()
      .then((m) => alive && setMeta(m))
      .catch((e: unknown) => {
        if (!alive) return;
        if (isAuthError(e)) setAuthError(e);
        else setMetaError(errorText(e, t("정보를 불러오지 못했어요.")));
      });
    return () => {
      alive = false;
    };
  }, [t]);

  // 주소의 ?species=(와 ?size=)는 종 목록을 받은 뒤 들어올 때마다 한 번 적용한다 (?prompt= 과 같이 bfcacheId 로 구분).
  // 목록에 없는 종·크기는 무시한다. 이미 그 종이면 고른 크기·마릿수·반려동물을 그대로 둔다 (?size= 가 있으면 크기만 바꾼다).
  // 다른 종이면 종 고르기와 같이 크기는 ?size= 또는 그 종의 첫 크기, 마릿수는 그 종의 상한 안으로 바꾸고,
  // 그 종이 아닌 반려동물은 연결을 끊는다
  const appliedSpeciesParam = useRef<string | null>(null);
  useEffect(() => {
    const next = wantedSpecies && !wantedPet ? meta?.species.find((s) => s.key === wantedSpecies) : undefined;
    if (!next) return;
    const key = `${bfcacheId}|${next.key}|${wantedSize ?? ""}`;
    if (appliedSpeciesParam.current === key) return;
    appliedSpeciesParam.current = key;
    const nextSize = next.sizes.find((s) => s.key === wantedSize)?.key;
    const sameSpecies = speciesRef.current === next.key;
    if (sameSpecies && !nextSize) return;
    setSize(nextSize ?? next.sizes[0]?.key ?? "");
    setHabitatId(null);
    if (sameSpecies) return;
    setSpecies(next.key);
    setCount((c) => capCount(c, maxCountOf(next)));
    unlinkPetOfOtherSpecies(next.key);
  }, [wantedSpecies, wantedSize, wantedPet, meta, bfcacheId, unlinkPetOfOtherSpecies]);

  // 반려동물을 고를 때 마릿수를 그 종의 상한 안으로 줄이려고 종 목록을 읽는다 (렌더 중에는 읽지 않는다)
  const metaRef = useRef<SpeciesResponse | null>(null);
  useEffect(() => {
    metaRef.current = meta;
  }, [meta]);

  const applyPet = useCallback((p: Pet) => {
    setPetId(p.id);
    setPetNotice(null);
    setSpecies(p.species);
    setSize(p.size);
    const known = metaRef.current;
    if (known) setCount((c) => capCount(c, maxCountOf(known.species.find((s) => s.key === p.species))));
    if (p.cage) setCage({ w: p.cage.width_mm, d: p.cage.depth_mm, h: p.cage.height_mm });
    setHabitatId(null);
  }, []);

  // 로그인한 경우: 내 반려동물(미리 채우기)과 남은 설계 횟수 (화면이 다시 보일 때마다 새로 불러온다)
  useEffect(() => {
    if (!userId) return;
    let alive = true;
    const petKey = wantedPet ? `${bfcacheId}|${wantedPet}` : null;
    api
      .pets()
      .then((list) => {
        if (!alive) return;
        setPets(list);
        if (petKey && appliedPetParam.current !== petKey) {
          appliedPetParam.current = petKey;
          const p = list.find((x) => x.id === wantedPet);
          setStep(1); // 채운 사육 환경부터 확인하게 한다
          setError(null);
          if (p) applyPet(p);
          else {
            setPetId(null);
            setHabitatId(null);
            setPetNotice(t("선택한 반려동물 정보를 찾지 못했어요. 직접 입력해 주세요."));
          }
        } else if (petIdRef.current && !list.some((x) => x.id === petIdRef.current)) {
          // 골라 둔 반려동물이 그사이 삭제됐다: 연결만 끊고 입력해 둔 값은 그대로 둔다
          setPetId(null);
          setHabitatId(null);
          setPetNotice(t("골라 둔 반려동물 정보가 없어져서 연결을 해제했어요. 아래 값을 확인해 주세요."));
        }
      })
      .catch((e: unknown) => {
        if (alive && isAuthError(e)) setAuthError(e); // 세션이 만료된 경우
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
  }, [userId, wantedPet, bfcacheId, applyPet, t]);

  const speciesOpt = meta?.species.find((s) => s.key === species);
  const sizeOpt = speciesOpt?.sizes.find((s) => s.key === size);
  const selectedPet = pets?.find((p) => p.id === petId) ?? null;
  const quotaExhausted = quota?.remaining === 0;
  /** 사육 환경 종류: 케이지면 예전 화면 그대로, 어항이면 수조·물 깊이 낱말과 수조 프리셋 */
  const kind = speciesKind(meta?.species, species);
  const aquarium = kind === "aquarium";
  const dims = DIM_LABELS[kind];
  const maxCount = speciesOpt?.max_count ?? DEFAULT_MAX_COUNT;
  const countNote = countWarning(sizeOpt, count);
  const volumeShort = tankVolumeShortfall({ width_mm: cage.w, depth_mm: cage.d, height_mm: cage.h }, sizeOpt, count);
  // 바닥 최소 기준 (서버 check_enclosure 와 같다. 어항은 안쪽 치수에 유리 두께를 더한 겉 크기로 비교)
  const floorShort = floorShortfall({ width_mm: cage.w, depth_mm: cage.d }, sizeOpt);

  const habitatErrors = habitatErrorsOf(cage, count, kind, maxCount, t);
  // 종 목록을 받았는데 고른 크기가 그 종에 없으면(반려동물·임시 저장에서 채운 옛 값 등) 크기를 다시 고르게 한다
  const sizeMissing = !!meta && !sizeOpt;

  // 사육 환경이 바뀌면 이전에 등록한 환경을 다시 쓰지 않는다
  const resetHabitat = () => setHabitatId(null);

  async function submit() {
    if (submittingRef.current || opening) return; // 이미 설계 중이거나 결과 화면으로 이동 중
    setError(null);
    if (!prompt.trim()) {
      setError(t("원하는 구조물이나 배치를 적어 주세요."));
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setAuthError(null); // 다른 탭에서 다시 로그인했을 수 있다 (또 실패하면 다시 안내한다)
    setEmailBlocked(false);
    try {
      let hid = habitatId;
      if (!hid) {
        const h = await api.createHabitat({
          species,
          size,
          count,
          cage: { width_mm: cage.w, depth_mm: cage.d, height_mm: cage.h },
          // 종이 다른 반려동물은 서버가 받지 않는다. 종을 바꿀 때 연결을 끊지만, 임시 저장에서 되살린 값 등도 한 번 더 거른다
          pet_id: selectedPet && selectedPet.species !== species ? null : petId,
        });
        hid = h.id;
        setHabitatId(hid);
      }
      const design = await api.createDesign(hid, prompt.trim());
      clearDraft(DRAFT_KEY);
      if (!user) void refresh(); // 다른 탭에서 다시 로그인한 경우: 헤더 등도 로그인 상태로 바꾼다
      // 결과 화면이 뜰 때까지는 opening 이 버튼을 막는다 (이동하는 동안 다시 눌러 같은 설계를 또 만들지 않게).
      // submitting 도 이동과 함께 풀리도록 같은 transition 안에서 바꾼다
      startOpening(() => {
        setSubmitting(false);
        router.push(`/designs/${design.id}`);
      });
    } catch (e) {
      if (isAuthError(e)) setAuthError(e); // 사용 중 세션이 만료된 경우
      else if (isEmailUnverified(e)) setEmailBlocked(true); // 위쪽 안내로 알려 준다 (로그인 상태도 다시 확인한다)
      else if (e instanceof ApiError && e.code === "design_quota_exceeded" && quota && quota.limit !== null)
        setQuota({ ...quota, used: Math.max(quota.used, quota.limit), remaining: 0 }); // 아래 안내로 알려 준다
      else if (e instanceof ApiError && e.code === "pet_species_mismatch") {
        // 고른 반려동물의 종이 그사이 바뀌었다(다른 탭에서 고친 경우 등): 연결을 끊어 다시 누르면 설계되게 한다
        setPetId(null);
        setError(t("고른 반려동물과 종이 달라서 반려동물 연결을 해제했어요. 다시 누르면 반려동물 연결 없이 설계해요."));
      } else {
        setError(errorText(e, t("설계 중 문제가 생겼어요. 다시 시도해 주세요.")));
        // 실패한 요청도 횟수에 들어가므로 남은 횟수를 다시 불러온다
        api
          .me()
          .then((m) => setQuota(m.design_quota))
          .catch(() => {
            /* 표시만 건너뛴다 */
          });
      }
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  // 쓰던 요구사항이 있으면 로그인이 풀려도 폼을 바꾸지 않는다 (위쪽 안내로 다시 로그인하게 한다)
  if (authError && !dirty) {
    return (
      <LoginRequired
        unavailable={authError.code === "auth_unavailable"}
        message={LOGIN_MESSAGE}
        description={LOGIN_DESCRIPTION}
      />
    );
  }
  if (!status) return <WizardSkeleton />;
  if (!user && !dirty) return <LoginRequired message={LOGIN_MESSAGE} description={LOGIN_DESCRIPTION} />;

  return (
    <div className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm sm:p-8">
      {needsLogin && (
        <div className="mb-4">
          <ReloginNotice next="/design" />
        </div>
      )}
      {!needsLogin && (emailUnverified || emailBlocked) && (
        <div className="mb-4">
          <EmailUnverifiedNotice action="맞춤 설계를 받을" />
        </div>
      )}
      <ol className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm" aria-label={t("진행 단계")}>
        {(["사육 환경", "요구사항"] as const).map((label, i) => {
          const n = (i + 1) as Step;
          const active = step === n;
          return (
            <li key={label} className="flex items-center gap-2 whitespace-nowrap">
              <span
                className={`grid h-7 w-7 place-items-center rounded-full font-semibold ${
                  active ? "bg-amber-500 text-white" : step > n ? "bg-amber-200 text-amber-900" : "bg-stone-200 text-stone-500"
                }`}
              >
                {n}
              </span>
              <span className={active ? "font-semibold" : "text-stone-500"}>{t(label)}</span>
              {i === 0 && <span className="mx-1 h-px w-8 bg-stone-300" aria-hidden />}
            </li>
          );
        })}
        {meta?.llm_provider === "mock" && (
          <li className="ml-auto whitespace-nowrap rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-800">
            {t("개발용 모의 해석기")}
          </li>
        )}
      </ol>

      {metaError && <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{metaError}</p>}
      {meta && !meta.storage_persistent && (
        <p role="status" className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          {t(
            "지금은 임시 저장소로 운영 중이에요. 만든 설계가 잠시 뒤 사라지거나 다시 열리지 않을 수 있으니, 필요한 파일은 바로 내려받아 주세요.",
          )}
        </p>
      )}

      {step === 1 && (
        <section aria-labelledby="habitat-title" className="space-y-6">
          <h2 id="habitat-title" className="text-xl font-bold">
            {t("사육 환경을 알려 주세요")}
          </h2>

          {carriedPrompt && prompt.trim() === carriedPrompt && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-sm">
              <p className="font-medium text-stone-800">{t("적어 주신 요청")}</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-stone-700">{carriedPrompt}</p>
              <p className="mt-2 text-xs text-stone-500">
                {aquarium
                  ? t("수조 정보를 확인하고 다음을 누르면 이 요청으로 설계해요. 다음 단계에서 고칠 수 있어요.")
                  : t("케이지 정보를 확인하고 다음을 누르면 이 요청으로 설계해요. 다음 단계에서 고칠 수 있어요.")}
              </p>
            </div>
          )}

          {pets && pets.length > 0 && (
            <div className="rounded-xl bg-amber-50 p-4">
              <label htmlFor={petSelectId} className="mb-1 block text-sm font-medium">
                {t("내 반려동물")}
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
                <option value="">{t("직접 입력")}</option>
                {pets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {`${p.name} · ${p.size_name_ko}`}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-stone-600">
                {selectedPet && !selectedPet.cage
                  ? kindOf(selectedPet, meta?.species) === "aquarium"
                    ? t("등록된 수조 치수가 없어서 종·크기만 채웠어요. 아래 치수를 확인해 주세요.")
                    : t("등록된 케이지 치수가 없어서 종·크기만 채웠어요. 아래 치수를 확인해 주세요.")
                  : t("고르면 종·크기와 케이지 치수가 채워져요. 채운 뒤에도 고칠 수 있어요.")}
              </p>
            </div>
          )}
          {pets && pets.length === 0 && (
            <p className="text-sm">
              <Link href="/me#pets" className="text-amber-700 underline-offset-2 hover:underline">
                {t("내 정보에서 반려동물을 등록하면 다음부터 자동으로 채워져요")}
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
              <span className="mb-1 block text-sm font-medium">{t("종")}</span>
              <select
                className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2"
                value={species}
                onChange={(e) => {
                  // 크기는 새 종의 첫 크기로, 마릿수는 새 종의 상한 안으로 (이전 종의 크기가 남아 있지 않게).
                  // 고른 반려동물이 새 종이 아니면 연결을 끊는다
                  const next = meta?.species.find((s) => s.key === e.target.value);
                  setSpecies(e.target.value);
                  setSize(next?.sizes[0]?.key ?? "");
                  if (next) setCount((c) => capCount(c, maxCountOf(next)));
                  resetHabitat();
                  unlinkPetOfOtherSpecies(e.target.value);
                }}
              >
                {(meta?.species ?? [{ key: "hamster", display_name: t("햄스터"), sizes: [] }]).map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium">{t("마릿수")}</span>
              <input
                type="number"
                min={COUNT_MIN}
                max={maxCount}
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
            <legend className="mb-2 text-sm font-medium">{t("크기")}</legend>
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
            {/* 크기 구분을 고르는 기준 (어항: 몸길이 재는 법·아주 작은 종). 서버가 화면 언어로 보낸다 */}
            {speciesOpt?.size_hint_ko && (
              <p data-testid="size-hint" className="mt-2 text-xs text-stone-500">
                {speciesOpt.size_hint_ko}
              </p>
            )}
            {countNote && <p className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{countNote}</p>}
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium">
              {aquarium ? t("수조 크기와 물 깊이 (mm)") : t("케이지 내부 치수 (mm)")}
            </legend>
            <div className="mb-3 flex flex-wrap gap-2">
              {presetsFor(kind).map((p) => (
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
                  {t(p.label)}
                </button>
              ))}
            </div>
            {aquarium && (
              <p className="mb-3 text-xs text-stone-500">
                {t(
                  "수조 버튼 이름은 흔한 수조의 겉 크기예요. 누르면 유리 두께 {g}mm를 빼서 안쪽 가로·세로를 채우고, 물 깊이는 수조 높이에서 바닥 유리와 바닥재 약 5cm, 수면 위 여유 약 3cm를 뺀 값으로 채워요. 내 수조와 다르면 고쳐 주세요.",
                  { g: TANK_PRESET_GLASS_MM },
                )}
              </p>
            )}
            <div className="grid grid-cols-3 gap-3">
              {dims.map(([k, label]) => (
                <label key={k} className="block">
                  <span className="mb-1 block text-xs text-stone-500">{t(label)}</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    aria-label={dimInputLabel(kind, k, t)}
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
            <p className="mt-2 text-xs text-stone-500">
              {aquarium
                ? t("가로·세로는 수조 안쪽 치수(유리 안쪽 사이)로, 물 깊이는 바닥재 위부터 수면까지 재 주세요. 바닥·부피 기준은 유리 두께를 더한 겉 크기로 비교해요.")
                : t("바닥재를 깐 상태의 내부 공간 기준으로 재 주세요.")}
            </p>
            {floorShort && (
              <p className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                {aquarium
                  ? t(
                      "수조 바닥 최소 기준은 겉 크기 {w}×{d}cm예요. 입력한 안쪽 치수에 유리 두께 {g}mm를 더하면 약 {ow}×{od}mm라 모자라요. 설계는 할 수 있지만 더 큰 수조를 권장해요.",
                      {
                        w: floorShort.minMm[0] / 10,
                        d: floorShort.minMm[1] / 10,
                        g: floorShort.glassMm,
                        ow: floorShort.floorMm[0],
                        od: floorShort.floorMm[1],
                      },
                    )
                  : t("사육장 바닥 최소 기준은 {w}×{d}cm예요. 설계는 할 수 있지만 더 넓은 사육장을 권장해요.", {
                      w: floorShort.minMm[0] / 10,
                      d: floorShort.minMm[1] / 10,
                    })}
              </p>
            )}
            {volumeShort && (
              <p className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                {volumeShort.byCount
                  ? t(
                      "수조 부피가 약 {v}L(안쪽 치수에 유리 두께 {g}mm, 물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더한 겉 크기로 어림)로 {count}마리 기준 권장 최소 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.",
                      {
                        v: Math.floor(volumeShort.volumeL), // 내림: 반올림하면 '약 54L … 최소 54L보다 작아요'처럼 보일 수 있다
                        g: glassOf(volumeShort.aquatic),
                        s: volumeShort.aquatic.substrate_depth_assumed_mm,
                        a: volumeShort.aquatic.air_gap_mm,
                        count,
                        need: Math.round(volumeShort.needL * 10) / 10,
                      },
                    )
                  : t(
                      "수조 부피가 약 {v}L(안쪽 치수에 유리 두께 {g}mm, 물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더한 겉 크기로 어림)로 최소 기준 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.",
                      {
                        v: Math.floor(volumeShort.volumeL),
                        g: glassOf(volumeShort.aquatic),
                        s: volumeShort.aquatic.substrate_depth_assumed_mm,
                        a: volumeShort.aquatic.air_gap_mm,
                        need: Math.round(volumeShort.needL * 10) / 10,
                      },
                    )}
              </p>
            )}
          </fieldset>

          {aquarium && <AquariumPrintNotice notes={speciesOpt?.print_notes_ko ?? []} />}

          {(habitatErrors.length > 0 || sizeMissing) && (
            <ul className="space-y-1 text-sm text-red-700">
              {sizeMissing && <li>• {t("크기를 골라 주세요.")}</li>}
              {habitatErrors.map((e) => (
                <li key={e}>• {e}</li>
              ))}
            </ul>
          )}

          {quotaExhausted && <QuotaExhausted limit={quota.limit} />}

          <div className="flex justify-end">
            <button
              type="button"
              disabled={habitatErrors.length > 0 || !meta || !sizeOpt}
              onClick={() => setStep(2)}
              className="rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-stone-300"
            >
              {t("다음")}
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section aria-labelledby="prompt-title" className="space-y-5">
          <h2 id="prompt-title" className="text-xl font-bold">
            {t("원하는 구조물을 적어 주세요")}
          </h2>
          <p className="break-words text-sm text-stone-600">
            {selectedPet && <span className="font-medium text-stone-800">{selectedPet.name} · </span>}
            {aquarium
              ? t("{species} {size} · {count}마리 · 수조 {w}×{d}mm · 물 깊이 {h}mm", {
                  species: speciesOpt?.display_name ?? "",
                  size: sizeOpt?.display_name ?? "",
                  count,
                  w: cage.w,
                  d: cage.d,
                  h: cage.h,
                })
              : t("{species} {size} · {count}마리 · 케이지 {w}×{d}×{h}mm", {
                  species: speciesOpt?.display_name ?? "",
                  size: sizeOpt?.display_name ?? "",
                  count,
                  w: cage.w,
                  d: cage.d,
                  h: cage.h,
                })}
          </p>
          <textarea
            aria-label={t("요구사항")}
            rows={5}
            maxLength={2000}
            placeholder={aquarium ? t("예: 새우가 숨을 수 있는 작은 동굴을 만들어 주세요") : t("예: 환기구가 있는 은신처를 만들어 주세요")}
            className="w-full rounded-xl border border-stone-300 p-4 leading-relaxed"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {examplePromptsFor(kind, size).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPrompt(t(p))}
                className="rounded-full bg-stone-100 px-3 py-1 text-sm text-stone-700 hover:bg-stone-200"
              >
                {t(p)}
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
              disabled={submitting || opening}
              className="rounded-xl border border-stone-300 px-5 py-3 font-medium hover:bg-stone-50"
            >
              {t("이전")}
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={submitting || opening || quotaExhausted || emailUnverified}
              className={`rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600 disabled:bg-amber-300 ${
                submitting || opening ? "disabled:cursor-wait" : "disabled:cursor-not-allowed"
              }`}
            >
              {opening ? t("결과 화면을 여는 중…") : submitting ? t("설계하는 중…") : t("맞춤 설계 받기")}
            </button>
          </div>
          {quota && quota.remaining !== null && !submitting && !opening && (
            <p className={`text-right text-xs ${quotaExhausted ? "font-medium text-red-700" : "text-stone-500"}`}>
              {t("최근 24시간 남은 설계 횟수: {n}회 · 실패한 요청도 횟수에 포함돼요.", { n: quota.remaining })}
            </p>
          )}
          {submitting && !opening && (
            <p className="text-right text-xs text-stone-500">
              {t("요구사항 해석 → 구조물 생성 → 안전 검증까지 최대 1분 정도 걸려요.")}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
