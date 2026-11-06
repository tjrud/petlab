"use client";

// 기본 에셋의 3D 모양 (단순 도형 조합). 모두 에셋 로컬 좌표(mm, Z-up, 바닥 중심 원점, 앞 = -Y)로 그려요.
// 크기는 카탈로그(lib/cageAssets.ts)의 [가로, 세로, 높이] 안에 들어가게 맞춰요.

import { RoundedBox } from "@react-three/drei";
import { useLoader } from "@react-three/fiber";
import { Component, Suspense, useMemo, type ReactNode } from "react";
import * as THREE from "three";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import type { CageAsset } from "@/lib/cageAssets";

type MatProps = { color: string; emissive: string; emissiveIntensity: number };

function Mat({ color, emissive, emissiveIntensity, ...rest }: MatProps & { side?: THREE.Side; opacity?: number }) {
  return (
    <meshStandardMaterial
      color={color}
      roughness={0.8}
      metalness={0}
      emissive={emissive}
      emissiveIntensity={emissiveIntensity}
      side={rest.side ?? THREE.FrontSide}
      transparent={rest.opacity !== undefined}
      opacity={rest.opacity ?? 1}
    />
  );
}

/** 단면(profile: [u, z] 점들)을 축 방향으로 길이만큼 늘린 각기둥. 지붕·경사로에 써요 */
function usePrism(profile: [number, number][], length: number, axis: "x" | "y") {
  // 점 배열은 그릴 때마다 새로 만들어지므로 값(문자열)으로 비교해요
  const key = JSON.stringify(profile);
  return useMemo(() => {
    const pts = JSON.parse(key) as [number, number][];
    const shape = new THREE.Shape(pts.map(([u, v]) => new THREE.Vector2(u, v)));
    const g = new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false });
    const m = new THREE.Matrix4();
    // 단면의 (u, v) 와 늘리는 방향(geometry z)을 에셋 좌표로 옮겨요
    if (axis === "x") m.set(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1);
    else m.set(1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1);
    g.applyMatrix4(m);
    g.translate(axis === "x" ? -length / 2 : 0, axis === "y" ? -length / 2 : 0, 0);
    g.computeVertexNormals();
    return g;
  }, [key, length, axis]);
}

const DARK = "#3b2a1c";

function Doorway({ y, width, height, x = 0 }: { y: number; width: number; height: number; x?: number }) {
  return (
    <group position={[x, y, 0]}>
      <mesh position={[0, 0, height / 2 - width / 4]}>
        <boxGeometry args={[width, 3, height - width / 2]} />
        <meshStandardMaterial color={DARK} roughness={1} />
      </mesh>
      {/* 아치 윗부분 */}
      {/* 원기둥 축(Y)이 앞뒤 방향이라 원판이 앞면에 선다. 위쪽 반원만 (x = r·sinθ, z = r·cosθ ≥ 0) */}
      <mesh position={[0, 0, height - width / 2]}>
        <cylinderGeometry args={[width / 2, width / 2, 3, 24, 1, false, -Math.PI / 2, Math.PI]} />
        <meshStandardMaterial color={DARK} roughness={1} />
      </mesh>
    </group>
  );
}

function House({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const wallH = h * 0.62;
  const roof = usePrism(
    [
      [-d / 2 - 8, wallH],
      [d / 2 + 8, wallH],
      [0, h],
    ],
    w + 12,
    "x",
  );
  const e = asset.entranceMm ?? 70;
  return (
    <group>
      <mesh position={[0, 0, wallH / 2]} castShadow receiveShadow>
        <boxGeometry args={[w, d, wallH]} />
        <Mat {...m} />
      </mesh>
      <mesh geometry={roof} castShadow>
        <Mat {...m} color="#8a5a33" side={THREE.DoubleSide} />
      </mesh>
      <Doorway y={-d / 2 - 1} width={e} height={Math.min(wallH - 6, e * 1.05)} />
    </group>
  );
}

function MultiRoom({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const e = asset.entranceMm ?? 70;
  return (
    <group>
      <mesh position={[0, 0, (h - 12) / 2]} castShadow receiveShadow>
        <boxGeometry args={[w, d, h - 12]} />
        <Mat {...m} />
      </mesh>
      <mesh position={[0, 0, h - 6]} castShadow>
        <boxGeometry args={[w, d, 12]} />
        <Mat {...m} color="#8a5a33" />
      </mesh>
      <Doorway y={-d / 2 - 1} x={-w / 4} width={e} height={Math.min(h - 30, e * 1.05)} />
      <Doorway y={-d / 2 - 1} x={w / 4} width={e * 0.8} height={Math.min(h - 30, e * 0.9)} />
    </group>
  );
}

function CornerHouse({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const wallH = h * 0.6;
  const r = (Math.max(w, d) / 2) * Math.SQRT2;
  const e = asset.entranceMm ?? 70;
  return (
    <group>
      <mesh position={[0, 0, wallH / 2]} castShadow receiveShadow>
        <boxGeometry args={[w, d, wallH]} />
        <Mat {...m} />
      </mesh>
      <mesh position={[0, 0, wallH + (h - wallH) / 2]} rotation={[Math.PI / 2, Math.PI / 4, 0]} scale={[w / Math.max(w, d), 1, d / Math.max(w, d)]} castShadow>
        <coneGeometry args={[r, h - wallH, 4]} />
        <Mat {...m} color="#9a6a3f" />
      </mesh>
      <Doorway y={-d / 2 - 1} width={e} height={Math.min(wallH - 6, e)} />
    </group>
  );
}

function LogArch({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  return (
    <mesh scale={[1, 1, h / (w / 2)]} castShadow receiveShadow>
      <cylinderGeometry args={[w / 2, w / 2, d, 32, 1, true, -Math.PI / 2, Math.PI]} />
      <Mat {...m} side={THREE.DoubleSide} />
    </mesh>
  );
}

function Tunnel({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const r = Math.min(d, h) / 2;
  return (
    <group>
      <mesh position={[0, 0, r]} rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
        <cylinderGeometry args={[r, r, w, 32, 1, true]} />
        <Mat {...m} side={THREE.DoubleSide} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[(s * w) / 2, 0, r]} rotation={[0, Math.PI / 2, 0]}>
          <torusGeometry args={[r - 2, 4, 8, 32]} />
          <Mat {...m} color="#5d8aa3" />
        </mesh>
      ))}
    </group>
  );
}

function Wheel({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const R = (h - 40) / 2;
  const depth = d * 0.55;
  return (
    <group>
      <mesh position={[0, 0, 6]} receiveShadow castShadow>
        <boxGeometry args={[w, d, 12]} />
        <Mat {...m} color="#d6d3d1" />
      </mesh>
      <mesh position={[0, d / 2 - 14, (30 + R) / 2 + 6]} castShadow>
        <boxGeometry args={[24, 18, 30 + R]} />
        <Mat {...m} color="#a8a29e" />
      </mesh>
      <mesh position={[0, -d * 0.08, 30 + R]} castShadow>
        <cylinderGeometry args={[R, R, depth, 48, 1, true]} />
        <Mat {...m} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0, -d * 0.08 + depth / 2, 30 + R]} rotation={[Math.PI / 2, 0, 0]}>
        <circleGeometry args={[R, 48]} />
        <Mat {...m} color="#e7f3ef" side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function Platform({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const leg = 16;
  return (
    <group>
      <mesh position={[0, 0, h - 7]} castShadow receiveShadow>
        <boxGeometry args={[w, d, 14]} />
        <Mat {...m} />
      </mesh>
      {[
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1],
      ].map(([sx, sy]) => (
        <mesh key={`${sx}${sy}`} position={[sx * (w / 2 - leg / 2 - 6), sy * (d / 2 - leg / 2 - 6), (h - 14) / 2]} castShadow>
          <boxGeometry args={[leg, leg, h - 14]} />
          <Mat {...m} color="#8f74b0" />
        </mesh>
      ))}
    </group>
  );
}

function Ramp({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const geo = usePrism(
    [
      [-w / 2, 0],
      [w / 2, 0],
      [w / 2, h],
    ],
    d,
    "y",
  );
  return (
    <mesh geometry={geo} castShadow receiveShadow>
      <Mat {...m} side={THREE.DoubleSide} />
    </mesh>
  );
}

function Bridge({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const n = 9;
  const pw = w / n;
  const zAt = (x: number) => Math.max(0, (h - 10) * Math.cos((x / w) * Math.PI));
  return (
    <group>
      {Array.from({ length: n }, (_, i) => {
        const x = -w / 2 + pw * (i + 0.5);
        const slope = Math.atan2(zAt(x + 1) - zAt(x - 1), 2);
        return (
          <mesh key={i} position={[x, 0, zAt(x) + 5]} rotation={[0, -slope, 0]} castShadow receiveShadow>
            <boxGeometry args={[pw * 0.82, d, 10]} />
            <Mat {...m} />
          </mesh>
        );
      })}
    </group>
  );
}

function Stone({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  return (
    <RoundedBox args={[w, d, h]} radius={Math.min(18, h / 2 - 1)} position={[0, 0, h / 2]} castShadow receiveShadow>
      <Mat {...m} />
    </RoundedBox>
  );
}

function Tray({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const t = 8;
  const fill = asset.key === "sand_bath" ? "#f5e6b8" : "#d8c3a0";
  // 앞쪽 벽은 턱 높이만큼 낮춰요 (넘어 들어가는 곳)
  const frontH = Math.min(h, asset.stepHeightMm ?? h);
  return (
    <group>
      <mesh position={[0, 0, t / 2]} receiveShadow>
        <boxGeometry args={[w, d, t]} />
        <Mat {...m} />
      </mesh>
      <mesh position={[0, d / 2 - t / 2, h / 2]} castShadow>
        <boxGeometry args={[w, t, h]} />
        <Mat {...m} />
      </mesh>
      <mesh position={[0, -d / 2 + t / 2, frontH / 2]} castShadow>
        <boxGeometry args={[w, t, frontH]} />
        <Mat {...m} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[(s * (w - t)) / 2, 0, h / 2]} castShadow>
          <boxGeometry args={[t, d, h]} />
          <Mat {...m} />
        </mesh>
      ))}
      <mesh position={[0, 0, Math.min(frontH, h) * 0.8]}>
        <boxGeometry args={[w - 2 * t, d - 2 * t, 2]} />
        <meshStandardMaterial color={fill} roughness={1} />
      </mesh>
    </group>
  );
}

function Bowl({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, , h] = asset.size;
  return (
    <group>
      <mesh position={[0, 0, h / 2]} rotation={[Math.PI / 2, 0, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[w / 2, w / 2 - 10, h, 32]} />
        <Mat {...m} />
      </mesh>
      <mesh position={[0, 0, h - 6]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[w / 2 - 8, w / 2 - 8, 2, 32]} />
        <meshStandardMaterial color="#b9894f" roughness={1} />
      </mesh>
    </group>
  );
}

function WaterStand({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  const r = w * 0.28;
  const bottleH = h * 0.62;
  return (
    <group>
      <mesh position={[0, 0, 6]} receiveShadow castShadow>
        <boxGeometry args={[w, d, 12]} />
        <Mat {...m} color="#d6d3d1" />
      </mesh>
      <mesh position={[0, d * 0.12, h - bottleH / 2]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <cylinderGeometry args={[r, r, bottleH, 24]} />
        <Mat {...m} opacity={0.75} />
      </mesh>
      <mesh position={[0, d * 0.12, (h - bottleH) / 2 + 6]}>
        <boxGeometry args={[10, 10, h - bottleH - 12]} />
        <Mat {...m} color="#a8a29e" />
      </mesh>
      {/* 꼭지 (앞쪽) */}
      <mesh position={[0, -d * 0.18, h - bottleH - 8]} rotation={[-Math.PI / 3, 0, 0]}>
        <cylinderGeometry args={[3, 3, d * 0.5, 8]} />
        <meshStandardMaterial color="#78716c" />
      </mesh>
    </group>
  );
}

function Plate({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  return (
    <mesh position={[0, 0, h / 2]} castShadow receiveShadow>
      <boxGeometry args={[w, d, h]} />
      <Mat {...m} />
    </mesh>
  );
}

// ── 내가 올린 STL·3MF 파일 ──

/** 파일을 불러오는 동안·불러오지 못했을 때: 외곽 크기 상자 (반투명) */
function MeshFallback({ asset, m }: { asset: CageAsset; m: MatProps }) {
  const [w, d, h] = asset.size;
  return (
    <mesh position={[0, 0, h / 2]}>
      <boxGeometry args={[w, d, h]} />
      <Mat {...m} opacity={0.35} />
    </mesh>
  );
}

class MeshErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** Blob 공개 주소는 쿠키 없이, API 경로(로컬 저장소)는 로그인 쿠키와 함께 받는다 */
const needsCredentials = (url: string) => !url.includes(".blob.vercel-storage.com");

/** 불러온 형상들을 바닥 가운데로 옮긴다 (가로·세로 가운데 0, 바닥 z=0). 단위는 mm 로 본다 */
function centered(parts: { geometry: THREE.BufferGeometry; matrix: THREE.Matrix4 }[]) {
  const box = new THREE.Box3();
  for (const p of parts) {
    p.geometry.computeBoundingBox();
    box.union(p.geometry.boundingBox!.clone().applyMatrix4(p.matrix));
  }
  const offset = new THREE.Matrix4().makeTranslation(
    -(box.min.x + box.max.x) / 2,
    -(box.min.y + box.max.y) / 2,
    -box.min.z,
  );
  return parts.map((p) => ({ geometry: p.geometry, matrix: offset.clone().multiply(p.matrix) }));
}

function StlMesh({ url, m }: { url: string; m: MatProps }) {
  const geometry = useLoader(STLLoader, url, (l) => l.setWithCredentials(needsCredentials(url)));
  const parts = useMemo(() => {
    geometry.computeVertexNormals();
    return centered([{ geometry, matrix: new THREE.Matrix4() }]);
  }, [geometry]);
  return <MeshParts parts={parts} m={m} />;
}

function ThreeMfMesh({ url, m }: { url: string; m: MatProps }) {
  const group = useLoader(ThreeMFLoader, url, (l) => l.setWithCredentials(needsCredentials(url)));
  const parts = useMemo(() => {
    group.updateMatrixWorld(true);
    const list: { geometry: THREE.BufferGeometry; matrix: THREE.Matrix4 }[] = [];
    group.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) list.push({ geometry: mesh.geometry, matrix: mesh.matrixWorld.clone() });
    });
    return centered(list);
  }, [group]);
  return <MeshParts parts={parts} m={m} />;
}

function MeshParts({ parts, m }: { parts: { geometry: THREE.BufferGeometry; matrix: THREE.Matrix4 }[]; m: MatProps }) {
  return (
    <group>
      {parts.map((p, i) => (
        <mesh key={i} geometry={p.geometry} matrix={p.matrix} matrixAutoUpdate={false} castShadow receiveShadow>
          <Mat {...m} />
        </mesh>
      ))}
    </group>
  );
}

function FileMesh({ asset, m }: { asset: CageAsset; m: MatProps }) {
  if (!asset.mesh) return <MeshFallback asset={asset} m={m} />;
  const fallback = <MeshFallback asset={asset} m={m} />;
  return (
    <MeshErrorBoundary key={asset.mesh.url} fallback={fallback}>
      <Suspense fallback={fallback}>
        {asset.mesh.format === "stl" ? <StlMesh url={asset.mesh.url} m={m} /> : <ThreeMfMesh url={asset.mesh.url} m={m} />}
      </Suspense>
    </MeshErrorBoundary>
  );
}

const SHAPES = {
  house: House,
  multi_room: MultiRoom,
  corner_house: CornerHouse,
  log_arch: LogArch,
  tunnel: Tunnel,
  wheel: Wheel,
  platform: Platform,
  ramp: Ramp,
  bridge: Bridge,
  stone: Stone,
  tray: Tray,
  bowl: Bowl,
  water_stand: WaterStand,
  plate: Plate,
  // 바닥재는 바닥 전체에 따로 그려요 (PlannerScene 의 Bedding)
  bedding: () => null,
  mesh: FileMesh,
} satisfies Record<CageAsset["shape"], (p: { asset: CageAsset; m: MatProps }) => React.ReactNode>;

export default function AssetModel({ asset, highlight }: { asset: CageAsset; highlight: "none" | "selected" | "hover" }) {
  const Shape = SHAPES[asset.shape];
  const m: MatProps = {
    color: asset.color,
    emissive: highlight === "none" ? "#000000" : "#ffb347",
    emissiveIntensity: highlight === "selected" ? 0.35 : highlight === "hover" ? 0.15 : 0,
  };
  return <Shape asset={asset} m={m} />;
}
