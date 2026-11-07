"use client";

// 회원이 올린 STL·3MF 를 불러와 그린다 (가상 케이지와 탐색 미리보기가 함께 쓴다).
// 형상은 바닥 가운데로 옮겨요: 가로·세로 가운데가 0, 바닥이 z=0 (Z-up, 단위 mm).

import { useLoader } from "@react-three/fiber";
import { Component, useMemo, type ReactNode } from "react";
import * as THREE from "three";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

export type MeshFormat = "stl" | "3mf";
export type MeshPart = { geometry: THREE.BufferGeometry; matrix: THREE.Matrix4 };

/** Blob 공개 주소는 쿠키 없이, API 경로(로컬 저장소)는 로그인 쿠키와 함께 받는다 */
export const needsCredentials = (url: string) => !url.includes(".blob.vercel-storage.com");

/** 불러온 형상들을 바닥 가운데로 옮긴다 */
export function centered(parts: MeshPart[]): MeshPart[] {
  const box = new THREE.Box3();
  for (const p of parts) {
    p.geometry.computeBoundingBox();
    box.union(p.geometry.boundingBox!.clone().applyMatrix4(p.matrix));
  }
  const offset = new THREE.Matrix4().makeTranslation(-(box.min.x + box.max.x) / 2, -(box.min.y + box.max.y) / 2, -box.min.z);
  return parts.map((p) => ({ geometry: p.geometry, matrix: offset.clone().multiply(p.matrix) }));
}

/** 3MF 그룹 안의 메시를 모은다 (각 메시의 위치·회전을 담은 행렬과 함께) */
export function partsOf3mf(group: THREE.Object3D): MeshPart[] {
  group.updateMatrixWorld(true);
  const list: MeshPart[] = [];
  group.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (mesh.isMesh) list.push({ geometry: mesh.geometry, matrix: mesh.matrixWorld.clone() });
  });
  return list;
}

function StlParts({ url, material }: { url: string; material: () => ReactNode }) {
  const geometry = useLoader(STLLoader, url, (l) => l.setWithCredentials(needsCredentials(url)));
  const parts = useMemo(() => {
    geometry.computeVertexNormals();
    return centered([{ geometry, matrix: new THREE.Matrix4() }]);
  }, [geometry]);
  return <MeshParts parts={parts} material={material} />;
}

function ThreeMfParts({ url, material }: { url: string; material: () => ReactNode }) {
  const group = useLoader(ThreeMFLoader, url, (l) => l.setWithCredentials(needsCredentials(url)));
  const parts = useMemo(() => centered(partsOf3mf(group)), [group]);
  return <MeshParts parts={parts} material={material} />;
}

function MeshParts({ parts, material }: { parts: MeshPart[]; material: () => ReactNode }) {
  return (
    <group>
      {parts.map((p, i) => (
        <mesh key={i} geometry={p.geometry} matrix={p.matrix} matrixAutoUpdate={false} castShadow receiveShadow>
          {material()}
        </mesh>
      ))}
    </group>
  );
}

const loaderOf = (f: MeshFormat) => (f === "stl" ? STLLoader : ThreeMFLoader);
let lastPreview: { url: string; format: MeshFormat } | null = null;

/** 미리보기는 마지막에 본 파일만 메모리에 남긴다 (탐색을 둘러보는 동안 큰 메시가 쌓이지 않게).
 * 막 본 파일은 남겨 두므로 "가상 케이지에 놓아 보기"로 넘어가면 다시 받지 않는다 */
export function keepOnlyPreview(url: string, format: MeshFormat) {
  if (lastPreview && (lastPreview.url !== url || lastPreview.format !== format)) {
    useLoader.clear(loaderOf(lastPreview.format), lastPreview.url);
  }
  lastPreview = { url, format };
}

/** 파일 형상 (불러오는 동안 Suspense 로 멈춘다. 감싸는 쪽에서 Suspense·MeshErrorBoundary 로 받는다) */
export function LoadedMesh({ url, format, material }: { url: string; format: MeshFormat; material: () => ReactNode }) {
  return format === "stl" ? <StlParts url={url} material={material} /> : <ThreeMfParts url={url} material={material} />;
}

/** 불러오지 못했으면 fallback 을 그린다 */
export class MeshErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode; onError?: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError?.();
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
