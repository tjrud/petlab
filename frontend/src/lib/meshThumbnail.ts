// STL·3MF 로 미리보기 이미지를 만든다 (탐색에 작품을 올릴 때 이미지를 따로 고르지 않았으면 대신 쓴다).
// 화면에 붙이지 않은 캔버스에 한 번 그려 PNG/WEBP 로 받는다. 브라우저에서만 쓴다.

import * as THREE from "three";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { centered, partsOf3mf, type MeshFormat, type MeshPart } from "@/components/three/FileMesh";

const W = 960;
const H = 720;
const BG = "#f5efe6";
const COLOR = "#c9a27e";

export const isMeshFormat = (f: string): f is MeshFormat => f === "stl" || f === "3mf";

function parse(buffer: ArrayBuffer, format: MeshFormat): MeshPart[] {
  if (format === "stl") {
    const g = new STLLoader().parse(buffer);
    g.computeVertexNormals();
    return centered([{ geometry: g, matrix: new THREE.Matrix4() }]);
  }
  return centered(partsOf3mf(new ThreeMFLoader().parse(buffer)));
}

/** 비스듬히 위에서 본 모습을 그린다. 그릴 수 없으면(형상이 비었거나 WebGL 이 없으면) null */
export async function renderMeshThumbnail(buffer: ArrayBuffer, format: MeshFormat): Promise<Blob | null> {
  const parts = parse(buffer, format);
  if (!parts.length) return null;
  const canvas = document.createElement("canvas");
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  } catch {
    parts.forEach((p) => p.geometry.dispose());
    return null;
  }
  try {
    renderer.setSize(W, H, false);
    renderer.setClearColor(BG);
    const scene = new THREE.Scene();
    // 파일은 Z-up(mm) 이고 three.js 는 Y-up 이라 X 축으로 -90° 돌린다
    const model = new THREE.Group();
    model.rotation.x = -Math.PI / 2;
    const material = new THREE.MeshStandardMaterial({ color: COLOR, roughness: 0.75, metalness: 0 });
    for (const p of parts) {
      const mesh = new THREE.Mesh(p.geometry, material);
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(p.matrix);
      model.add(mesh);
    }
    scene.add(model);
    scene.add(new THREE.HemisphereLight("#ffffff", "#b8a48c", 1.6));
    const sun = new THREE.DirectionalLight("#ffffff", 1.8);
    sun.position.set(1, 2, 1.5);
    scene.add(sun);

    // 메시는 행렬을 직접 넣었으므로(matrixAutoUpdate 끔) 크기를 재기 전에 월드 행렬을 먼저 맞춘다
    scene.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, 1);
    const camera = new THREE.PerspectiveCamera(35, W / H, radius / 100, radius * 20);
    const dist = (radius / Math.sin(THREE.MathUtils.degToRad(35 / 2))) * 1.1;
    const dir = new THREE.Vector3(1, 0.75, 1.25).normalize();
    camera.position.copy(center).addScaledVector(dir, dist);
    camera.lookAt(center);
    renderer.render(scene, camera);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/webp", 0.88));
    material.dispose();
    return blob;
  } finally {
    parts.forEach((p) => p.geometry.dispose());
    renderer.dispose();
    renderer.forceContextLoss();
  }
}

/** 이미지 Blob 을 올릴 수 있는 File 로 (브라우저가 WEBP 를 못 만들면 PNG 로 온다) */
export function thumbnailFile(blob: Blob, baseName: string): File {
  const ext = blob.type === "image/webp" ? "webp" : blob.type === "image/jpeg" ? "jpg" : "png";
  const stem = baseName.replace(/\.[^.]+$/, "").slice(0, 80) || "preview";
  return new File([blob], `${stem}-미리보기.${ext}`, { type: blob.type || "image/png" });
}
