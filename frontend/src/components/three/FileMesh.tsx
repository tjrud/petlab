"use client";

// 회원이 올린 STL·3MF 를 불러와 그린다 (가상 케이지와 탐색 미리보기가 함께 쓴다).
// 형상은 바닥 가운데로 옮겨요: 가로·세로 가운데가 0, 바닥이 z=0 (Z-up, 단위 mm).

import { Outlines } from "@react-three/drei";
import { useLoader, useThree } from "@react-three/fiber";
import { Component, useEffect, useMemo, useState, type ReactNode } from "react";
import * as THREE from "three";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { mergeVertices, toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

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
/** 바깥 윤곽선 (살짝 부풀린 뒷면을 진한 색으로: 둥근 모서리 모델도 실루엣이 또렷해진다). thickness 는 CSS 픽셀 */
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
export const triangleCount = (parts: MeshPart[]) =>
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
  const threshold = style && triangleCount(parts) <= EDGE_MAX_TRIANGLES ? style.thresholdDeg : undefined;
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

/** 윤곽선용 형상: 법선만 매끈하게 따로 가진 형상 (원본은 건드리지 않는다).
 * - 인덱스 없는 형상(STL·RoundedBox·각기둥): 위치 속성을 원본과 함께 쓰고 toCreasedNormals 로 법선을 만든다.
 *   toCreasedNormals 는 인덱스 없는 형상을 받으면 복사하지 않고 그 형상의 법선을 덮어쓰므로, 원본에 직접 쓰면 면이 물결처럼 보인다.
 * - 인덱스 있는 형상(3MF·상자·원기둥): 모서리마다 꼭짓점을 따로 둔 경우가 많아 그대로 법선을 내면 윤곽선 모서리가 갈라진다.
 *   위치가 같은 꼭짓점을 합친 새 형상으로 법선을 낸다 */
export function outlineGeometry(source: THREE.BufferGeometry): THREE.BufferGeometry {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", source.attributes.position);
  if (source.index) {
    g.setIndex(source.index);
    const welded = mergeVertices(g);
    welded.computeVertexNormals();
    return welded;
  }
  return toCreasedNormals(g, Math.PI);
}

/** 윤곽선 형상을 버린다. 원본과 함께 쓰는 위치·인덱스 버퍼는 남기고 이 형상만의 버퍼만 GPU 에서 내린다
 * (함께 쓰는 버퍼를 dispose 하면 같은 파일을 놓아 둔 다른 구조물의 버퍼까지 지워진다) */
export function disposeOutlineGeometry(hull: THREE.BufferGeometry, source: THREE.BufferGeometry) {
  if (hull.attributes.position === source.attributes.position) hull.deleteAttribute("position");
  if (hull.index && hull.index === source.index) hull.setIndex(null);
  hull.dispose();
}

/** 같은 원본 형상의 윤곽선 형상은 한 번만 만들어 함께 쓴다 (같은 STL 을 여러 개 놓아도 계산·메모리는 한 번) */
const HULLS = new Map<THREE.BufferGeometry, { hull: THREE.BufferGeometry; refs: number }>();
export function acquireOutlineGeometry(source: THREE.BufferGeometry): THREE.BufferGeometry {
  const hit = HULLS.get(source);
  if (hit) {
    hit.refs += 1;
    return hit.hull;
  }
  const hull = outlineGeometry(source);
  HULLS.set(source, { hull, refs: 1 });
  return hull;
}
export function releaseOutlineGeometry(source: THREE.BufferGeometry) {
  const hit = HULLS.get(source);
  if (!hit) return;
  hit.refs -= 1;
  if (hit.refs <= 0) {
    HULLS.delete(source);
    disposeOutlineGeometry(hit.hull, source);
  }
}

/** 고르기·끌기 판정에서 이 메시와 그 아래(Outlines)를 모두 뺀다 (false 를 돌려줘야 자식까지 건너뛴다) */
export const NO_RAYCAST = () => false as unknown as void;

/** 바깥 윤곽선: 보이지 않는 형상(매끈한 법선)에 Outlines 를 붙인다.
 * 법선 계산은 큰 메시에서 수백 ms 걸리므로 형상을 먼저 보여 준 뒤 다음 차례에 만든다 */
function OutlineParts({ parts, style }: { parts: MeshPart[]; style: OutlineStyle }) {
  const dpr = useThree((s) => s.viewport.dpr);
  const [built, setBuilt] = useState<{ parts: MeshPart[]; hulls: THREE.BufferGeometry[] } | null>(null);
  useEffect(() => {
    let acquired: THREE.BufferGeometry[] = [];
    const t = window.setTimeout(() => {
      acquired = parts.map((p) => p.geometry);
      setBuilt({ parts, hulls: acquired.map(acquireOutlineGeometry) });
    }, 0);
    return () => {
      window.clearTimeout(t);
      acquired.forEach(releaseOutlineGeometry);
    };
  }, [parts]);
  const hulls = built && built.parts === parts ? built.hulls : null;
  if (!hulls) return null;
  return (
    <>
      {parts.map((p, i) => (
        <mesh key={i} geometry={hulls[i]} matrix={p.matrix} matrixAutoUpdate={false} raycast={NO_RAYCAST}>
          {/* 이 형상 자체는 그리지 않고 윤곽선만 */}
          <meshBasicMaterial visible={false} />
          {/* 두께는 그리기 버퍼 픽셀 단위라 기기 픽셀 비율을 곱한다. 깊이를 뒤로 밀어 얇은 곳에서 앞면을 뚫지 않게 */}
          <Outlines angle={0} thickness={style.thickness * dpr} color={style.color} polygonOffset polygonOffsetFactor={10} />
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
