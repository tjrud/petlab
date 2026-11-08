"use client";

// 회원이 올린 STL·3MF 를 불러와 그린다 (가상 케이지와 탐색 미리보기가 함께 쓴다).
// 형상은 바닥 가운데로 옮겨요: 가로·세로 가운데가 0, 바닥이 z=0 (Z-up, 단위 mm).

import { Outlines } from "@react-three/drei";
import { useLoader } from "@react-three/fiber";
import { Component, useEffect, useMemo, useState, type ReactNode } from "react";
import * as THREE from "three";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

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

/** 모서리 선: 이웃한 면이 이 각도(°) 이상 꺾이는 곳만 그린다 (곡면의 잔 삼각형 경계는 빼고) */
export type EdgeStyle = { color: string; opacity: number; thresholdDeg: number };
/** 바깥 윤곽선 (살짝 부풀린 뒷면을 진한 색으로: 둥근 모서리 모델도 실루엣이 또렷해진다). thickness 는 화면 픽셀 */
export type OutlineStyle = { color: string; thickness: number };
type PartsOptions = {
  material: () => ReactNode;
  edges?: EdgeStyle;
  outline?: OutlineStyle;
  /** 형상이 준비되면 (카메라 맞춤 등에 쓴다) */
  onParts?: (parts: MeshPart[]) => void;
  /** 형상이 자기 그림자를 받을지 (기본 받음). 큰 메시는 그림자 맵 잡음이 얼룩처럼 보여 미리보기에서는 끈다 */
  selfShadow?: boolean;
};

/** 꺾인 모서리 선은 이보다 작은 메시에만 (수십만 삼각형이면 계산이 몇 초 걸리고 잔 선이 너무 많아진다) */
export const EDGE_MAX_TRIANGLES = 150_000;
const triangles = (parts: MeshPart[]) =>
  parts.reduce((n, p) => n + (p.geometry.index ? p.geometry.index.count : p.geometry.attributes.position.count) / 3, 0);

function StlParts({ url, ...opts }: { url: string } & PartsOptions) {
  const geometry = useLoader(STLLoader, url, (l) => l.setWithCredentials(needsCredentials(url)));
  const parts = useMemo(() => {
    geometry.computeVertexNormals();
    return centered([{ geometry, matrix: new THREE.Matrix4() }]);
  }, [geometry]);
  return <MeshParts parts={parts} {...opts} />;
}

function ThreeMfParts({ url, ...opts }: { url: string } & PartsOptions) {
  const group = useLoader(ThreeMFLoader, url, (l) => l.setWithCredentials(needsCredentials(url)));
  const parts = useMemo(() => centered(partsOf3mf(group)), [group]);
  return <MeshParts parts={parts} {...opts} />;
}

/** 모서리 선 형상. 큰 메시(수십만 삼각형)는 계산이 1초 가까이 걸리므로 형상을 먼저 보여 준 뒤 다음 차례에 만든다 */
function useEdgeGeometries(parts: MeshPart[], style: EdgeStyle | undefined) {
  const [result, setResult] = useState<{ parts: MeshPart[]; lines: THREE.EdgesGeometry[] } | null>(null);
  const threshold = style && triangles(parts) <= EDGE_MAX_TRIANGLES ? style.thresholdDeg : undefined;
  useEffect(() => {
    if (threshold === undefined) return;
    let made: THREE.EdgesGeometry[] = [];
    const t = window.setTimeout(() => {
      made = parts.map((p) => new THREE.EdgesGeometry(p.geometry, threshold));
      setResult({ parts, lines: made });
    }, 0);
    return () => {
      window.clearTimeout(t);
      made.forEach((g) => g.dispose());
    };
  }, [parts, threshold]);
  return result && result.parts === parts ? result.lines : null;
}

/** 윤곽선용 형상: 위치는 원본과 함께 쓰고 법선만 매끈하게 따로 만든다.
 * toCreasedNormals 는 인덱스 없는 형상(STL)을 받으면 복사하지 않고 원본의 법선을 덮어쓰므로, 원본에 직접 쓰면
 * 모델 면이 물결처럼 보인다 */
export function outlineGeometry(source: THREE.BufferGeometry): THREE.BufferGeometry {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", source.attributes.position);
  if (source.index) g.setIndex(source.index);
  return toCreasedNormals(g, Math.PI);
}

/** 바깥 윤곽선: 보이지 않는 형상(매끈한 법선)에 Outlines 를 붙인다 */
function OutlineParts({ parts, style }: { parts: MeshPart[]; style: OutlineStyle }) {
  const hulls = useMemo(() => parts.map((p) => outlineGeometry(p.geometry)), [parts]);
  return (
    <>
      {parts.map((p, i) => (
        <mesh key={i} geometry={hulls[i]} matrix={p.matrix} matrixAutoUpdate={false}>
          <meshBasicMaterial colorWrite={false} depthWrite={false} />
          {/* 깊이를 뒤로 밀어, 얇은 곳에서 부풀린 면이 앞면을 뚫고 보이지 않게 */}
          <Outlines screenspace angle={0} thickness={style.thickness} color={style.color} polygonOffset polygonOffsetFactor={10} />
        </mesh>
      ))}
    </>
  );
}

function MeshParts({ parts, material, edges, outline, onParts, selfShadow = true }: { parts: MeshPart[] } & PartsOptions) {
  const lines = useEdgeGeometries(parts, edges);
  useEffect(() => {
    onParts?.(parts);
  }, [parts, onParts]);
  return (
    <group>
      {parts.map((p, i) => (
        <mesh key={i} geometry={p.geometry} matrix={p.matrix} matrixAutoUpdate={false} castShadow receiveShadow={selfShadow}>
          {material()}
        </mesh>
      ))}
      {outline && <OutlineParts parts={parts} style={outline} />}
      {edges &&
        lines?.map((g, i) => (
          <lineSegments key={`e${i}`} geometry={g} matrix={parts[i].matrix} matrixAutoUpdate={false}>
            <lineBasicMaterial color={edges.color} transparent opacity={edges.opacity} />
          </lineSegments>
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
export function LoadedMesh({ url, format, ...opts }: { url: string; format: MeshFormat } & PartsOptions) {
  return format === "stl" ? <StlParts url={url} {...opts} /> : <ThreeMfParts url={url} {...opts} />;
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
