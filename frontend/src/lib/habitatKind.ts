// 사육 환경 종류(케이지·어항)를 알아내고, 종류에 따라 달라지는 낱말·프리셋·어림 계산을 모아 둔다.
// 케이지 문구는 원래 문구 그대로다 (햄스터 화면은 바뀌지 않는다).
// 어항이면 높이 칸에 물 깊이(바닥재 위~수면)를 받는다. 서버도 사육 환경의 height_mm 을 물 깊이로 본다.

import type { TFunction } from "@/i18n/translate";
import type { AquaticRules, Cage, HabitatKind, SizeOption, SpeciesOption } from "@/lib/types";

/** 종 목록에서 찾은 종의 사육 환경. 목록에 없는 종이나 habitat 이 없는 옛 서버 응답은 케이지 */
export function speciesKind(species: readonly SpeciesOption[] | null | undefined, key: string): HabitatKind {
  return species?.find((s) => s.key === key)?.habitat ?? "cage";
}

/**
 * 서버가 보낸 사육 환경·반려동물·배치안의 종류.
 * habitat_kind 를 먼저 보고, 없으면(옛 서버 응답) 종 목록에서, 그래도 모르면 케이지
 */
export function kindOf(
  x: { habitat_kind?: HabitatKind | null; species?: string } | null | undefined,
  species?: readonly SpeciesOption[] | null,
): HabitatKind {
  if (!x) return "cage";
  if (x.habitat_kind === "cage" || x.habitat_kind === "aquarium") return x.habitat_kind;
  return x.species ? speciesKind(species, x.species) : "cage";
}

/** 케이지에서 키우는 종인지 (가상 케이지는 이런 종만 쓴다) */
export const isCageSpecies = (s: SpeciesOption) => (s.habitat ?? "cage") === "cage";

/** 마릿수 입력 상한 (옛 서버 응답에 max_count 가 없으면 예전 상한 10) */
export const DEFAULT_MAX_COUNT = 10;
export const maxCountOf = (s: SpeciesOption | null | undefined) => s?.max_count ?? DEFAULT_MAX_COUNT;

/** 종을 바꿀 때 마릿수가 새 종의 상한을 넘으면 상한으로 줄인다 (그 밖의 입력은 그대로 두고 입력 확인이 알린다) */
export const capCount = (n: number, max: number) => (n > max ? max : n);

/** 가상 케이지에 쓸 기본 종·크기: 햄스터 골든이 있으면 그것, 없으면 첫 케이지 종의 첫 크기 */
export function fallbackCageSpecies(species: readonly SpeciesOption[] | null | undefined): { species: string; size: string } {
  const cage = (species ?? []).filter(isCageSpecies);
  const hamster = cage.find((s) => s.key === "hamster");
  if (hamster?.sizes.some((z) => z.key === "syrian")) return { species: "hamster", size: "syrian" };
  const first = cage.find((s) => s.sizes.length > 0);
  return first ? { species: first.key, size: first.sizes[0].key } : { species: "hamster", size: "syrian" };
}

export type DimKey = "w" | "d" | "h";

/** 치수 칸의 짧은 이름 (한국어 원문. 보여 줄 때 t() 로 번역한다) */
export const DIM_LABELS: Record<HabitatKind, readonly (readonly [DimKey, string])[]> = {
  cage: [
    ["w", "가로"],
    ["d", "세로"],
    ["h", "높이"],
  ],
  aquarium: [
    ["w", "가로"],
    ["d", "세로"],
    ["h", "물 깊이"],
  ],
};

/** 치수 입력 칸의 이름 (설계하기 화면). 케이지는 "케이지 가로 (mm)", 어항은 "수조 가로 (mm)"·"물 깊이 (mm)" */
export function dimInputLabel(kind: HabitatKind, k: DimKey, t: TFunction): string {
  if (kind === "aquarium") return k === "w" ? t("수조 가로 (mm)") : k === "d" ? t("수조 세로 (mm)") : t("물 깊이 (mm)");
  return t("케이지 {label} (mm)", { label: t(k === "w" ? "가로" : k === "d" ? "세로" : "높이") });
}

/** 카드·요약 한 줄: "케이지 600×400×300mm" / "수조 600×300mm · 물 깊이 280mm" */
export function enclosureSummary(kind: HabitatKind, c: Cage, t: TFunction): string {
  const v = { w: c.width_mm, d: c.depth_mm, h: c.height_mm };
  return kind === "aquarium" ? t("수조 {w}×{d}mm · 물 깊이 {h}mm", v) : t("케이지 {w}×{d}×{h}mm", v);
}

/**
 * 어항 수조 프리셋. 이름은 흔히 파는 수조의 겉 크기(가로×세로×높이)이고,
 * 물 깊이는 수조 높이에서 바닥재 약 5cm·수면 위 여유 약 3cm 를 뺀 값이다.
 * 이름이 숫자뿐인 것도 t() 로 보이므로 영어 사전에 같은 값을 둔다.
 */
export const TANK_PRESETS = [
  { label: "30큐브 30×30×30cm", w: 300, d: 300, h: 220 },
  { label: "45×30×30cm", w: 450, d: 300, h: 220 },
  { label: "60×30×36cm", w: 600, d: 300, h: 280 },
  { label: "60×45×45cm", w: 600, d: 450, h: 370 },
  { label: "90×45×45cm", w: 900, d: 450, h: 370 },
] as const;

/** 수조 부피 어림 L: 가로 × 세로 × (물 깊이 + 바닥재 어림 두께 + 수면 위 여유). 서버 checks.tank_volume_l 과 같은 식 */
export function tankVolumeL(c: Cage, a: AquaticRules): number {
  return (c.width_mm * c.depth_mm * (c.height_mm + a.substrate_depth_assumed_mm + a.air_gap_mm)) / 1e6;
}

export type TankVolumeShortfall = {
  /** 어림한 수조 부피 L */
  volumeL: number;
  /** 권장 최소 부피 L */
  needL: number;
  /** 마릿수 기준(마리당 부피 × 마릿수)이 최소 부피보다 커서 그 값을 쓴 경우 */
  byCount: boolean;
  aquatic: AquaticRules;
};

/** 수조가 권장 부피보다 작으면 그 내용, 아니면(또는 어항이 아니면) null. 서버 check_tank_volume 과 같은 기준 */
export function tankVolumeShortfall(c: Cage, size: SizeOption | null | undefined, count: number): TankVolumeShortfall | null {
  const a = size?.aquatic;
  if (!a) return null;
  const volumeL = tankVolumeL(c, a);
  const perCount = a.volume_l_per_animal != null ? count * a.volume_l_per_animal : null;
  const byCount = perCount !== null && perCount > a.min_volume_l;
  const needL = byCount ? perCount : a.min_volume_l;
  return volumeL < needL - 1e-9 ? { volumeL, needL, byCount, aquatic: a } : null;
}

/** 권장 마릿수를 벗어날 때의 경고 (서버가 보낸 문구, 화면 언어로 와 있다). 서버 check_count 처럼 최대를 먼저 본다 */
export function countWarning(size: SizeOption | null | undefined, count: number): string | null {
  if (!size) return null;
  if (size.max_recommended_count != null && count > size.max_recommended_count) return size.count_warning_ko;
  if (size.min_recommended_count != null && count < size.min_recommended_count) return size.min_count_warning_ko ?? null;
  return null;
}

/** 어항용 3D 출력 안전 근거를 정리한 커뮤니티 글 (「어항에 3D 출력물, 수질 면에서 써도 될까요」) */
export const AQUARIUM_PRINT_POST_ID = "4f64bf7ac33d43e89d5d034a93ca2760";
export const AQUARIUM_PRINT_POST_HREF = `/community/${AQUARIUM_PRINT_POST_ID}`;
