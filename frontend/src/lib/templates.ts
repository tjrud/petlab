// 구조물 종류별 표시 정보 (뷰어 색상, 파라미터 이름)
// 파라미터 이름은 한국어 원문으로 두고, 보여 줄 때 t(PARAM_LABELS[k]) 로 번역한다

import type { TFunction } from "@/i18n/translate";

export const TEMPLATE_COLORS: Record<string, string> = {
  hideout: "#d9a066",
  tunnel: "#7fb0a0",
  ramp: "#b99ad6",
  sand_bath: "#e6cf8f",
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
};

export function formatParam(key: string, value: number, t: TFunction): string {
  const v = Number.isInteger(value) ? value.toString() : value.toFixed(1);
  if (key.endsWith("_mm")) return `${v}mm`;
  if (key.endsWith("_deg")) return `${v}°`;
  if (key === "steps") return value === 0 ? t("경사로") : t("{n}단", { n: v });
  if (key.endsWith("_count")) return t("{n}개", { n: v });
  return v;
}
