// 사육 환경 종류(케이지·어항)를 알아내고, 종류에 따라 달라지는 낱말·프리셋·어림 계산을 모아 둔다.
// 케이지 문구는 원래 문구 그대로다 (햄스터 화면은 바뀌지 않는다).
// 어항이면 높이 칸에 물 깊이(바닥재 위~수면)를 받는다. 서버도 사육 환경의 height_mm 을 물 깊이로 본다.
// 어항 가로·세로는 수조 안쪽 치수다 (배치·틈 검사가 안쪽 벽 기준). 바닥·부피 기준만 겉 크기라 비교할 때 유리 두께를 더한다.

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
 * 수조 버튼이 겉 크기에서 안쪽 치수·물 깊이를 어림할 때 쓰는 값 mm.
 * species.yaml 어항 aquatic 의 유리 두께(glass_thickness_assumed_mm)·윗여유(air_gap_mm), 물고기 구분 바닥재 두께와 같다.
 */
export const TANK_PRESET_GLASS_MM = 6;
const TANK_PRESET_SUBSTRATE_MM = 50;
const TANK_PRESET_AIR_GAP_MM = 30;

/** 겉 크기 W×D×H mm 수조의 안쪽 가로·세로(유리 2장을 뺀다)와 물 깊이(바닥 유리·바닥재·수면 위 여유를 뺀다) */
const tankPreset = (label: string, w: number, d: number, h: number) => ({
  label,
  w: w - 2 * TANK_PRESET_GLASS_MM,
  d: d - 2 * TANK_PRESET_GLASS_MM,
  h: h - TANK_PRESET_GLASS_MM - TANK_PRESET_SUBSTRATE_MM - TANK_PRESET_AIR_GAP_MM,
});

/**
 * 어항 수조 프리셋. 이름은 흔히 파는 수조의 겉 크기(가로×세로×높이)이고, 값은 입력 칸이 받는 안쪽 치수와 물 깊이다
 * (예: 60×30×36cm → 588×288mm, 물 깊이 274mm). 서버는 이 값에 유리 두께를 다시 더해 겉 크기 기준(바닥·부피)과 비교한다.
 * 이름이 숫자뿐인 것도 t() 로 보이므로 영어 사전에 같은 값을 둔다.
 */
export const TANK_PRESETS = [
  tankPreset("30큐브 30×30×30cm", 300, 300, 300),
  tankPreset("45×30×30cm", 450, 300, 300),
  tankPreset("60×30×36cm", 600, 300, 360),
  tankPreset("60×45×45cm", 600, 450, 450),
  tankPreset("90×45×45cm", 900, 450, 450),
] as const;

/** 유리 두께 어림 mm (옛 서버 응답에 없으면 0: 입력값 그대로 비교) */
export const glassOf = (a: AquaticRules) => a.glass_thickness_assumed_mm ?? 0;

/** 수조 겉 가로·세로 어림 mm = 안쪽 치수 + 유리 2장. 서버 checks.tank_outer_floor_mm 과 같은 식 */
export function tankOuterFloorMm(c: Pick<Cage, "width_mm" | "depth_mm">, a: AquaticRules): [number, number] {
  const g = glassOf(a);
  return [c.width_mm + 2 * g, c.depth_mm + 2 * g];
}

/**
 * 수조 부피 어림 L (겉 크기 기준): 겉 가로 × 겉 세로 × (물 깊이 + 바닥재 어림 두께 + 수면 위 여유 + 바닥 유리).
 * 서버 checks.tank_volume_l 과 같은 식 (54L 같은 표준 부피는 겉 치수로 계산한 총부피다)
 */
export function tankVolumeL(c: Cage, a: AquaticRules): number {
  const [w, d] = tankOuterFloorMm(c, a);
  return (w * d * (c.height_mm + a.substrate_depth_assumed_mm + a.air_gap_mm + glassOf(a))) / 1e6;
}

export type FloorShortfall = {
  /** 비교한 바닥 [가로, 세로] mm (어항은 유리 두께를 더한 겉 크기, 케이지는 입력값) */
  floorMm: [number, number];
  /** 최소 기준 [긴 변, 짧은 변] mm */
  minMm: [number, number];
  /** 더한 유리 두께 mm (케이지는 0) */
  glassMm: number;
};

/** 바닥이 최소 기준보다 작으면 그 내용, 아니면(또는 기준이 없으면) null. 긴 변·짧은 변끼리 비교 (서버 check_enclosure 와 같다) */
export function floorShortfall(c: Pick<Cage, "width_mm" | "depth_mm">, size: SizeOption | null | undefined): FloorShortfall | null {
  const min = size?.enclosure_min_floor_mm;
  if (!min) return null;
  const a = size?.aquatic;
  const [w, d] = a ? tankOuterFloorMm(c, a) : [c.width_mm, c.depth_mm];
  const [needLong, needShort] = min;
  const below = Math.max(w, d) + 1e-6 < needLong || Math.min(w, d) + 1e-6 < needShort;
  return below ? { floorMm: [w, d], minMm: [needLong, needShort], glassMm: a ? glassOf(a) : 0 } : null;
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
