"use client";

// 가상 케이지 3D 화면: 바닥 격자·케이지 외곽·배치한 에셋을 그리고, 끌어서 옮기기와 선택을 처리해요.
// 케이지 좌표(mm, Z-up, 원점 = 앞-왼쪽 바닥 모서리)로 그린 뒤 X축 -90° 회전해 three.js(Y-up)에 올려요.
// 그래서 three.js 월드 좌표 (wx, wy, wz) ↔ 케이지 좌표 (x, y, z) = (wx, -wz, wy).

import { Edges, Html, OrbitControls } from "@react-three/drei";
import { Canvas, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import AssetModel from "@/components/cage/AssetModel";
import { getAsset, type CageAsset } from "@/lib/cageAssets";
import { accessStrip, type LayoutReport } from "@/lib/cageLayout";
import type { Cage, LayoutItem, LayoutRules } from "@/lib/types";

export type CameraView = "3d" | "top" | "front";

type Props = {
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
const GROUND = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
/** 3D 위에 띄운 글자가 마우스를 가로채지 않게 (구조물을 바로 잡을 수 있게) */
const NO_POINTER = { pointerEvents: "none" } as const;

type Controls = { enabled: boolean; target: THREE.Vector3; update: () => void };

function CameraRig({ cage, view, nonce }: { cage: Cage; view: CameraView; nonce: number }) {
  const getState = useThree((s) => s.get);
  // 컨트롤이 준비되면(makeDefault) 다시 맞추려고 구독만 해요. 값은 효과 안에서 getState() 로 읽어요
  const controlsReady = useThree((s) => s.controls !== null);
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  useEffect(() => {
    const { camera } = getState();
    const controls = getState().controls as unknown as Controls | null;
    const S = Math.max(W, D, H);
    const target = new THREE.Vector3(W / 2, view === "top" ? 0 : H * 0.15, -D / 2);
    if (view === "top") camera.position.set(W / 2, S * 1.55, -D / 2 + 0.01);
    else if (view === "front") camera.position.set(W / 2, H * 0.55, S * 1.25);
    else camera.position.set(W / 2 + S * 0.45, S * 0.95, S * 1.15);
    camera.far = S * 20;
    camera.updateProjectionMatrix();
    if (controls) {
      controls.target.copy(target);
      controls.update();
    } else {
      camera.lookAt(target);
    }
  }, [getState, controlsReady, W, D, H, view, nonce]);
  return null;
}

function FloorGrid({ cage }: { cage: Cage }) {
  const { width_mm: W, depth_mm: D } = cage;
  const [minor, major] = useMemo(() => {
    const mk = (step: number, skip?: number) => {
      const pts: number[] = [];
      for (let x = step; x < W; x += step) if (!skip || x % skip !== 0) pts.push(x, 0, 0.3, x, D, 0.3);
      for (let y = step; y < D; y += step) if (!skip || y % skip !== 0) pts.push(0, y, 0.3, W, y, 0.3);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      return g;
    };
    return [mk(50, 100), mk(100)];
  }, [W, D]);
  return (
    <group>
      <lineSegments geometry={minor}>
        <lineBasicMaterial color="#eadfca" />
      </lineSegments>
      <lineSegments geometry={major}>
        <lineBasicMaterial color="#d5c19c" />
      </lineSegments>
    </group>
  );
}

function CageShell({ cage }: { cage: Cage }) {
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  // 3D 위 글자(Html)는 이벤트 대상이 연결된 뒤에 붙여요. 먼저 붙이면 대상이 바뀌며 글자가 지워져요
  const labelsReady = useThree((s) => Boolean(s.events.connected));
  const strip = Math.max(4, Math.min(W, D) * 0.012);
  return (
    <group>
      <mesh position={[W / 2, D / 2, 0]} receiveShadow>
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial color="#f6ead3" roughness={1} />
      </mesh>
      <FloorGrid cage={cage} />
      {/* 앞(관찰 면) 표시 */}
      <mesh position={[W / 2, strip / 2, 0.6]}>
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
  item,
  asset,
  selected,
  state,
  onSelect,
  onDragStart,
  onDrag,
  onDragEnd,
}: {
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

  const groundPoint = (e: ThreeEvent<PointerEvent>) => (e.ray.intersectPlane(GROUND, hit) ? { x: hit.x, y: -hit.z } : null);

  const footColor = state === "error" ? "#ef4444" : state === "warning" ? "#f59e0b" : selected ? "#f59e0b" : "#a8a29e";
  const footOpacity = state === "error" ? 0.45 : state === "warning" ? 0.3 : selected ? 0.3 : 0.15;

  return (
    <group
      position={[item.x_mm, item.y_mm, 0]}
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
      <color attach="background" args={["#fbf7f0"]} />
      <ambientLight intensity={0.7} />
      <directionalLight
        position={[W * 0.2, S * 1.6, S * 0.8]}
        intensity={1.4}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-S}
        shadow-camera-right={S * 2}
        shadow-camera-top={S}
        shadow-camera-bottom={-S * 2}
      />
      <group rotation={Z_UP_TO_Y_UP}>
        <CageShell cage={cage} />
        {items.map((it) => {
          const asset = getAsset(it.asset);
          if (!asset) return null;
          const state = report.errorIds.has(it.id) ? "error" : report.warningIds.has(it.id) ? "warning" : "ok";
          return (
            <PlacedItem
              key={it.id}
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
        {selected && selectedAsset && rules && (
          <AccessStrips item={selected} asset={selectedAsset} depth={rules.gap_passable_min_mm} />
        )}
      </group>
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.05} minDistance={S * 0.25} maxDistance={S * 4} />
      <CameraRig cage={cage} view={view} nonce={viewNonce} />
    </Canvas>
  );
}
