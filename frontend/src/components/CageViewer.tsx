"use client";

import { Edges, Html, OrbitControls } from "@react-three/drei";
import { Canvas, useLoader, type ThreeEvent } from "@react-three/fiber";
import { Component, Suspense, useMemo, useState, type ReactNode } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { useT } from "@/i18n/client";
import { api } from "@/lib/api";
import { TEMPLATE_COLORS } from "@/lib/templates";
import type { Cage, HabitatKind, Item } from "@/lib/types";

type Props = {
  cage: Cage;
  /** 사육 환경 종류 (어항이면 높이가 물 깊이). 없으면 케이지 */
  kind?: HabitatKind;
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
  // 관리자 세션 쿠키를 함께 보낸다 (같은 출처면 기본 전송, 로컬 개발처럼 출처가 다를 때를 위해 명시)
  const geometry = useLoader(STLLoader, api.meshUrl(item.mesh_url!), (loader) => loader.setWithCredentials(true));
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

/**
 * 구조물 메시를 받지 못하면(서버가 409 로 막음·네트워크 오류) 그 구조물만 빼고 그린다.
 * 없으면 useLoader 가 던진 오류가 화면 전체를 멈춘다.
 */
class MeshErrorBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function CageBox({ cage, kind }: { cage: Cage; kind: HabitatKind }) {
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
      {kind === "aquarium" ? (
        <>
          {/* 물 (바닥재 위~수면, 반투명 + 모서리선). 높이가 물 깊이다.
              밑면을 바닥 그림과 같은 높이에 두면 두 면이 번갈아 비쳐(z-fighting) 얼룩이 지므로 1mm 띄운다 */}
          <mesh position={[W / 2, D / 2, (H + 1) / 2]}>
            <boxGeometry args={[W, D, H - 1]} />
            <meshBasicMaterial color="#4fa3d9" transparent opacity={0.08} depthWrite={false} side={THREE.BackSide} />
            <Edges color="#3a86bd" />
          </mesh>
          {/* 수면 */}
          <mesh position={[W / 2, D / 2, H]}>
            <planeGeometry args={[W, D]} />
            <meshBasicMaterial color="#7cc4ec" transparent opacity={0.16} depthWrite={false} side={THREE.DoubleSide} />
          </mesh>
        </>
      ) : (
        /* 케이지 외곽 (반투명 + 모서리선) */
        <mesh position={[W / 2, D / 2, H / 2]}>
          <boxGeometry args={[W, D, H]} />
          <meshBasicMaterial color="#9bb7d4" transparent opacity={0.06} depthWrite={false} side={THREE.BackSide} />
          <Edges color="#6b8fb5" />
        </mesh>
      )}
    </group>
  );
}

export default function CageViewer({ cage, kind = "cage", items, selected, errorItems, onSelect }: Props) {
  const t = useT();
  const { width_mm: W, depth_mm: D, height_mm: H } = cage;
  const S = Math.max(W, D, H);
  // three.js 월드 좌표(Y-up)에서 케이지 중심: (W/2, H/2, -D/2)
  const target: [number, number, number] = [W / 2, H * 0.2, -D / 2];
  const camera = { position: [W / 2 + S * 0.4, S * 1.0, S * 1.35] as [number, number, number], fov: 40, near: 1, far: S * 20 };
  const placed = items.filter((it) => it.mesh_url && it.placement);
  // 메시를 받지 못한 구성(버전·구조물 목록)을 기억한다. 다른 버전으로 바꾸면 안내가 사라진다
  const meshesKey = placed.map((it) => it.mesh_url).join("|");
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const meshFailed = failedKey === meshesKey;

  return (
    <div className="relative h-full w-full">
      <div className="pointer-events-none absolute left-3 top-3 z-10 space-y-0.5 rounded-lg bg-white/85 px-3 py-2 text-xs text-stone-600 shadow-sm">
        <p className="font-semibold text-stone-800">
          {kind === "aquarium"
            ? t("수조 {w} × {d} mm · 물 깊이 {h} mm", { w: W, d: D, h: H })
            : t("케이지 내부 {w} × {d} × {h} mm", { w: W, d: D, h: H })}
        </p>
        <p>
          <span className="mr-1 inline-block h-2 w-3 rounded-sm bg-amber-500 align-middle" />
          {t("앞(관찰 면)")}
        </p>
        {kind === "aquarium" && (
          <p>
            <span className="mr-1 inline-block h-2 w-3 rounded-sm bg-sky-300 align-middle" />
            {t("물 (바닥재 위~수면)")}
          </p>
        )}
      </div>
      {meshFailed && (
        <p
          role="status"
          className="absolute inset-x-3 bottom-3 z-10 rounded-lg bg-red-50/95 px-3 py-2 text-xs text-red-700 shadow-sm"
        >
          {t(
            "일부 구조물의 3D 형상을 불러오지 못했어요. 이 버전을 만든 뒤 서비스가 바뀌어 형상을 다시 확인하지 못했을 수 있어요. 같은 요청으로 새 버전을 만들어 주세요.",
          )}
        </p>
      )}
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
          <CageBox cage={cage} kind={kind} />
          {placed.map((it) => (
            <MeshErrorBoundary key={`${it.mesh_url}`} onError={() => setFailedKey(meshesKey)}>
              <Suspense fallback={null}>
                <Part item={it} selected={selected === it.index} hasError={errorItems.has(it.index)} onSelect={onSelect} />
              </Suspense>
            </MeshErrorBoundary>
          ))}
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
