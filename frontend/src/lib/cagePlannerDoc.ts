// 가상 케이지 플래너의 문서: 되돌리기 기록, 화면 정보(이름·종·크기·반려동물·배치안 ID),
// 저장 비교용 스냅샷, 이 브라우저의 임시 저장 (새로 고침·로그인 후 이어서).

import type { Cage, CageLayout, LayoutItem } from "@/lib/types";

const DRAFT_KEY = "nestforge:cage-draft:v1";

// ── 되돌리기 기록 ──

export type Doc = { cage: Cage; items: LayoutItem[] };
type Hist = { past: Doc[]; present: Doc; future: Doc[] };
export type HistAction =
  | { type: "commit"; fn: (d: Doc) => Doc }
  | { type: "preview"; fn: (d: Doc) => Doc } // 끄는 중: 기록 없이 바꾼다
  | { type: "settle"; base: Doc } // 끌기를 마치면 시작 전 상태를 기록에 넣는다
  | { type: "undo" }
  | { type: "redo" }
  | { type: "reset"; doc: Doc };

const HISTORY_LIMIT = 100;

export function histReducer(h: Hist, a: HistAction): Hist {
  switch (a.type) {
    case "commit": {
      const next = a.fn(h.present);
      if (next === h.present) return h;
      return { past: [...h.past, h.present].slice(-HISTORY_LIMIT), present: next, future: [] };
    }
    case "preview":
      return { ...h, present: a.fn(h.present) };
    case "settle":
      if (a.base === h.present) return h;
      return { past: [...h.past, a.base].slice(-HISTORY_LIMIT), present: h.present, future: [] };
    case "undo":
      if (!h.past.length) return h;
      return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1], future: [h.present, ...h.future] };
    case "redo":
      if (!h.future.length) return h;
      return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) };
    case "reset":
      return { past: [], present: a.doc, future: [] };
  }
}

export type Meta = { name: string; species: string; size: string; petId: string | null; layoutId: string | null };
type Draft = Meta & Doc;

/** 서버가 돌려준 배치안에서 화면 정보(이름·종·크기·반려동물·배치안 ID)만 꺼내요 */
export const metaOf = (l: CageLayout): Meta => ({ name: l.name, species: l.species, size: l.size, petId: l.pet_id, layoutId: l.id });

export function readDraft(): Draft | null {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const d = JSON.parse(raw) as Draft;
    if (!d || typeof d !== "object" || !Array.isArray(d.items) || !d.cage) return null;
    return d;
  } catch {
    return null;
  }
}

export function writeDraft(d: Draft | null) {
  try {
    if (d) window.localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
    else window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* 저장소를 쓸 수 없는 브라우저(사생활 보호 모드 등): 임시 저장 없이 계속 */
  }
}

export const snapshotOf = (m: Meta, d: Doc) =>
  JSON.stringify({ n: m.name, s: m.species, z: m.size, p: m.petId, c: d.cage, i: d.items });
