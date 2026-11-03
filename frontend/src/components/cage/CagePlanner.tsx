"use client";

// 가상 케이지 공간 설계: 케이지 크기를 정하고, 기본 에셋을 게임처럼 골라 놓고 옮기고 돌려 보며
// 겹침·케이지 밖·끼임 틈·출입구 공간을 바로 확인해요. 로그인하면 배치안을 계정에 저장할 수 있어요.
// 로그인하지 않아도 쓸 수 있고, 작업 중인 배치는 이 브라우저에 임시로 남겨 둬요 (새로 고침·로그인 후 이어서).

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import CageSizePanel from "@/components/cage/CageSizePanel";
import CatalogPanel from "@/components/cage/CatalogPanel";
import InspectorPanel from "@/components/cage/InspectorPanel";
import LayoutsPanel from "@/components/cage/LayoutsPanel";
import ReviewPanel from "@/components/cage/ReviewPanel";
import type { CameraView } from "@/components/cage/PlannerScene";
import { api, ApiError, isAuthError } from "@/lib/api";
import { getAsset, type CageAsset } from "@/lib/cageAssets";
import {
  checkLayout,
  findFreeSpot,
  isOutsideCage,
  newItemId,
  normDeg,
  pullInside,
  round1,
  snapPosition,
} from "@/lib/cageLayout";
import type { Cage, CageLayout, CageLayoutInput, CageLayoutSummary, LayoutItem, LayoutRules, Pet, SpeciesResponse } from "@/lib/types";
import { ui } from "@/lib/ui";

const PlannerScene = dynamic(() => import("@/components/cage/PlannerScene"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-stone-500">3D 화면 준비 중…</div>,
});

// 처음 크기는 종 규칙의 사육장 최소 기준(100×50×50cm, species.yaml enclosure_min_floor_mm)에 맞춰요
const DEFAULT_CAGE: Cage = { width_mm: 1000, depth_mm: 500, height_mm: 500 };
const DEFAULT_NAME = "새 배치안";
const DRAFT_KEY = "nestforge:cage-draft:v1";
const MAX_ITEMS = 80; // 서버 MAX_LAYOUT_ITEMS 와 같다
/** "기본 구성 한 번에 넣기": 쳇바퀴는 케이지 높이에 들어가는 것 중 큰 것으로 */
const STARTER = ["hideout_multi", "wheel", "sand_bath", "bowl", "water_stand"];
const WHEELS = ["wheel_280", "wheel_210"];

// ── 되돌리기 기록 ──

type Doc = { cage: Cage; items: LayoutItem[] };
type Hist = { past: Doc[]; present: Doc; future: Doc[] };
type HistAction =
  | { type: "commit"; fn: (d: Doc) => Doc }
  | { type: "preview"; fn: (d: Doc) => Doc } // 끄는 중: 기록 없이 바꾼다
  | { type: "settle"; base: Doc } // 끌기를 마치면 시작 전 상태를 기록에 넣는다
  | { type: "undo" }
  | { type: "redo" }
  | { type: "reset"; doc: Doc };

const HISTORY_LIMIT = 100;

function histReducer(h: Hist, a: HistAction): Hist {
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

type Meta = { name: string; species: string; size: string; petId: string | null; layoutId: string | null };
type Draft = Meta & Doc;

/** 서버가 돌려준 배치안에서 화면 정보(이름·종·크기·반려동물·배치안 ID)만 꺼내요 */
const metaOf = (l: CageLayout): Meta => ({ name: l.name, species: l.species, size: l.size, petId: l.pet_id, layoutId: l.id });

/** 새 항목: 빈 자리(벽·모서리부터)에 회전 0으로 놓아요. 키 순서는 저장 비교(snapshotOf)와 맞춰 둬요 */
function newItemAt(cage: Cage, items: LayoutItem[], asset: CageAsset, rules: LayoutRules | null): LayoutItem {
  const p = findFreeSpot(cage, items, asset, 0, rules);
  return { id: newItemId(), asset: asset.key, x_mm: round1(p.x), y_mm: round1(p.y), rotation_deg: 0 };
}

function readDraft(): Draft | null {
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

function writeDraft(d: Draft | null) {
  try {
    if (d) window.localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
    else window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* 저장소를 쓸 수 없는 브라우저(사생활 보호 모드 등): 임시 저장 없이 계속 */
  }
}

const snapshotOf = (m: Meta, d: Doc) =>
  JSON.stringify({ n: m.name, s: m.species, z: m.size, p: m.petId, c: d.cage, i: d.items });

function isTyping(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

type Tab = "catalog" | "cage" | "saved";

export default function CagePlanner() {
  const router = useRouter();
  const wantedLayout = useSearchParams().get("layout");
  const { status, user } = useAuth();
  const userId = user?.id ?? null;

  const [hist, dispatch] = useReducer(histReducer, { past: [], present: { cage: DEFAULT_CAGE, items: [] }, future: [] });
  const { cage, items } = hist.present;
  const [meta, setMeta] = useState<Meta>({ name: DEFAULT_NAME, species: "hamster", size: "syrian", petId: null, layoutId: null });
  /** 마지막으로 저장(또는 불러온) 상태. 지금 상태와 다르면 저장하지 않은 변경이 있다 */
  const [savedSnap, setSavedSnap] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<CameraView>("3d");
  const [viewNonce, setViewNonce] = useState(0);
  const [grid, setGrid] = useState(true);
  const [magnet, setMagnet] = useState(true);
  const [tab, setTab] = useState<Tab>("catalog");

  const [species, setSpecies] = useState<SpeciesResponse | null>(null);
  const [pets, setPets] = useState<Pet[] | null>(null);
  const [layouts, setLayouts] = useState<CageLayoutSummary[] | null>(null);
  const [layoutsError, setLayoutsError] = useState<string | null>(null);
  /** 저장·삭제 중 (요청을 기다리는 동안) */
  const [writing, setWriting] = useState(false);
  /** 배치안 불러오는 중 */
  const [loadingLayout, setLoadingLayout] = useState(false);
  const busy = writing || loadingLayout;
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [ready, setReady] = useState(false);

  // ── 규칙·내 정보 불러오기 ──

  useEffect(() => {
    let alive = true;
    api
      .species()
      .then((s) => alive && setSpecies(s))
      .catch(() => alive && setSpecies(null));
    return () => {
      alive = false;
    };
  }, []);

  const refreshLayouts = useCallback(() => {
    api
      .layouts()
      .then((l) => {
        setLayouts(l);
        setLayoutsError(null);
      })
      .catch((e: unknown) => {
        if (!isAuthError(e)) setLayoutsError(e instanceof ApiError ? e.messageKo : "배치안 목록을 불러오지 못했어요.");
      });
  }, []);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    api
      .pets()
      .then((p) => alive && setPets(p))
      .catch(() => alive && setPets(null));
    refreshLayouts();
    return () => {
      alive = false;
    };
  }, [userId, refreshLayouts]);

  const sizeOpt = species?.species.find((s) => s.key === meta.species)?.sizes.find((z) => z.key === meta.size);
  const rules = sizeOpt?.layout_rules ?? null;
  const report = useMemo(() => checkLayout(cage, items, rules), [cage, items, rules]);

  // ── 배치안 불러오기 (주소의 ?layout=) / 임시 저장 되살리기 ──

  /** 화면의 배치를 통째로 바꿀 때마다 올리는 번호 (불러오기·임시 저장 되살리기·새로 만들기) */
  const docGen = useRef(0);

  const applyLayout = useCallback((l: CageLayout) => {
    const m = metaOf(l);
    const d: Doc = { cage: l.cage, items: l.items };
    docGen.current += 1;
    setMeta(m);
    dispatch({ type: "reset", doc: d });
    setSavedSnap(snapshotOf(m, d));
    setSelectedId(null);
    setViewNonce((n) => n + 1);
  }, []);

  /** 효과가 마지막으로 처리한 주소의 배치안 ID. 주소가 실제로 바뀌었을 때만 처리해요 */
  const seenParam = useRef<string | null | undefined>(undefined);
  /** 화면에서 직접 바꾼 주소의 배치안 ID (저장·새로 만들기·삭제 뒤). 효과가 그 주소에 닿으면 다시 불러오지 않아요 */
  const selfNav = useRef<string | null | undefined>(undefined);
  /** 진행 중인 배치안 불러오기의 번호. 그사이 주소가 바뀌면 늦게 온 응답은 버려요 */
  const loadSeq = useRef(0);
  const loading = useRef<number | null>(null);
  /** 저장·삭제가 끝났을 때 다른 화면에 가 있어서 미뤄 둔 주소 맞추기 (from 주소로 돌아오면 to 로 바꿔요) */
  const pendingParam = useRef<{ from: string | null | undefined; to: string | null } | null>(null);

  /** 화면의 상태를 먼저 바꾼 뒤 주소만 맞춰요 (그 주소의 배치안을 다시 불러오지 않게) */
  const replaceLayoutParam = useCallback((id: string | null) => {
    if (window.location.pathname !== "/cage") {
      // 저장·삭제를 기다리는 사이 다른 화면으로 떠났으면 지금 주소는 건드리지 않고, 돌아왔을 때 맞춰요
      pendingParam.current = { from: seenParam.current, to: id };
      selfNav.current = undefined;
      return;
    }
    pendingParam.current = null;
    // 비교 대상은 효과가 이미 처리한 주소예요 (로그인 상태를 기다리는 동안에는 아직 처리 전)
    selfNav.current = id === seenParam.current ? undefined : id;
    // router.replace 는 서버 왕복을 기다리는 전환이라 그사이 다른 이동이 끼면 버려질 수 있어요.
    // history.replaceState 는 Next 가 서버 왕복 없이 반영해요 (useSearchParams 는 다음 렌더에 바뀜)
    window.history.replaceState(null, "", id ? `/cage?layout=${id}` : "/cage");
  }, []);

  const loadLayout = useCallback(
    (id: string) => {
      const seq = ++loadSeq.current;
      loading.current = seq;
      setLoadingLayout(true);
      api
        .layout(id)
        .then((l) => {
          if (loading.current === seq) applyLayout(l);
        })
        .catch((e: unknown) => {
          if (loading.current === seq) setNotice({ kind: "error", text: e instanceof ApiError ? e.messageKo : "배치안을 불러오지 못했어요." });
        })
        .finally(() => {
          if (loading.current !== seq) return;
          loading.current = null;
          setLoadingLayout(false);
          setReady(true);
        });
    },
    [applyLayout],
  );

  // 브라우저 저장소와 로그인 상태는 서버 렌더 때 알 수 없으므로, 화면이 붙은 뒤 효과에서 한 번 상태를 채워요
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    // 다른 화면에 가 있는 동안 끝난 저장·삭제의 주소 맞추기: 떠날 때의 주소로 돌아왔으면(뒤로 가기 등) 이제 맞춰요
    const pending = pendingParam.current;
    if (pending) {
      pendingParam.current = null;
      if (wantedLayout === pending.from && seenParam.current === pending.from) {
        replaceLayoutParam(pending.to);
        return;
      }
    }
    // 주소가 그대로면 아무것도 하지 않아요. 메타만 바뀐 렌더나, 주소 변경이 아직 반영되기 전 렌더에서
    // 옛 주소를 보고 옛 배치안을 다시 불러오면 안 돼요
    if (seenParam.current === wantedLayout) return;
    // 저장한 배치안을 열려면 로그인 상태가 필요해요. 브라우저 임시 저장은 기다리지 않고 바로 되살려요
    if (wantedLayout && status === null) return;
    seenParam.current = wantedLayout;
    // 주소가 바뀌었으니 진행 중인 불러오기는 버려요 (예: 불러오는 중에 뒤로 가기)
    if (loading.current !== null) {
      loading.current = null;
      setLoadingLayout(false);
    }
    const mine = selfNav.current !== undefined && selfNav.current === wantedLayout;
    selfNav.current = undefined;
    if (mine) {
      setReady(true);
      return;
    }
    if (!wantedLayout) {
      const d = readDraft();
      if (d && !ready) {
        const m: Meta = { name: d.name || DEFAULT_NAME, species: d.species, size: d.size, petId: d.petId, layoutId: d.layoutId };
        setMeta(m);
        const valid = (i: LayoutItem) =>
          typeof i?.id === "string" && typeof i.asset === "string" &&
          [i.x_mm, i.y_mm, i.rotation_deg].every((v) => typeof v === "number" && Number.isFinite(v));
        docGen.current += 1;
        dispatch({ type: "reset", doc: { cage: d.cage, items: d.items.filter(valid) } });
      }
      setReady(true);
      return;
    }
    if (meta.layoutId === wantedLayout) {
      setReady(true);
      return;
    }
    if (!userId) {
      setReady(true);
      setNotice({ kind: "error", text: "저장한 배치안은 로그인하면 열 수 있어요." });
      return;
    }
    loadLayout(wantedLayout);
  }, [status, wantedLayout, userId, meta.layoutId, ready, loadLayout, replaceLayoutParam]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // 작업 중인 배치를 이 브라우저에 남겨요 (불러오기를 마친 뒤부터)
  useEffect(() => {
    if (!ready) return;
    const empty = items.length === 0 && !meta.layoutId && meta.name === DEFAULT_NAME;
    writeDraft(empty ? null : { ...meta, cage, items });
  }, [ready, meta, cage, items]);

  const snap = snapshotOf(meta, hist.present);
  const dirty = savedSnap === null ? items.length > 0 : snap !== savedSnap;

  // ── 편집 동작 ──

  const commit = useCallback((fn: (d: Doc) => Doc) => dispatch({ type: "commit", fn }), []);

  const updateItem = useCallback(
    (id: string, fn: (it: LayoutItem) => LayoutItem) =>
      commit((d) => ({ ...d, items: d.items.map((it) => (it.id === id ? fn(it) : it)) })),
    [commit],
  );

  const addAsset = useCallback(
    (asset: CageAsset) => {
      if (items.length >= MAX_ITEMS) {
        setNotice({ kind: "error", text: `구조물은 ${MAX_ITEMS}개까지 놓을 수 있어요.` });
        return;
      }
      const item = newItemAt(cage, items, asset, rules);
      commit((d) => ({ ...d, items: [...d.items, item] }));
      setSelectedId(item.id);
    },
    [cage, items, commit, rules],
  );

  const addStarter = useCallback(() => {
    commit((d) => {
      let list = d.items;
      for (const slot of STARTER) {
        const key =
          slot === "wheel" ? (WHEELS.find((k) => (getAsset(k)?.size[2] ?? Infinity) <= d.cage.height_mm) ?? null) : slot;
        const a = key ? getAsset(key) : undefined;
        if (!a || list.length >= MAX_ITEMS) continue;
        list = [...list, newItemAt(d.cage, list, a, rules)];
      }
      return { ...d, items: list };
    });
  }, [commit, rules]);

  const removeItem = useCallback(
    (id: string) => {
      commit((d) => ({ ...d, items: d.items.filter((it) => it.id !== id) }));
      setSelectedId((s) => (s === id ? null : s));
    },
    [commit],
  );

  const duplicateItem = useCallback(
    (id: string) => {
      const src = items.find((it) => it.id === id);
      const asset = src && getAsset(src.asset);
      if (!src || !asset || items.length >= MAX_ITEMS) return;
      const p = findFreeSpot(cage, items, asset, src.rotation_deg, rules);
      const copy: LayoutItem = { ...src, id: newItemId(), x_mm: round1(p.x), y_mm: round1(p.y) };
      commit((d) => ({ ...d, items: [...d.items, copy] }));
      setSelectedId(copy.id);
    },
    [items, cage, commit, rules],
  );

  const rotateItem = useCallback(
    (id: string, deg: number, absolute = false) =>
      commit((d) => ({
        ...d,
        items: d.items.map((it) => {
          if (it.id !== id) return it;
          const next = { ...it, rotation_deg: normDeg(absolute ? deg : it.rotation_deg + deg) };
          // 벽 가까이에서 돌려도 케이지 밖으로 나가지 않게 안쪽으로 밀어 줘요 (원래 안에 있던 경우)
          const a = getAsset(it.asset);
          const wasInside = a && !isOutsideCage(it, a, d.cage);
          return wasInside ? pullInside(d.cage, next) : next;
        }),
      })),
    [commit],
  );

  const moveItem = useCallback(
    (id: string, x: number, y: number) => updateItem(id, (it) => ({ ...it, x_mm: round1(x), y_mm: round1(y) })),
    [updateItem],
  );

  // 끌어서 옮기기
  const dragBase = useRef<Doc | null>(null);
  const onDragStart = useCallback(() => {
    dragBase.current = hist.present;
  }, [hist.present]);
  const onDrag = useCallback(
    (id: string, x: number, y: number) =>
      dispatch({
        type: "preview",
        fn: (d) => {
          const it = d.items.find((i) => i.id === id);
          const a = it && getAsset(it.asset);
          if (!it || !a) return d;
          const p = snapPosition(d.cage, d.items, { ...it, x_mm: x, y_mm: y }, a, grid ? 10 : 0, magnet);
          const nx = round1(p.x);
          const ny = round1(p.y);
          if (nx === it.x_mm && ny === it.y_mm) return d;
          return { ...d, items: d.items.map((i) => (i.id === id ? { ...i, x_mm: nx, y_mm: ny } : i)) };
        },
      }),
    [grid, magnet],
  );
  const onDragEnd = useCallback(() => {
    if (dragBase.current) dispatch({ type: "settle", base: dragBase.current });
    dragBase.current = null;
  }, []);

  const applyCage = useCallback((c: Cage) => {
    commit((d) => (d.cage.width_mm === c.width_mm && d.cage.depth_mm === c.depth_mm && d.cage.height_mm === c.height_mm ? d : { ...d, cage: c }));
    setViewNonce((n) => n + 1);
  }, [commit]);

  const outsideCount = useMemo(
    () =>
      items.filter((it) => {
        const a = getAsset(it.asset);
        return a && isOutsideCage(it, a, cage);
      }).length,
    [items, cage],
  );

  const pullAllInside = useCallback(() => commit((d) => ({ ...d, items: d.items.map((it) => pullInside(d.cage, it)) })), [commit]);

  const pickPet = useCallback(
    (p: Pet) => {
      setMeta((m) => ({ ...m, species: p.species, size: p.size, petId: p.id }));
      if (p.cage) applyCage(p.cage);
    },
    [applyCage],
  );

  // ── 키보드 ──

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? "redo" : "undo" });
        return;
      }
      if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        dispatch({ type: "redo" });
        return;
      }
      if (!selectedId) return;
      if (mod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        duplicateItem(selectedId);
        return;
      }
      if (mod || e.altKey) return;
      const step = e.shiftKey ? 1 : 10;
      const moves: Record<string, [number, number]> = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, step], // 화면 위쪽 = 케이지 안쪽(뒤)
        ArrowDown: [0, -step],
      };
      if (e.key in moves) {
        e.preventDefault();
        const [dx, dy] = moves[e.key];
        updateItem(selectedId, (it) => ({ ...it, x_mm: round1(it.x_mm + dx), y_mm: round1(it.y_mm + dy) }));
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        removeItem(selectedId);
      } else if (e.key === "r" || e.key === "R") {
        rotateItem(selectedId, e.shiftKey ? -90 : 90);
      } else if (e.key === "q" || e.key === "Q") {
        rotateItem(selectedId, 15);
      } else if (e.key === "e" || e.key === "E") {
        rotateItem(selectedId, -15);
      } else if (e.key === "Escape") {
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, duplicateItem, removeItem, rotateItem, updateItem]);

  // ── 저장·불러오기·새로 만들기 ──

  const body = (): CageLayoutInput => ({
    name: meta.name.trim() || DEFAULT_NAME,
    species: meta.species,
    size: meta.size,
    cage,
    pet_id: meta.petId,
    // 카탈로그에 있는 것만, 서버 범위 안의 값으로
    items: items
      .filter((it) => getAsset(it.asset))
      .map((it) => ({
        ...it,
        x_mm: Math.min(2500, Math.max(-500, round1(it.x_mm))),
        y_mm: Math.min(2500, Math.max(-500, round1(it.y_mm))),
        rotation_deg: normDeg(it.rotation_deg),
      })),
  });

  /** 저장·삭제를 시작한 때의 화면 배치 번호와 불러오기 번호 */
  const placeNow = () => ({ gen: docGen.current, seq: loadSeq.current });
  /** 그사이 화면의 배치가 다른 것으로 바뀌었거나 바뀌는 중인지 (뒤로·앞으로 가기로 다른 배치안을 불러옴 등).
   *  주소만 바뀌고 같은 배치가 그대로면(메뉴의 '가상 케이지', 다른 화면에 다녀옴) 옮겨 간 것이 아니에요 */
  const movedSince = (p: { gen: number; seq: number }) =>
    docGen.current !== p.gen || (loading.current !== null && loadSeq.current !== p.seq);

  const save = async (saveAsNew: boolean) => {
    let asNew = saveAsNew;
    if (busy) return;
    setWriting(true);
    setNotice(null);
    const start = placeNow();
    try {
      let b = body();
      let petDropped = false;
      // 연결한 반려동물이 이 계정에 없으면(지웠거나, 임시 저장이 다른 계정의 것) 연결만 빼고 다시 저장해요
      const write = async (send: (x: CageLayoutInput) => Promise<CageLayout>) => {
        try {
          return await send(b);
        } catch (e) {
          if (!(e instanceof ApiError && e.code === "pet_not_found" && b.pet_id)) throw e;
          b = { ...b, pet_id: null };
          petDropped = true;
          return await send(b);
        }
      };
      let saved: CageLayout;
      const openId = meta.layoutId;
      if (openId && !asNew) {
        try {
          saved = await write((x) => api.updateLayout(openId, x));
        } catch (e) {
          // 다른 곳에서 지웠거나, 이 브라우저의 임시 저장이 다른 계정의 배치안을 가리키면 새 배치안으로 저장해요
          if (!(e instanceof ApiError && e.status === 404)) throw e;
          saved = await write(api.createLayout);
          asNew = true;
        }
      } else {
        saved = await write(api.createLayout);
      }
      const petNote = petDropped ? " 연결된 반려동물을 찾을 수 없어 반려동물 연결은 빼고 저장했어요." : "";
      if (movedSince(start)) {
        // 저장을 기다리는 사이 다른 배치안으로 옮겨 갔으면 지금 화면에는 반영하지 않고 알리기만 해요
        setNotice({ kind: "ok", text: `"${saved.name}" 배치안으로 저장했어요. 내 배치안에서 열 수 있어요.${petNote}` });
        refreshLayouts();
        return;
      }
      // 화면의 배치·되돌리기 기록은 그대로 두고 저장된 상태만 기억해요
      const m = metaOf(saved);
      setMeta(m);
      setSavedSnap(snapshotOf(m, { cage: saved.cage, items: saved.items }));
      replaceLayoutParam(saved.id);
      setNotice({ kind: "ok", text: (asNew || !openId ? "새 배치안으로 저장했어요." : "저장했어요.") + petNote });
      refreshLayouts();
    } catch (e) {
      setNotice({
        kind: "error",
        text: isAuthError(e) ? "로그인이 풀렸어요. 다시 로그인하면 이어서 저장할 수 있어요 (작업은 이 브라우저에 남아 있어요)." : e instanceof ApiError ? e.messageKo : "저장하지 못했어요.",
      });
    } finally {
      setWriting(false);
    }
  };

  const confirmDiscard = () => !dirty || window.confirm("저장하지 않은 변경이 있어요. 버리고 계속할까요?");

  const openLayout = (id: string) => {
    if (!confirmDiscard()) return;
    // 주소가 이미 이 배치안이면(불러오기에 실패했을 때 등) 주소가 바뀌지 않으니 바로 불러와요
    if (id === wantedLayout) loadLayout(id);
    else router.push(`/cage?layout=${id}`, { scroll: false });
  };

  const newLayout = () => {
    if (!confirmDiscard()) return;
    const m: Meta = { name: DEFAULT_NAME, species: meta.species, size: meta.size, petId: null, layoutId: null };
    docGen.current += 1;
    setMeta(m);
    dispatch({ type: "reset", doc: { cage: hist.present.cage, items: [] } });
    setSavedSnap(null);
    setSelectedId(null);
    setNotice(null);
    replaceLayoutParam(null);
  };

  const deleteLayout = async (l: CageLayoutSummary) => {
    if (!window.confirm(`"${l.name}" 배치안을 지울까요? 되돌릴 수 없어요.`)) return;
    setWriting(true);
    const start = placeNow();
    try {
      await api.deleteLayout(l.id);
      if (l.id === meta.layoutId && !movedSince(start)) {
        // 지금 열린 배치안을 지웠으면 화면의 배치는 저장 전 새 배치안으로 남겨요
        setMeta((m) => ({ ...m, layoutId: null }));
        setSavedSnap(null);
        replaceLayoutParam(null);
      }
      refreshLayouts();
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof ApiError ? e.messageKo : "지우지 못했어요." });
    } finally {
      setWriting(false);
    }
  };

  // ── 화면 ──

  const selected = items.find((it) => it.id === selectedId) ?? null;
  const selectedAsset = selected ? getAsset(selected.asset) : undefined;
  const selectedIssues = selected ? report.issues.filter((i) => i.itemIds.includes(selected.id)) : [];
  const needsLogin = status !== null && !user;

  return (
    <div className="space-y-4">
      {/* 상단: 이름·종·저장 */}
      <div className={`${ui.card} flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between`}>
        <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <label className="block">
            <span className={ui.label}>배치안 이름</span>
            <input
              className={ui.input}
              value={meta.name}
              maxLength={40}
              onChange={(e) => setMeta((m) => ({ ...m, name: e.target.value }))}
            />
          </label>
          <label className="block">
            <span className={ui.label}>반려동물 종·크기 (검토 기준)</span>
            <select
              className={ui.input}
              value={`${meta.species}/${meta.size}`}
              disabled={!species}
              onChange={(e) => {
                const [s, z] = e.target.value.split("/");
                setMeta((m) => ({ ...m, species: s, size: z }));
              }}
            >
              {species ? (
                species.species.flatMap((sp) =>
                  sp.sizes.map((z) => (
                    <option key={`${sp.key}/${z.key}`} value={`${sp.key}/${z.key}`}>
                      {sp.display_name} · {z.display_name}
                    </option>
                  )),
                )
              ) : (
                <option value={`${meta.species}/${meta.size}`}>불러오는 중…</option>
              )}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {dirty && <span className="text-xs text-amber-700">저장하지 않은 변경</span>}
          <button type="button" className={ui.btnSecondary} onClick={newLayout} disabled={busy}>
            새로 만들기
          </button>
          {user ? (
            <>
              {meta.layoutId && (
                <button type="button" className={ui.btnSecondary} onClick={() => void save(true)} disabled={busy}>
                  새 배치안으로 저장
                </button>
              )}
              <button type="button" className={ui.btnPrimary} onClick={() => void save(false)} disabled={busy || (!dirty && !!meta.layoutId)}>
                {busy ? "저장 중…" : "저장"}
              </button>
            </>
          ) : needsLogin ? (
            <Link href="/login?next=%2Fcage" className={ui.btnPrimary}>
              로그인하고 저장
            </Link>
          ) : null}
        </div>
      </div>

      {notice && (
        <p role={notice.kind === "error" ? "alert" : "status"} className={notice.kind === "error" ? ui.error : ui.success}>
          {notice.text}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        {/* 3D 화면 */}
        <div className="space-y-4">
          <div className="relative h-[60vh] min-h-[380px] overflow-hidden rounded-2xl border border-amber-200 bg-[#fbf7f0] shadow-sm lg:h-[620px]">
            <PlannerScene
              cage={cage}
              items={items}
              selectedId={selectedId}
              report={report}
              rules={rules}
              view={view}
              viewNonce={viewNonce}
              onSelect={setSelectedId}
              onDragStart={onDragStart}
              onDrag={onDrag}
              onDragEnd={onDragEnd}
            />
            <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
              <div className="flex overflow-hidden rounded-lg border border-stone-200 bg-white/90 text-xs shadow-sm" role="group" aria-label="시점">
                {(
                  [
                    ["3d", "3D"],
                    ["top", "위에서"],
                    ["front", "정면"],
                  ] as const
                ).map(([v, label]) => (
                  <button
                    key={v}
                    type="button"
                    aria-pressed={view === v}
                    onClick={() => {
                      setView(v);
                      setViewNonce((n) => n + 1);
                    }}
                    className={`px-2.5 py-1.5 ${view === v ? "bg-amber-100 font-semibold text-amber-900" : "text-stone-600 hover:bg-stone-50"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white/90 px-2 py-1.5 text-xs text-stone-600 shadow-sm">
                <input type="checkbox" checked={grid} onChange={(e) => setGrid(e.target.checked)} />
                1cm 격자
              </label>
              <label className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white/90 px-2 py-1.5 text-xs text-stone-600 shadow-sm">
                <input type="checkbox" checked={magnet} onChange={(e) => setMagnet(e.target.checked)} />
                벽·구조물에 붙이기
              </label>
            </div>
            <div className="absolute right-3 top-3 flex gap-1.5">
              <button
                type="button"
                className="rounded-lg border border-stone-200 bg-white/90 px-2.5 py-1.5 text-xs shadow-sm disabled:opacity-40"
                onClick={() => dispatch({ type: "undo" })}
                disabled={!hist.past.length}
                title="되돌리기 (Ctrl+Z)"
              >
                ↶ 되돌리기
              </button>
              <button
                type="button"
                className="rounded-lg border border-stone-200 bg-white/90 px-2.5 py-1.5 text-xs shadow-sm disabled:opacity-40"
                onClick={() => dispatch({ type: "redo" })}
                disabled={!hist.future.length}
                title="다시 하기 (Ctrl+Shift+Z)"
              >
                ↷ 다시 하기
              </button>
            </div>
            <div className="pointer-events-none absolute bottom-3 right-3 max-w-[calc(100%-1.5rem)] rounded-lg bg-white/85 px-3 py-2 text-right text-[11px] leading-relaxed text-stone-600 shadow-sm">
              <p className="font-semibold text-stone-800">
                케이지 {cage.width_mm}×{cage.depth_mm}×{cage.height_mm}mm · 구조물 {items.length}개
              </p>
              <p className="hidden sm:block">끌어서 옮기기 · R 90° 회전 · Q/E 15° · 방향키 1cm(Shift 1mm) · Del 삭제</p>
              <p className="sm:hidden">구조물을 끌어서 옮기고, 아래 패널에서 돌려요</p>
            </div>
          </div>

          <div className={ui.card}>
            <ReviewPanel
              report={report}
              itemCount={items.length}
              rulesLoaded={rules !== null}
              rulesReviewed={species?.rules_reviewed ?? false}
              onPick={(id) => setSelectedId(id)}
            />
          </div>
        </div>

        {/* 오른쪽: 선택한 구조물 + 카탈로그·케이지 크기·저장 목록 */}
        <aside className="space-y-4">
          {selected && selectedAsset && (
            <div className={ui.card}>
              <InspectorPanel
                item={selected}
                asset={selectedAsset}
                cage={cage}
                issues={selectedIssues}
                onMove={(x, y) => moveItem(selected.id, x, y)}
                onRotate={(d) => rotateItem(selected.id, d)}
                onRotateTo={(d) => rotateItem(selected.id, d, true)}
                onDuplicate={() => duplicateItem(selected.id)}
                onRemove={() => removeItem(selected.id)}
              />
            </div>
          )}
          <div className={ui.card}>
            <div className="mb-4 flex gap-1 rounded-xl bg-stone-100 p-1 text-sm" role="tablist" aria-label="패널">
              {(
                [
                  ["catalog", "카탈로그"],
                  ["cage", "케이지 크기"],
                  ["saved", "내 배치안"],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={tab === k}
                  onClick={() => setTab(k)}
                  className={`flex-1 rounded-lg px-2 py-1.5 ${tab === k ? "bg-white font-semibold shadow-sm" : "text-stone-600"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "catalog" && <CatalogPanel onAdd={addAsset} onStarter={addStarter} empty={items.length === 0} />}
            {tab === "cage" && (
              <CageSizePanel
                cage={cage}
                onApply={applyCage}
                pets={pets}
                onPickPet={pickPet}
                outsideCount={outsideCount}
                onPullInside={pullAllInside}
              />
            )}
            {tab === "saved" &&
              (user ? (
                <LayoutsPanel
                  layouts={layouts}
                  currentId={meta.layoutId}
                  error={layoutsError}
                  busy={busy}
                  onOpen={openLayout}
                  onDelete={(l) => void deleteLayout(l)}
                />
              ) : (
                <p className="text-sm text-stone-600">
                  <Link href="/login?next=%2Fcage" className={ui.link}>
                    로그인
                  </Link>
                  하면 배치안을 계정에 저장하고 다른 기기에서도 열 수 있어요. 지금 작업은 이 브라우저에 임시로 남아 있어요.
                </p>
              ))}
          </div>
          <div className={`${ui.cardPlain} text-sm`}>
            <p className="font-medium">배치가 마음에 드시나요?</p>
            <p className="mt-1 text-stone-600">이 케이지에 꼭 맞는 은신처·터널·램프를 AI가 설계하고 3D 프린팅 파일로 만들어 드려요.</p>
            <Link href={meta.petId ? `/design?pet=${encodeURIComponent(meta.petId)}` : "/design"} className={`${ui.link} mt-2 inline-block font-medium`}>
              AI 맞춤 설계로 이어가기 →
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}
