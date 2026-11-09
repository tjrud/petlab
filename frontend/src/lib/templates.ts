// 구조물 종류별 표시 정보 (뷰어 색상, 파라미터 이름)
// 파라미터 이름은 한국어 원문으로 두고, 보여 줄 때 t(PARAM_LABELS[k]) 로 번역한다

import type { TFunction } from "@/i18n/translate";

export const TEMPLATE_COLORS: Record<string, string> = {
  hideout: "#d9a066",
  tunnel: "#7fb0a0",
  ramp: "#b99ad6",
  sand_bath: "#e6cf8f",
  house: "#c97f6b",
};

export const PARAM_LABELS: Record<string, string> = {
  width_mm: "가로",
  depth_mm: "세로",
  height_mm: "높이",
  entrance_diameter_mm: "출입구 폭",
  entrance_count: "출입구 개수",
  vent_count: "환기구 개수",
  vent_diameter_mm: "환기구 지름",
  wall_thickness_mm: "벽 두께",
  length_mm: "길이",
  inner_diameter_mm: "내경",
  bend_angle_deg: "휨 각도",
  slope_deg: "경사각",
  steps: "단 수",
  lip_height_mm: "턱 높이",
  basin_depth_mm: "안쪽 깊이",
  shape: "단면 모양",
  path: "휘는 모양",
  // 집(house) 템플릿: 중첩 파라미터는 점 표기 키로 보여 준다
  "walls.thickness_mm": "벽 두께",
  "floor.enabled": "바닥판",
  "floor.thickness_mm": "바닥판 두께",
  "roof.kind": "지붕 모양",
  "roof.pitch_deg": "지붕 경사",
  "roof.tip_deg": "지붕 꼭대기 각도",
  "floors.count": "층 수",
  "floors.level_height_mm": "2층 바닥 높이",
  "floors.plate_thickness_mm": "층판 두께",
  "floors.climb": "오르는 수단",
  "floors.ramp_width_mm": "내부 경사로 폭",
  "floors.slope_deg": "내부 경사로 경사",
  "floors.exit_side": "2층 출입구 면",
  "doors.sides": "출입구 면",
  "doors.width_mm": "출입구 폭",
  "windows.count": "창 개수",
  "windows.diameter_mm": "창 지름",
  "ports.sides": "터널 연결부 면",
  "ports.diameter_mm": "연결부 폭",
  "ports.flange_mm": "플랜지 길이",
};

const SIDE_LABELS: Record<string, string> = { front: "앞", back: "뒤", left: "왼쪽", right: "오른쪽" };

/** 고르는 값으로 된 파라미터(단면 모양 등)의 이름 */
export const CHOICE_LABELS: Record<string, Record<string, string>> = {
  shape: {
    pointed_arch: "뾰족 아치",
    round_arch: "둥근 아치",
    tube: "둥근 관",
    box: "네모",
    house: "집 모양",
  },
  path: { arc: "한 방향 곡선", s_curve: "S자" },
  "roof.kind": { flat: "평 지붕", pitched: "경사 지붕", rounded: "둥근 지붕" },
  "floors.climb": { internal_ramp: "내부 경사로", external_ramp: "바깥 램프" },
  "floors.exit_side": SIDE_LABELS,
  "doors.sides": SIDE_LABELS,
  "ports.sides": SIDE_LABELS,
};

/** 파라미터 값 (숫자·선택값·참/거짓·면 목록·중첩 부품) */
export type ParamValue = number | string | boolean | string[] | { [key: string]: ParamValue };

/**
 * 중첩 파라미터(집 템플릿의 부품)를 점 표기 키로 펼친다. 쓰이지 않는 부품 값(평 지붕의 경사각, 1층 집의 층 값 등)은 뺀다.
 */
export function flattenParams(params: Record<string, ParamValue>): [string, ParamValue][] {
  const out: [string, ParamValue][] = [];
  const walk = (obj: Record<string, ParamValue>, prefix: string) => {
    for (const [k, v] of Object.entries(obj)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v !== null && typeof v === "object" && !Array.isArray(v)) walk(v, key);
      else out.push([key, v]);
    }
  };
  walk(params, "");
  const get = (k: string) => out.find(([key]) => key === k)?.[1];
  const roof = get("roof.kind");
  const floors = get("floors.count");
  const climb = get("floors.climb");
  const windows = get("windows.count");
  const ports = get("ports.sides");
  return out.filter(([key]) => {
    if (key === "roof.pitch_deg") return roof === "pitched";
    if (key === "roof.tip_deg") return roof === "rounded";
    if (key === "floor.thickness_mm") return get("floor.enabled") !== false;
    if (key.startsWith("floors.") && key !== "floors.count") {
      if (floors !== 2) return false;
      if (["floors.ramp_width_mm", "floors.slope_deg"].includes(key)) return climb === "internal_ramp";
      if (key === "floors.exit_side") return climb === "external_ramp";
    }
    if (key === "windows.diameter_mm") return windows !== 0;
    if (["ports.diameter_mm", "ports.flange_mm"].includes(key)) return !(Array.isArray(ports) && ports.length === 0);
    return true;
  });
}

export function formatParam(key: string, value: ParamValue, t: TFunction): string {
  if (typeof value === "boolean") return value ? t("있음") : t("없음");
  if (Array.isArray(value)) {
    if (value.length === 0) return t("없음");
    return value.map((v) => formatParam(key, v, t)).join(" · ");
  }
  if (typeof value === "object") return "";
  if (typeof value === "string") {
    const label = CHOICE_LABELS[key]?.[value];
    return label ? t(label) : value;
  }
  const v = Number.isInteger(value) ? value.toString() : value.toFixed(1);
  if (key.endsWith("_mm")) return `${v}mm`;
  if (key.endsWith("_deg")) return `${v}°`;
  if (key === "steps") return value === 0 ? t("경사로") : t("{n}단", { n: v });
  if (key === "floors.count") return t("{n}층", { n: v });
  if (key.endsWith("_count") || key.endsWith(".count")) return t("{n}개", { n: v });
  return v;
}
