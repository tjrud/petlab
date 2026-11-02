// 가상 케이지 배치 계산: 바닥 차지 영역(회전 사각형), 겹침·거리, 빈 자리 찾기, 벽·구조물 붙이기, 배치 검토.
//
// 좌표계는 백엔드 배치기와 같아요: mm, 원점 = 앞-왼쪽 바닥 모서리, x = 오른쪽, y = 뒤쪽(안쪽), 회전은 위에서 볼 때 반시계.
// 검토 기준 수치(끼임 틈·출입구 폭·오르는 높이)는 서버의 종별 규칙(/species 의 layout_rules)에서 받아요.

import { getAsset, type CageAsset, type Side } from "@/lib/cageAssets";
import type { Cage, LayoutItem, LayoutRules } from "@/lib/types";

export type Pt = { x: number; y: number };
export type Box = { x0: number; y0: number; x1: number; y1: number };

/** 이만큼(mm) 이하로 겹치거나 벽을 넘는 건 계산 오차로 보고 넘어가요 */
const TOL = 0.5;

const rad = (deg: number) => (deg * Math.PI) / 180;

export function normDeg(deg: number): number {
  const d = ((deg % 360) + 360) % 360;
  return Math.round(d * 1000) / 1000 === 360 ? 0 : Math.round(d * 1000) / 1000;
}

/** 에셋 로컬 좌표(바닥 중심 원점) → 케이지 좌표 */
export function toCage(item: LayoutItem, lx: number, ly: number): Pt {
  const t = rad(item.rotation_deg);
  const c = Math.cos(t);
  const s = Math.sin(t);
  return { x: item.x_mm + lx * c - ly * s, y: item.y_mm + lx * s + ly * c };
}

function rectPoly(item: LayoutItem, x0: number, y0: number, x1: number, y1: number): Pt[] {
  return [toCage(item, x0, y0), toCage(item, x1, y0), toCage(item, x1, y1), toCage(item, x0, y1)];
}

/** 바닥을 차지하는 영역 (반시계 방향 꼭짓점 4개) */
export function footprint(item: LayoutItem, asset: CageAsset): Pt[] {
  const [w, d] = asset.size;
  return rectPoly(item, -w / 2, -d / 2, w / 2, d / 2);
}

export function bounds(poly: Pt[]): Box {
  const xs = poly.map((p) => p.x);
  const ys = poly.map((p) => p.y);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}

/** 회전했을 때 위에서 본 가로·세로 (바깥 상자) */
export function rotatedExtent(asset: CageAsset, deg: number): { w: number; d: number } {
  const t = rad(deg);
  const [w, d] = asset.size;
  const c = Math.abs(Math.cos(t));
  const s = Math.abs(Math.sin(t));
  return { w: w * c + d * s, d: w * s + d * c };
}

/** 볼록 다각형 두 개가 겹치는 깊이 (분리축 정리). 떨어져 있으면 0 */
export function overlapDepth(a: Pt[], b: Pt[]): number {
  let min = Infinity;
  for (const poly of [a, b]) {
    for (let i = 0; i < poly.length; i++) {
      const p = poly[i];
      const q = poly[(i + 1) % poly.length];
      const len = Math.hypot(q.x - p.x, q.y - p.y);
      if (len === 0) continue;
      const nx = -(q.y - p.y) / len;
      const ny = (q.x - p.x) / len;
      const proj = (pts: Pt[]) => {
        let lo = Infinity;
        let hi = -Infinity;
        for (const v of pts) {
          const d = v.x * nx + v.y * ny;
          lo = Math.min(lo, d);
          hi = Math.max(hi, d);
        }
        return [lo, hi] as const;
      };
      const [alo, ahi] = proj(a);
      const [blo, bhi] = proj(b);
      const o = Math.min(ahi, bhi) - Math.max(alo, blo);
      if (o <= 0) return 0;
      min = Math.min(min, o);
    }
  }
  return min;
}

function pointSegDist(p: Pt, a: Pt, b: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const L = dx * dx + dy * dy;
  const t = L === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** 떨어진 볼록 다각형 사이의 가장 짧은 거리 (겹치면 0) */
export function polyDistance(a: Pt[], b: Pt[]): number {
  if (overlapDepth(a, b) > 0) return 0;
  let min = Infinity;
  for (const [P, Q] of [
    [a, b],
    [b, a],
  ]) {
    for (const p of P) {
      for (let i = 0; i < Q.length; i++) min = Math.min(min, pointSegDist(p, Q[i], Q[(i + 1) % Q.length]));
    }
  }
  return min;
}

/** 벽까지 거리 (영역의 가장 가까운 점 기준). 벽 밖으로 나가면 음수 */
export function wallGaps(poly: Pt[], cage: Cage): Record<"left" | "right" | "front" | "back", number> {
  const b = bounds(poly);
  return { left: b.x0, right: cage.width_mm - b.x1, front: b.y0, back: cage.depth_mm - b.y1 };
}

/** 출입하는 면 바로 앞, 동물이 지나갈 자리 (폭 = 출입구 폭, 깊이 = 통과 가능한 최소 폭) */
export function accessStrip(item: LayoutItem, asset: CageAsset, side: Side, depth: number): Pt[] {
  const [w, d] = asset.size;
  const along = side === "front" || side === "back" ? w : d;
  const half = Math.min(along, asset.entranceMm ?? along) / 2;
  switch (side) {
    case "front":
      return rectPoly(item, -half, -d / 2 - depth, half, -d / 2);
    case "back":
      return rectPoly(item, -half, d / 2, half, d / 2 + depth);
    case "left":
      return rectPoly(item, -w / 2 - depth, -half, -w / 2, half);
    case "right":
      return rectPoly(item, w / 2, -half, w / 2 + depth, half);
  }
}

// ── 배치 검토 ──

export type CheckSeverity = "error" | "warning";

export type LayoutIssue = {
  key: string;
  severity: CheckSeverity;
  message: string;
  /** 관련 항목 ID (화면에서 강조하고, 누르면 선택해요) */
  itemIds: string[];
};

export type LayoutReport = {
  issues: LayoutIssue[];
  /** 오류가 있는 항목 ID */
  errorIds: Set<string>;
  /** 경고만 있는 항목 ID */
  warningIds: Set<string>;
  /** 바닥 면적 대비 구조물이 차지한 비율 (0~1, 겹친 부분은 두 번 셈) */
  coverage: number;
  /** 카탈로그에 없는 에셋 키 (옛 배치안) */
  unknownAssets: string[];
};

const fmt = (mm: number) => `${Math.round(mm)}mm`;

/** 받침에 맞춰 조사를 붙여요: josa("은신처", "와과") → "은신처와", josa("밥그릇", "이가") → "밥그릇이" */
export function josa(word: string, pair: "이가" | "와과" | "을를" | "은는"): string {
  const code = word.charCodeAt(word.length - 1);
  if (code < 0xac00 || code > 0xd7a3) return `${word}${pair[0]}(${pair[1]})`;
  const batchim = (code - 0xac00) % 28 !== 0;
  const [withB, withoutB] = pair === "이가" ? ["이", "가"] : pair === "와과" ? ["과", "와"] : pair === "을를" ? ["을", "를"] : ["은", "는"];
  return word + (batchim ? withB : withoutB);
}

/**
 * 배치 검토.
 *  - 오류: 케이지 밖으로 나감, 케이지보다 높음, 다른 구조물과 겹침
 *  - 경고(규칙이 있을 때): 끼임 틈, 출입구 앞이 막힘, 출입구·터널이 좁음, 오르는 높이·턱이 높음, 위쪽 끼임 틈
 */
export function checkLayout(cage: Cage, items: LayoutItem[], rules: LayoutRules | null): LayoutReport {
  const issues: LayoutIssue[] = [];
  const unknownAssets: string[] = [];
  const placed: { item: LayoutItem; asset: CageAsset; poly: Pt[] }[] = [];
  for (const item of items) {
    const asset = getAsset(item.asset);
    if (!asset) unknownAssets.push(item.asset);
    else placed.push({ item, asset, poly: footprint(item, asset) });
  }
  const W = cage.width_mm;
  const D = cage.depth_mm;
  const H = cage.height_mm;
  const add = (severity: CheckSeverity, key: string, message: string, ...itemIds: string[]) =>
    issues.push({ severity, key, message, itemIds });

  // 바닥에서 넘어갈 수 있는 낮은 물건(밥그릇·판 등)은 틈·통로를 막지 않는 것으로 봐요
  const low = (a: CageAsset) => rules !== null && a.size[2] <= rules.max_step_height_mm;
  const isTrap = (gap: number) =>
    rules !== null && gap > rules.gap_safe_max_mm + TOL && gap < rules.gap_passable_min_mm - TOL;

  // 케이지 자체가 권장 최소 바닥보다 작으면 (긴 변·짧은 변끼리 비교)
  if (rules) {
    const [minLong, minShort] = rules.enclosure_min_floor_mm;
    const long = Math.max(W, D);
    const short = Math.min(W, D);
    if (long < minLong - TOL || short < minShort - TOL) {
      add(
        "warning",
        "floor",
        `케이지 바닥 ${Math.round(W / 10)}×${Math.round(D / 10)}cm가 권장 최소 ${Math.round(minLong / 10)}×${Math.round(minShort / 10)}cm보다 작아요. 더 넓은 케이지를 권장해요.`,
      );
    }
  }

  for (const { item, asset, poly } of placed) {
    const g = wallGaps(poly, cage);
    const out = Object.values(g).some((v) => v < -TOL);
    if (out) add("error", `out:${item.id}`, `${josa(asset.name, "이가")} 케이지 밖으로 나가 있어요.`, item.id);
    if (asset.size[2] > H + TOL) {
      add("error", `tall:${item.id}`, `${asset.name} 높이 ${fmt(asset.size[2])}가 케이지 높이 ${fmt(H)}보다 높아요.`, item.id);
    }
    if (!rules) continue;
    if (!out && !low(asset)) {
      const trapWalls = (Object.entries(g) as [keyof typeof g, number][]).filter(([, v]) => isTrap(v));
      if (trapWalls.length) {
        const names = { left: "왼쪽", right: "오른쪽", front: "앞", back: "뒤" };
        const where = trapWalls.map(([k, v]) => `${names[k]} 벽 ${fmt(v)}`).join(", ");
        add(
          "warning",
          `wallgap:${item.id}`,
          `${josa(asset.name, "와과")} 벽 사이 틈(${where})에 몸이 끼일 수 있어요. 벽에 붙이거나 ${fmt(rules.gap_passable_min_mm)} 이상 띄워 주세요.`,
          item.id,
        );
      }
    }
    if (asset.entranceMm !== undefined) {
      const min = asset.isTunnel ? rules.tunnel_min_inner_diameter_mm : rules.entrance_min_diameter_mm;
      if (asset.entranceMm < min - TOL) {
        add(
          "warning",
          `entrance:${item.id}`,
          `${asset.name}의 ${asset.isTunnel ? "안지름" : "출입구 폭"} ${fmt(asset.entranceMm)}가 이 아이에게 좁아요 (최소 ${fmt(min)}).`,
          item.id,
        );
      }
    }
    if (asset.climbHeightMm !== undefined) {
      if (asset.climbHeightMm > rules.max_climb_height_mm + TOL) {
        add(
          "warning",
          `climb:${item.id}`,
          `${asset.name} 높이 ${fmt(asset.climbHeightMm)}는 떨어지면 다칠 수 있어요 (권장 최대 ${fmt(rules.max_climb_height_mm)}).`,
          item.id,
        );
      }
      const head = H - asset.size[2];
      if (isTrap(head)) {
        add(
          "warning",
          `ceiling:${item.id}`,
          `${asset.name} 위와 천장 사이(${fmt(head)})에 끼일 수 있어요. 더 낮은 구조물을 쓰거나 천장이 높은 케이지가 좋아요.`,
          item.id,
        );
      }
    }
    if (asset.entranceCount !== undefined && asset.entranceCount < rules.hideout_min_entrances) {
      add(
        "warning",
        `exits:${item.id}`,
        `${josa(asset.name, "은는")} 출입구가 ${asset.entranceCount}개라 막다른 곳이 될 수 있어요. 출입구가 ${rules.hideout_min_entrances}개 이상인 은신처를 권장해요.`,
        item.id,
      );
    }
    if (asset.sandBathInnerMm) {
      const [mw, md] = rules.sand_bath_min_inner_mm;
      const [iw, id] = asset.sandBathInnerMm;
      if (Math.max(iw, id) < Math.max(mw, md) - TOL || Math.min(iw, id) < Math.min(mw, md) - TOL) {
        add(
          "warning",
          `bath:${item.id}`,
          `${asset.name} 안쪽 ${fmt(iw)}×${fmt(id)}가 권장 최소 ${fmt(mw)}×${fmt(md)}보다 작아요.`,
          item.id,
        );
      }
    }
    if (asset.stepHeightMm !== undefined && asset.stepHeightMm > rules.max_step_height_mm + TOL) {
      add(
        "warning",
        `step:${item.id}`,
        `${asset.name} 턱 ${fmt(asset.stepHeightMm)}가 높아 넘어 들어가기 어려워요 (권장 최대 ${fmt(rules.max_step_height_mm)}).`,
        item.id,
      );
    }
  }

  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i];
      const b = placed[j];
      const depth = overlapDepth(a.poly, b.poly);
      if (depth > TOL) {
        add("error", `overlap:${a.item.id}:${b.item.id}`, `${josa(a.asset.name, "와과")} ${josa(b.asset.name, "이가")} 겹쳐요.`, a.item.id, b.item.id);
        continue;
      }
      if (!rules || low(a.asset) || low(b.asset)) continue;
      const gap = polyDistance(a.poly, b.poly);
      if (isTrap(gap)) {
        add(
          "warning",
          `gap:${a.item.id}:${b.item.id}`,
          `${josa(a.asset.name, "와과")} ${b.asset.name} 사이 틈 ${fmt(gap)}에 몸이 끼일 수 있어요. 붙이거나 ${fmt(rules.gap_passable_min_mm)} 이상 띄워 주세요.`,
          a.item.id,
          b.item.id,
        );
      }
    }
  }

  if (rules) {
    const sideName: Record<Side, string> = { front: "앞쪽", back: "뒤쪽", left: "왼쪽", right: "오른쪽" };
    for (const { item, asset } of placed) {
      for (const side of asset.accessSides ?? []) {
        const strip = accessStrip(item, asset, side, rules.gap_passable_min_mm);
        const sb = bounds(strip);
        const blockedByWall = sb.x0 < -TOL || sb.y0 < -TOL || sb.x1 > W + TOL || sb.y1 > D + TOL;
        const blocker = placed.find(
          (o) => o.item.id !== item.id && !low(o.asset) && overlapDepth(strip, o.poly) > TOL,
        );
        if (blockedByWall || blocker) {
          add(
            "warning",
            `access:${item.id}:${side}`,
            `${asset.name}의 ${sideName[side]} 출입구 앞이 ${blocker ? `${blocker.asset.name}에` : "벽에"} 막혀 있어요. 앞에 ${fmt(rules.gap_passable_min_mm)} 이상 비워 주세요.`,
            item.id,
            ...(blocker ? [blocker.item.id] : []),
          );
        }
      }
    }
  }

  const errorIds = new Set<string>();
  const warningIds = new Set<string>();
  for (const iss of issues) for (const id of iss.itemIds) (iss.severity === "error" ? errorIds : warningIds).add(id);
  for (const id of errorIds) warningIds.delete(id);
  const area = placed.reduce((s, p) => s + p.asset.size[0] * p.asset.size[1], 0);
  issues.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1));
  return { issues, errorIds, warningIds, coverage: W * D > 0 ? area / (W * D) : 0, unknownAssets };
}

// ── 놓기·움직이기 도우미 ──

/** 케이지 안이고 다른 구조물과 겹치지 않는지 */
function fits(cage: Cage, poly: Pt[], others: Pt[][]): boolean {
  const b = bounds(poly);
  if (b.x0 < -TOL || b.y0 < -TOL || b.x1 > cage.width_mm + TOL || b.y1 > cage.depth_mm + TOL) return false;
  return others.every((o) => overlapDepth(poly, o) <= TOL);
}

/**
 * 새 에셋을 둘 자리. 실제 케이지처럼 벽·모서리부터 채워요.
 * 겹치지 않는 후보 중 (규칙이 있으면) 끼임 틈·출입구 막힘이 적은 곳, 그다음 벽·모서리에 붙는 곳, 그다음 뒤쪽을 골라요.
 * 후보는 벽에 붙는 위치, 다른 구조물에 붙는 위치, 일정 간격 격자예요. 자리가 없으면 가운데.
 */
export function findFreeSpot(
  cage: Cage,
  items: LayoutItem[],
  asset: CageAsset,
  rotation = 0,
  rules: LayoutRules | null = null,
): Pt {
  const W = cage.width_mm;
  const D = cage.depth_mm;
  const others: { asset: CageAsset; poly: Pt[]; strips: Pt[][] }[] = [];
  for (const it of items) {
    const a = getAsset(it.asset);
    if (!a) continue;
    const strips = rules ? (a.accessSides ?? []).map((sd) => accessStrip(it, a, sd, rules.gap_passable_min_mm)) : [];
    others.push({ asset: a, poly: footprint(it, a), strips });
  }
  const low = (a: CageAsset) => rules !== null && a.size[2] <= rules.max_step_height_mm;
  const isTrap = (gap: number) =>
    rules !== null && gap > rules.gap_safe_max_mm + TOL && gap < rules.gap_passable_min_mm - TOL;

  const { w, d } = rotatedExtent(asset, rotation);
  const xs = new Set<number>([w / 2, W - w / 2, W / 2]);
  const ys = new Set<number>([d / 2, D - d / 2, D / 2]);
  const pass = rules?.gap_passable_min_mm ?? 0;
  for (const o of others) {
    const b = bounds(o.poly);
    for (const g of [0, pass]) {
      xs.add(b.x1 + g + w / 2);
      xs.add(b.x0 - g - w / 2);
      ys.add(b.y1 + g + d / 2);
      ys.add(b.y0 - g - d / 2);
    }
  }
  const step = Math.max(10, Math.round(Math.min(W, D) / 30 / 10) * 10);
  for (let x = w / 2; x <= W - w / 2 + 1e-6; x += step) xs.add(x);
  for (let y = d / 2; y <= D - d / 2 + 1e-6; y += step) ys.add(y);

  let best: Pt | null = null;
  let bestScore = Infinity;
  for (const x of xs) {
    for (const y of ys) {
      const cand: LayoutItem = { id: "_", asset: asset.key, x_mm: x, y_mm: y, rotation_deg: rotation };
      const poly = footprint(cand, asset);
      if (!fits(cage, poly, others.map((o) => o.poly))) continue;
      const g = wallGaps(poly, cage);
      let problems = 0;
      if (rules) {
        if (!low(asset)) problems += Object.values(g).filter(isTrap).length;
        for (const o of others) {
          if (!low(asset) && !low(o.asset) && isTrap(polyDistance(poly, o.poly))) problems++;
          // 다른 구조물의 출입구 앞을 막지 않게
          if (!low(asset) && o.strips.some((st) => overlapDepth(st, poly) > TOL)) problems++;
        }
        for (const sd of asset.accessSides ?? []) {
          const st = accessStrip(cand, asset, sd, rules.gap_passable_min_mm);
          const sb = bounds(st);
          const wall = sb.x0 < -TOL || sb.y0 < -TOL || sb.x1 > W + TOL || sb.y1 > D + TOL;
          if (wall || others.some((o) => !low(o.asset) && overlapDepth(st, o.poly) > TOL)) problems++;
        }
      }
      // 벽·모서리에 붙을수록, 뒤쪽일수록 좋아요 (앞은 관찰 면이라 비워 두는 편이 보기 좋아요)
      const score = problems * 1e6 + Math.min(g.left, g.right) + Math.min(g.front, g.back) + g.back * 0.01;
      if (score < bestScore) {
        bestScore = score;
        best = { x, y };
      }
    }
  }
  return best ?? { x: W / 2, y: D / 2 };
}

/** 이 거리(mm) 안으로 다가가면 벽·구조물 모서리에 착 붙어요 */
export const SNAP_MM = 15;

/**
 * 움직인 위치를 다듬어요: 격자에 맞추고, 벽이나 옆 구조물 모서리에 가까우면 붙여요.
 * 케이지 밖으로 완전히 나가지는 않게 가운데 점을 케이지 안으로 묶어 둬요.
 */
export function snapPosition(
  cage: Cage,
  items: LayoutItem[],
  moving: LayoutItem,
  asset: CageAsset,
  grid: number,
  magnet: boolean,
): Pt {
  let x = Math.min(Math.max(moving.x_mm, 0), cage.width_mm);
  let y = Math.min(Math.max(moving.y_mm, 0), cage.depth_mm);
  if (grid > 0) {
    x = Math.round(x / grid) * grid;
    y = Math.round(y / grid) * grid;
  }
  if (!magnet) return { x, y };
  const b = bounds(footprint({ ...moving, x_mm: x, y_mm: y }, asset));
  const xTargets: { edge: "x0" | "x1"; at: number }[] = [
    { edge: "x0", at: 0 },
    { edge: "x1", at: cage.width_mm },
  ];
  const yTargets: { edge: "y0" | "y1"; at: number }[] = [
    { edge: "y0", at: 0 },
    { edge: "y1", at: cage.depth_mm },
  ];
  for (const it of items) {
    if (it.id === moving.id) continue;
    const a = getAsset(it.asset);
    if (!a) continue;
    const o = bounds(footprint(it, a));
    // 옆으로 나란한 구조물에만 붙어요 (반대 축 범위가 겹칠 때)
    if (o.y0 < b.y1 && o.y1 > b.y0) xTargets.push({ edge: "x0", at: o.x1 }, { edge: "x1", at: o.x0 });
    if (o.x0 < b.x1 && o.x1 > b.x0) yTargets.push({ edge: "y0", at: o.y1 }, { edge: "y1", at: o.y0 });
  }
  let dx = 0;
  let best = SNAP_MM;
  for (const t of xTargets) {
    const delta = t.at - b[t.edge];
    if (Math.abs(delta) < best) {
      best = Math.abs(delta);
      dx = delta;
    }
  }
  let dy = 0;
  best = SNAP_MM;
  for (const t of yTargets) {
    const delta = t.at - b[t.edge];
    if (Math.abs(delta) < best) {
      best = Math.abs(delta);
      dy = delta;
    }
  }
  return { x: x + dx, y: y + dy };
}

/** 케이지 밖으로 나간 항목을 벽 안쪽으로 밀어 넣어요 (케이지를 줄였을 때) */
export function pullInside(cage: Cage, item: LayoutItem): LayoutItem {
  const a = getAsset(item.asset);
  if (!a) return item;
  const { w, d } = rotatedExtent(a, item.rotation_deg);
  const clamp = (v: number, half: number, max: number) => (half * 2 > max ? max / 2 : Math.min(Math.max(v, half), max - half));
  return {
    ...item,
    x_mm: Math.round(clamp(item.x_mm, w / 2, cage.width_mm) * 10) / 10,
    y_mm: Math.round(clamp(item.y_mm, d / 2, cage.depth_mm) * 10) / 10,
  };
}

let seq = 0;
/** 배치안 안에서 겹치지 않는 항목 ID */
export function newItemId(): string {
  seq = (seq + 1) % 1e6;
  return `i${Date.now().toString(36)}${seq.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
