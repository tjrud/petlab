"use client";

import { Edges, Html, OrbitControls } from "@react-three/drei";
import { Canvas, useLoader, type ThreeEvent } from "@react-three/fiber";
import { Suspense, useMemo } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { api } from "@/lib/api";
import { TEMPLATE_COLORS } from "@/lib/templates";
import type { Cage, Item } from "@/lib/types";

type Props = {
  cage: Cage;
  items: Item[];
  selected: number | null;
  errorItems: Set<number>;
  onSelect: (index: number | null) => void;
};

/** 백엔드 메시는 케이지 좌표계(mm, Z-up, 원점=앞-왼쪽 바닥 모서리)로 온다. three.js 는 Y-up 이므로 X축 -90° 회전. */
const Z_UP_TO_Y_UP: [number, number, number] = [-Math.PI / 2, 0, 0];

function Part({
  item,
  selected,
  hasError,
  onSelect,
}: {
  item: Item;
  selected: boolean;
  hasError: boolean;
  onSelect: (i: number) => void;
}) {
  const geometry = useLoader(STLLoader, api.meshUrl(item.mesh_url!));
  useMemo(() => geometry.computeVertexNormals(), [geometry]);
  const base = hasError ? "#e05252" : (TEMPLATE_COLORS[item.template] ?? "#c8a27a");
  const p = item.placement!;
  return (
    <group>
      <mesh
        geometry={geometry}
        castShadow
        receiveShadow
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect(item.index);
        }}
      >
        <meshStandardMaterial
          color={base}
          roughness={0.75}
          metalness={0}
          emissive={selected ? "#ffb347" : "#000000"}
          emissiveIntensity={selected ? 0.35 : 0}
        />
      </mesh>
      {selected && (
        <Html position={[p.x_mm, p.y_mm, item.size_mm[2] + 15]} center zIndexRange={[10, 0]}>
          <div className="pointer-events-none whitespace-nowrap rounded-md bg-stone-900/85 px-2 py-1 text-xs text-white">
            {item.label_ko}
          </div>
        </Html>
      )}
    </group>
  );
}

function CageBox({ cage }: { cage: Cage }) {
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  const strip = Math.max(4, Math.min(W, D) * 0.012);
  return (
    <group>
      {/* 바닥 (바닥재) */}
      <mesh position={[W / 2, D / 2, 0]} receiveShadow>
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial color="#f3e6cf" roughness={1} />
      </mesh>
      {/* 앞(관찰 면) 표시: 앞쪽 바닥 모서리를 따라 주황색 띠 */}
      <mesh position={[W / 2, strip / 2, 0.5]}>
        <planeGeometry args={[W, strip]} />
        <meshBasicMaterial color="#f59e0b" />
      </mesh>
      {/* 케이지 외곽 (반투명 + 모서리선) */}
      <mesh position={[W / 2, D / 2, H / 2]}>
        <boxGeometry args={[W, D, H]} />
        <meshBasicMaterial color="#9bb7d4" transparent opacity={0.06} depthWrite={false} side={THREE.BackSide} />
        <Edges color="#6b8fb5" />
      </mesh>
    </group>
  );
}

export default function CageViewer({ cage, items, selected, errorItems, onSelect }: Props) {
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  const S = Math.max(W, D, H);
  // three.js 월드 좌표(Y-up)에서 케이지 중심: (W/2, H/2, -D/2)
  const target: [number, number, number] = [W / 2, H * 0.2, -D / 2];
  const camera = { position: [W / 2 + S * 0.4, S * 1.0, S * 1.35] as [number, number, number], fov: 40, near: 1, far: S * 20 };
  const placed = items.filter((it) => it.mesh_url && it.placement);

  return (
    <div className="relative h-full w-full">
      <div className="pointer-events-none absolute left-3 top-3 z-10 space-y-0.5 rounded-lg bg-white/85 px-3 py-2 text-xs text-stone-600 shadow-sm">
        <p className="font-semibold text-stone-800">
          케이지 내부 {W} × {D} × {H} mm
        </p>
        <p>
          <span className="mr-1 inline-block h-2 w-3 rounded-sm bg-amber-500 align-middle" />앞(관찰 면)
        </p>
      </div>
      <Canvas
        shadows="percentage"
        camera={camera}
        onPointerMissed={() => onSelect(null)}
        className="h-full w-full"
        gl={{ preserveDrawingBuffer: true }}
      >
        <color attach="background" args={["#fbf7f0"]} />
        <ambientLight intensity={0.65} />
        <directionalLight
          position={[W * 0.2, S * 1.6, S * 0.8]}
          intensity={1.5}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-left={-S}
          shadow-camera-right={S}
          shadow-camera-top={S}
          shadow-camera-bottom={-S}
        />
        <group rotation={Z_UP_TO_Y_UP}>
          <CageBox cage={cage} />
          <Suspense fallback={null}>
            {placed.map((it) => (
              <Part
                key={`${it.mesh_url}`}
                item={it}
                selected={selected === it.index}
                hasError={errorItems.has(it.index)}
                onSelect={onSelect}
              />
            ))}
          </Suspense>
        </group>
        <OrbitControls
          makeDefault
          target={target}
          maxPolarAngle={Math.PI / 2.05}
          minDistance={S * 0.3}
          maxDistance={S * 4}
        />
      </Canvas>
    </div>
  );
}
