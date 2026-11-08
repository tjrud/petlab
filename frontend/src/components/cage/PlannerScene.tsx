"use client";

// 가상 케이지 3D 화면: 바닥 격자·케이지 외곽·배치한 에셋을 그리고, 끌어서 옮기기와 선택을 처리해요.
// 케이지 좌표(mm, Z-up, 원점 = 앞-왼쪽 바닥 모서리)로 그린 뒤 X축 -90° 회전해 three.js(Y-up)에 올려요.
// 그래서 three.js 월드 좌표 (wx, wy, wz) ↔ 케이지 좌표 (x, y, z) = (wx, -wz, wy).

import { Edges, Html, OrbitControls } from "@react-three/drei";
import { Canvas, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import AssetModel from "@/components/cage/AssetModel";
import { beddingDepth, getAsset, isFloorLayer, type CageAsset } from "@/lib/cageAssets";
import { accessStrip, type LayoutReport } from "@/lib/cageLayout";
import { contactShadowTexture, fitCamera, PREVIEW_BG, viewDirection } from "@/lib/previewLook";
import type { Cage, LayoutItem, LayoutRules } from "@/lib/types";

export type CameraView = "3d" | "top" | "front";

type Props = {
  /** 3D 화면 배경색 */
  background?: string;
  cage: Cage;
  items: LayoutItem[];
  selectedId: string | null;
  report: LayoutReport;
  rules: LayoutRules | null;
  view: CameraView;
  /** 바뀌면 카메라를 다시 맞춰요 (같은 시점 버튼을 다시 눌렀을 때) */
  viewNonce: number;
  onSelect: (id: string | null) => void;
  onDragStart: (id: string) => void;
  onDrag: (id: string, x: number, y: number) => void;
  onDragEnd: (id: string) => void;
};

const Z_UP_TO_Y_UP: [number, number, number] = [-Math.PI / 2, 0, 0];
/** 끌 때 마우스가 가리키는 바닥 높이 (three.js 월드 y = 케이지 z). 바닥재를 깔면 그 윗면 */
const groundAt = (z: number) => new THREE.Plane(new THREE.Vector3(0, 1, 0), -z);
/** 3D 위에 띄운 글자가 마우스를 가로채지 않게 (구조물을 바로 잡을 수 있게) */
const NO_POINTER = { pointerEvents: "none" } as const;

type Controls = { enabled: boolean; target: THREE.Vector3; update: () => void };

/** 시점별 카메라 방향 (Y-up, 케이지 앞쪽이 +Z) */
const VIEW_DIR: Record<CameraView, () => THREE.Vector3> = {
  "3d": () => viewDirection(34, 24),
  top: () => new THREE.Vector3(0, 1, 0.002).normalize(), // 위에서 (화면 위쪽이 케이지 뒤)
  front: () => viewDirection(14, 0),
};
/** 케이지가 화면(가로·세로 중 좁은 쪽)에서 차지하는 비율. 위쪽 도구 모음·치수 글자 자리를 남긴다 */
const CAGE_FILL = 0.84;

/** 케이지 전체(외곽 상자)가 화면에 들어오도록 카메라를 맞춰요. 화면 비율까지 따지므로 모바일 세로 화면에서도
 * 좌우가 잘리지 않아요. 시점·케이지 크기·화면 크기가 바뀔 때, 같은 시점 버튼을 다시 눌렀을 때 다시 맞춰요 */
function CameraRig({ cage, view, nonce }: { cage: Cage; view: CameraView; nonce: number }) {
  const getState = useThree((s) => s.get);
  // 컨트롤이 준비되면(makeDefault) 다시 맞추려고 구독만 해요. 값은 효과 안에서 getState() 로 읽어요
  const controlsReady = useThree((s) => s.controls !== null);
  const size = useThree((s) => s.size);
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  useEffect(() => {
    const camera = getState().camera as THREE.PerspectiveCamera;
    const controls = getState().controls as unknown as Controls | null;
    if (size.width === 0 || size.height === 0) return;
    camera.aspect = size.width / size.height;
    // 케이지 외곽 상자의 꼭짓점 (three.js 월드: 가로 x, 높이 y, 깊이 -z)
    const corners: THREE.Vector3[] = [];
    for (const x of [0, W]) for (const y of [0, H]) for (const z of [0, -D]) corners.push(new THREE.Vector3(x, y, z));
    const target = fitCamera(camera, corners, CAGE_FILL, VIEW_DIR[view]());
    camera.far = Math.max(W, D, H) * 20;
    camera.updateProjectionMatrix();
    if (controls) {
      controls.target.copy(target);
      controls.update();
    } else {
      camera.lookAt(target);
    }
  }, [getState, controlsReady, size.width, size.height, W, D, H, view, nonce]);
  return null;
}

function FloorGrid({ cage, z }: { cage: Cage; z: number }) {
  const { width_mm: W, depth_mm: D } = cage;
  const [minor, major] = useMemo(() => {
    const mk = (step: number, skip?: number) => {
      const pts: number[] = [];
      const h = z + 0.3;
      for (let x = step; x < W; x += step) if (!skip || x % skip !== 0) pts.push(x, 0, h, x, D, h);
      for (let y = step; y < D; y += step) if (!skip || y % skip !== 0) pts.push(0, y, h, W, y, h);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      return g;
    };
    return [mk(50, 100), mk(100)];
  }, [W, D, z]);
  return (
    <group>
      {/* 옅게: 재기 위한 보조선이라 구조물보다 눈에 띄지 않게 */}
      <lineSegments geometry={minor}>
        <lineBasicMaterial color="#e9e4da" />
      </lineSegments>
      <lineSegments geometry={major}>
        <lineBasicMaterial color="#d9d1c2" />
      </lineSegments>
    </group>
  );
}

function CageShell({ cage, floorZ }: { cage: Cage; floorZ: number }) {
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  // 3D 위 글자(Html)는 이벤트 대상이 연결된 뒤에 붙여요. 먼저 붙이면 대상이 바뀌며 글자가 지워져요
  const labelsReady = useThree((s) => Boolean(s.events.connected));
  const strip = Math.max(4, Math.min(W, D) * 0.012);
  return (
    <group>
      <mesh position={[W / 2, D / 2, 0]} receiveShadow>
        <planeGeometry args={[W, D]} />
        {/* 밝은 종이색 바닥: 쿨그레이 배경과 구분되고, 나무색 구조물이 또렷하게 */}
        <meshStandardMaterial color="#fbf8f2" roughness={1} />
      </mesh>
      <FloorGrid cage={cage} z={floorZ} />
      {/* 앞(관찰 면) 표시 */}
      <mesh position={[W / 2, strip / 2, floorZ + 0.6]}>
        <planeGeometry args={[W, strip]} />
        <meshBasicMaterial color="#f59e0b" />
      </mesh>
      <mesh position={[W / 2, D / 2, H / 2]}>
        <boxGeometry args={[W, D, H]} />
        <meshBasicMaterial color="#9bb7d4" transparent opacity={0.05} depthWrite={false} side={THREE.BackSide} />
        <Edges color="#6b8fb5" />
      </mesh>
      {labelsReady && (
        <>
          <Html style={NO_POINTER} position={[W / 2, -Math.min(W, D) * 0.06, 0]} center zIndexRange={[5, 0]}>
            <span className="pointer-events-none whitespace-nowrap rounded bg-white/85 px-1.5 py-0.5 text-[11px] text-stone-600 shadow-sm">
              가로 {Math.round(W)}mm · 앞
            </span>
          </Html>
          <Html style={NO_POINTER} position={[-Math.min(W, D) * 0.06, D / 2, 0]} center zIndexRange={[5, 0]}>
            <span className="pointer-events-none whitespace-nowrap rounded bg-white/85 px-1.5 py-0.5 text-[11px] text-stone-600 shadow-sm">
              세로 {Math.round(D)}mm
            </span>
          </Html>
        </>
      )}
    </group>
  );
}

/** 0~1 사이 결정적 난수 (바닥재 조각 위치가 그릴 때마다 바뀌지 않게) */
function seeded(seed: number) {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

/** 바닥재: 바닥 전체를 깊이만큼 채우고, 윗면에 톱밥·종이 조각을 흩뿌려요. 마우스는 통과해요 */
function Bedding({ cage, asset }: { cage: Cage; asset: CageAsset }) {
  const { width_mm: W, depth_mm: D } = cage;
  const depth = asset.size[2];
  const count = Math.min(5000, Math.round((W * D) / 250));
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const rnd = seeded(W * 7919 + D * 104729 + depth);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const e = new THREE.Euler();
    const sc = new THREE.Vector3();
    for (let i = 0; i < count; i++) {
      e.set((rnd() - 0.5) * 0.6, (rnd() - 0.5) * 0.6, rnd() * Math.PI);
      q.setFromEuler(e);
      const k = 0.6 + rnd() * 0.9;
      sc.set(k, k, 1);
      m.compose(new THREE.Vector3(rnd() * W, rnd() * D, depth + 0.4 + rnd() * 1.2), q, sc);
      mesh.setMatrixAt(i, m);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }, [W, D, depth, count]);
  const none = () => null;
  return (
    <group>
      <mesh position={[W / 2, D / 2, depth / 2]} receiveShadow raycast={none}>
        <boxGeometry args={[W, D, depth]} />
        <meshStandardMaterial color={asset.color} roughness={1} />
      </mesh>
      <instancedMesh key={count} ref={ref} args={[undefined, undefined, count]} raycast={none} receiveShadow>
        <boxGeometry args={[9, 4, 1.2]} />
        <meshStandardMaterial color={asset.floorLayer?.flakeColor ?? asset.color} roughness={1} />
      </instancedMesh>
    </group>
  );
}

/** 구조물이 바닥에 닿는 곳의 흐린 그림자 (주광 그림자가 다른 쪽으로 떨어져도 바닥에 놓여 보이게) */
function ContactBlob({ asset }: { asset: CageAsset }) {
  const [w, d] = asset.size;
  const map = useMemo(() => contactShadowTexture(), []);
  return (
    <mesh position={[0, 0, 0.5]} raycast={() => null}>
      <planeGeometry args={[w * 1.3, d * 1.3]} />
      <meshBasicMaterial map={map} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

function Footprint({ asset, color, opacity }: { asset: CageAsset; color: string; opacity: number }) {
  const [w, d] = asset.size;
  return (
    <mesh position={[0, 0, 0.8]}>
      <planeGeometry args={[w, d]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} />
    </mesh>
  );
}

function PlacedItem({
  floorZ,
  item,
  asset,
  selected,
  state,
  onSelect,
  onDragStart,
  onDrag,
  onDragEnd,
}: {
  floorZ: number;
  item: LayoutItem;
  asset: CageAsset;
  selected: boolean;
  state: "ok" | "warning" | "error";
  onSelect: (id: string) => void;
  onDragStart: (id: string) => void;
  onDrag: (id: string, x: number, y: number) => void;
  onDragEnd: (id: string) => void;
}) {
  // 끄는 동안 시점 회전을 잠가요 (이벤트 때 현재 컨트롤을 읽는다)
  const getState = useThree((s) => s.get);
  const setOrbit = (enabled: boolean) => {
    const c = getState().controls as unknown as Controls | null;
    if (c) c.enabled = enabled;
  };
  const drag = useRef<{ dx: number; dy: number; pointerId: number } | null>(null);
  const [hover, setHover] = useState(false);
  const hit = useMemo(() => new THREE.Vector3(), []);

  // 커서 모양은 이벤트에서만 바꾸고, 화면에서 사라질 때 되돌려요
  useEffect(
    () => () => {
      document.body.style.cursor = "";
    },
    [],
  );

  const ground = useMemo(() => groundAt(floorZ), [floorZ]);
  const groundPoint = (e: ThreeEvent<PointerEvent>) => (e.ray.intersectPlane(ground, hit) ? { x: hit.x, y: -hit.z } : null);

  const footColor = state === "error" ? "#ef4444" : state === "warning" ? "#f59e0b" : selected ? "#f59e0b" : "#a8a29e";
  const footOpacity = state === "error" ? 0.45 : state === "warning" ? 0.3 : selected ? 0.3 : 0.15;

  return (
    <group
      position={[item.x_mm, item.y_mm, floorZ]}
      rotation={[0, 0, (item.rotation_deg * Math.PI) / 180]}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHover(true);
        if (!drag.current) document.body.style.cursor = "grab";
      }}
      onPointerOut={() => {
        setHover(false);
        if (!drag.current) document.body.style.cursor = "";
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        onSelect(item.id);
        const p = groundPoint(e);
        if (!p) return;
        (e.target as Element).setPointerCapture(e.pointerId);
        drag.current = { dx: item.x_mm - p.x, dy: item.y_mm - p.y, pointerId: e.pointerId };
        setOrbit(false);
        document.body.style.cursor = "grabbing";
        onDragStart(item.id);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d || e.pointerId !== d.pointerId) return;
        e.stopPropagation();
        const p = groundPoint(e);
        if (p) onDrag(item.id, p.x + d.dx, p.y + d.dy);
      }}
      onPointerUp={(e) => {
        const d = drag.current;
        if (!d || e.pointerId !== d.pointerId) return;
        e.stopPropagation();
        (e.target as Element).releasePointerCapture(e.pointerId);
        drag.current = null;
        setOrbit(true);
        document.body.style.cursor = "";
        onDragEnd(item.id);
      }}
    >
      <ContactBlob asset={asset} />
      <Footprint asset={asset} color={footColor} opacity={footOpacity} />
      <AssetModel asset={asset} highlight={selected ? "selected" : hover ? "hover" : "none"} />
      {selected && (
        <Html style={NO_POINTER} position={[0, 0, asset.size[2] + 18]} center zIndexRange={[10, 0]}>
          <div className="pointer-events-none whitespace-nowrap rounded-md bg-stone-900/85 px-2 py-1 text-xs text-white">
            {asset.name}
          </div>
        </Html>
      )}
    </group>
  );
}

/** 선택한 에셋의 출입구 앞 공간 (비어 있어야 하는 자리) */
function AccessStrips({ item, asset, depth }: { item: LayoutItem; asset: CageAsset; depth: number }) {
  const geos = useMemo(
    () =>
      (asset.accessSides ?? []).map((side) => {
        const poly = accessStrip(item, asset, side, depth);
        const shape = new THREE.Shape(poly.map((p) => new THREE.Vector2(p.x, p.y)));
        return new THREE.ShapeGeometry(shape);
      }),
    [item, asset, depth],
  );
  return (
    <group position={[0, 0, 1]}>
      {geos.map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshBasicMaterial color="#10b981" transparent opacity={0.25} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

export default function PlannerScene({
  background = PREVIEW_BG,
  cage,
  items,
  selectedId,
  report,
  rules,
  view,
  viewNonce,
  onSelect,
  onDragStart,
  onDrag,
  onDragEnd,
}: Props) {
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  const S = Math.max(W, D, H);
  const selected = items.find((i) => i.id === selectedId) ?? null;
  const selectedAsset = selected ? getAsset(selected.asset) : undefined;
  // 바닥재는 바닥 전체에 깔고, 다른 구조물은 그 위에 놓아요
  const floorZ = beddingDepth(items);
  const bedding = items.map((it) => getAsset(it.asset)).find(isFloorLayer);
  // 주광은 케이지 가운데를 향해 왼쪽 앞 위에서 (카메라는 오른쪽 앞). 그림자가 보이는 쪽 바닥에 떨어져요
  const lightTarget = useMemo(() => new THREE.Object3D(), []);
  const center: [number, number, number] = [W / 2, 0, -D / 2];

  return (
    <Canvas
      shadows="percentage"
      camera={{ position: [W / 2 + S * 0.45, S * 0.95, S * 1.15], fov: 40, near: 1, far: S * 20 }}
      onPointerMissed={(e) => {
        if (e.button === 0) onSelect(null);
      }}
      className="h-full w-full touch-none"
      gl={{ preserveDrawingBuffer: true }}
    >
      <color attach="background" args={[background]} />
      {/* 환경광 + 주광(부드러운 그림자) + 보조광 + 역광: 면마다 밝기가 달라 형태가 살고, 안쪽 면이 까맣게 죽지 않게 */}
      <hemisphereLight args={["#ffffff", "#d9c9b4", 1.0]} />
      <ambientLight intensity={0.22} />
      <primitive object={lightTarget} position={center} />
      <directionalLight
        position={[W / 2 - S * 0.9, S * 1.6, -D / 2 + S * 0.9]}
        target={lightTarget}
        intensity={2.0}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={S * 0.002}
        shadow-radius={5}
        shadow-camera-left={-S * 0.9}
        shadow-camera-right={S * 0.9}
        shadow-camera-top={S * 0.9}
        shadow-camera-bottom={-S * 0.9}
        shadow-camera-near={S * 0.1}
        shadow-camera-far={S * 4}
      />
      <directionalLight position={[W / 2 + S * 1.4, S * 0.7, -D / 2 + S * 0.6]} intensity={0.5} />
      <directionalLight position={[W / 2 + S * 0.3, S * 1.0, -D / 2 - S * 1.6]} intensity={0.6} />
      <group rotation={Z_UP_TO_Y_UP}>
        <CageShell cage={cage} floorZ={floorZ} />
        {bedding && <Bedding cage={cage} asset={bedding} />}
        {items.map((it) => {
          const asset = getAsset(it.asset);
          if (!asset || isFloorLayer(asset)) return null;
          const state = report.errorIds.has(it.id) ? "error" : report.warningIds.has(it.id) ? "warning" : "ok";
          return (
            <PlacedItem
              key={it.id}
              floorZ={floorZ}
              item={it}
              asset={asset}
              selected={it.id === selectedId}
              state={state}
              onSelect={onSelect}
              onDragStart={onDragStart}
              onDrag={onDrag}
              onDragEnd={onDragEnd}
            />
          );
        })}
        {selected && selectedAsset && rules && !isFloorLayer(selectedAsset) && (
          <group position={[0, 0, floorZ]}>
            <AccessStrips item={selected} asset={selectedAsset} depth={rules.gap_passable_min_mm} />
          </group>
        )}
      </group>
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.05} minDistance={S * 0.25} maxDistance={S * 4} />
      <CameraRig cage={cage} view={view} nonce={viewNonce} />
    </Canvas>
  );
}
