// STL·3MF 로 미리보기 이미지를 만든다 (탐색에 작품을 올릴 때 이미지를 따로 고르지 않았으면 대신 쓴다).
// 화면에 붙이지 않은 캔버스에 한 번 그려 PNG/WEBP 로 받는다. 브라우저에서만 쓴다.

import * as THREE from "three";
import { ThreeMFLoader } from "three/examples/jsm/loaders/3MFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import {
  centered,
  EDGE_MAX_TRIANGLES,
  outlineGeometry,
  partsOf3mf,
  triangleCount,
  type MeshFormat,
  type MeshPart,
} from "@/components/three/FileMesh";
import { decodeNfm } from "@/lib/nfm";
import { EDGE_STYLE, fitCamera, MODEL_COLOR, OUTLINE_STYLE, PREVIEW_BG, samplePoints } from "@/lib/previewLook";

const W = 960;
const H = 720;
/** 목록 카드에서는 조금 더 크게 채운다 */
const FILL = 0.78;

export { isMeshFormat } from "@/lib/meshUrl";

/** format "nfm": 서버가 만든 가벼운 미리보기 메시 (원본보다 수십 배 작다) */
async function parse(buffer: ArrayBuffer, format: MeshFormat | "nfm"): Promise<MeshPart[]> {
  if (format === "nfm") return centered([{ geometry: await decodeNfm(buffer), matrix: new THREE.Matrix4() }]);
  if (format === "stl") {
    const g = new STLLoader().parse(buffer);
    g.computeVertexNormals();
    return centered([{ geometry: g, matrix: new THREE.Matrix4() }]);
  }
  return centered(partsOf3mf(new ThreeMFLoader().parse(buffer)));
}

/** 비스듬히 위에서 본 모습을 그린다. 그릴 수 없으면(형상이 비었거나 WebGL 이 없으면) null */
export async function renderMeshThumbnail(buffer: ArrayBuffer, format: MeshFormat | "nfm"): Promise<Blob | null> {
  const parts = await parse(buffer, format);
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
    renderer.setClearColor(PREVIEW_BG);
    // 3D 미리보기(@react-three/fiber 기본값)와 같은 색 처리·부드러운 그림자
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap; // three 0.187 에서 PCFSoft 는 없어졌다 (shadow.radius 로 부드럽게)
    const scene = new THREE.Scene();
    // 파일은 Z-up(mm) 이고 three.js 는 Y-up 이라 X 축으로 -90° 돌린다
    const model = new THREE.Group();
    model.rotation.x = -Math.PI / 2;
    const material = new THREE.MeshStandardMaterial({ color: MODEL_COLOR, roughness: 0.62, metalness: 0 });
    const lineMaterial = new THREE.LineBasicMaterial({ color: EDGE_STYLE.color, transparent: true, opacity: EDGE_STYLE.opacity });
    // 바깥 윤곽선: 법선 방향으로 살짝 부풀린 뒷면을 진한 색으로 (미리보기의 Outlines 와 같은 방식)
    const outlineMaterial = new THREE.MeshBasicMaterial({
      color: OUTLINE_STYLE.color,
      side: THREE.BackSide,
      // 깊이를 뒤로 밀어, 얇은 곳에서 부풀린 면이 앞면을 뚫고 얼룩처럼 보이지 않게
      polygonOffset: true,
      polygonOffsetFactor: 10,
      polygonOffsetUnits: 10,
    });
    const owned: { dispose: () => void }[] = [material, lineMaterial, outlineMaterial];
    const withEdges = triangleCount(parts) <= EDGE_MAX_TRIANGLES;
    const meshes: THREE.Mesh[] = [];
    for (const p of parts) {
      const mesh = new THREE.Mesh(p.geometry, material);
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(p.matrix);
      mesh.castShadow = true; // 바닥에만 그림자 (자기 그림자는 큰 메시에서 얼룩처럼 보인다)
      model.add(mesh);
      meshes.push(mesh);
      if (withEdges) {
        const edges = new THREE.EdgesGeometry(p.geometry, EDGE_STYLE.thresholdDeg);
        owned.push(edges);
        const lines = new THREE.LineSegments(edges, lineMaterial);
        lines.matrixAutoUpdate = false;
        lines.matrix.copy(p.matrix);
        model.add(lines);
      }
    }
    scene.add(model);

    // 메시는 행렬을 직접 넣었으므로(matrixAutoUpdate 끔) 크기를 재기 전에 월드 행렬을 먼저 맞춘다
    scene.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(model);
    const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1);
    const camera = new THREE.PerspectiveCamera(35, W / H);
    fitCamera(camera, samplePoints(meshes.map((m) => ({ geometry: m.geometry, toWorld: m.matrixWorld }))), FILL);
    // 윤곽선 두께: 화면에서 약 1.5px 이 되도록 카메라 거리로 정한다
    const pxWorld = (2 * camera.position.distanceTo(box.getCenter(new THREE.Vector3())) * Math.tan(THREE.MathUtils.degToRad(35 / 2))) / H;
    const thickness = pxWorld * OUTLINE_STYLE.thickness;
    for (const m of meshes) {
      const smooth = outlineGeometry(m.geometry);
      // 3MF 부품 변환에 배율이 있으면 그만큼 나눠 화면 두께를 맞춘다 (두께는 부품마다 다른 uniform)
      const t = thickness / Math.max(m.matrix.getMaxScaleOnAxis(), 1e-6);
      const hullMaterial = outlineMaterial.clone();
      hullMaterial.onBeforeCompile = (shader) => {
        shader.uniforms.outlineT = { value: t };
        shader.vertexShader = `uniform float outlineT;\n${shader.vertexShader}`.replace(
          "#include <begin_vertex>",
          "vec3 transformed = vec3( position ) + normalize( normal ) * outlineT;",
        );
      };
      owned.push(smooth, hullMaterial);
      const hull = new THREE.Mesh(smooth, hullMaterial);
      hull.matrixAutoUpdate = false;
      hull.matrix.copy(m.matrix);
      model.add(hull);
    }
    scene.updateMatrixWorld(true);

    // 환경광 + 주광(그림자) + 보조광 + 역광
    scene.add(new THREE.HemisphereLight("#ffffff", "#d9c9b4", 1.1));
    scene.add(new THREE.AmbientLight("#ffffff", 0.25));
    const key = new THREE.DirectionalLight("#ffffff", 2.2);
    // 카메라(오른쪽 앞)와 반대쪽인 왼쪽 앞 위에서 비춰 그림자가 보이는 쪽 바닥에 떨어지게
    key.position.set(-radius * 1.3, box.min.y + radius * 2.4, radius * 1.4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = radius * 0.004;
    key.shadow.radius = 6;
    const sh = radius * 1.6;
    Object.assign(key.shadow.camera, { left: -sh, right: sh, top: sh, bottom: -sh, near: radius * 0.1, far: radius * 8 });
    key.shadow.camera.updateProjectionMatrix();
    scene.add(key);
    const fill = new THREE.DirectionalLight("#ffffff", 0.55);
    fill.position.set(radius * 2, radius * 0.9, radius * 0.8);
    scene.add(fill);
    const rim = new THREE.DirectionalLight("#ffffff", 0.75);
    rim.position.set(radius * 0.4, radius * 1.4, -radius * 2.2);
    scene.add(rim);
    // 그림자를 받는 투명 바닥
    const floorGeo = new THREE.PlaneGeometry(radius * 10, radius * 10);
    const floorMat = new THREE.ShadowMaterial({ opacity: 0.18 });
    owned.push(floorGeo, floorMat);
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = box.min.y + 0.05;
    floor.receiveShadow = true;
    scene.add(floor);
    // 바닥에 닿는 곳의 옅은 접촉 그림자 (발자국 크기의 흐린 타원)
    const spot = document.createElement("canvas");
    spot.width = spot.height = 128;
    const ctx = spot.getContext("2d");
    if (ctx) {
      const g = ctx.createRadialGradient(64, 64, 8, 64, 64, 64);
      g.addColorStop(0, "rgba(43,33,24,0.55)");
      g.addColorStop(0.6, "rgba(43,33,24,0.25)");
      g.addColorStop(1, "rgba(43,33,24,0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 128, 128);
      const tex = new THREE.CanvasTexture(spot);
      const size = box.getSize(new THREE.Vector3());
      const contactGeo = new THREE.PlaneGeometry(size.x * 1.35, size.z * 1.35);
      const contactMat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false });
      owned.push(tex, contactGeo, contactMat);
      const contact = new THREE.Mesh(contactGeo, contactMat);
      contact.rotation.x = -Math.PI / 2;
      contact.position.set((box.min.x + box.max.x) / 2, box.min.y + 0.1, (box.min.z + box.max.z) / 2);
      contact.renderOrder = -1;
      scene.add(contact);
    }

    renderer.render(scene, camera);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/webp", 0.88));
    owned.forEach((o) => o.dispose());
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
