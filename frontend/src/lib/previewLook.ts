// 3D 미리보기(탐색 상세)와 자동 대표 이미지가 함께 쓰는 모습: 색·모서리 선·카메라 각도와 화면 맞춤.

import * as THREE from "three";

/** 밝은 쿨그레이 배경 (나무색 모델과 확실히 구분되게) */
export const PREVIEW_BG = "#eef1f4";
/** 채도를 조금 올린 나무색 */
export const MODEL_COLOR = "#c8874e";
/** 꺾인 모서리만 얇고 진하게 (곡면의 잔 삼각형 경계는 빼려고 25° 이상 꺾인 곳만) */
export const EDGE_STYLE = { color: "#3b2716", opacity: 0.55, thresholdDeg: 25 } as const;
/** 바깥 윤곽선 (화면 픽셀 두께) */
export const OUTLINE_STYLE = { color: "#3b2716", thickness: 1.6 } as const;
/** 위에서 내려다보는 각도와 오른쪽으로 돌린 각도 */
export const ELEVATION_DEG = 32;
export const AZIMUTH_DEG = 35;

/** 카메라 방향 (Y-up, 모델 앞쪽이 +Z): 오른쪽 앞 위 */
export function viewDirection(): THREE.Vector3 {
  const el = THREE.MathUtils.degToRad(ELEVATION_DEG);
  const az = THREE.MathUtils.degToRad(AZIMUTH_DEG);
  return new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
}

const SAMPLE_POINTS = 30_000;

/** 형상의 꼭짓점을 고르게 골라(최대 SAMPLE_POINTS 개) 월드 좌표(Y-up)로. toWorld 는 각 메시의 월드 행렬 */
export function samplePoints(parts: { geometry: THREE.BufferGeometry; toWorld: THREE.Matrix4 }[]): THREE.Vector3[] {
  const total = parts.reduce((n, p) => n + p.geometry.attributes.position.count, 0);
  const step = Math.max(1, Math.floor(total / SAMPLE_POINTS));
  const out: THREE.Vector3[] = [];
  for (const p of parts) {
    const pos = p.geometry.attributes.position;
    for (let i = 0; i < pos.count; i += step) out.push(new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(p.toWorld));
  }
  return out;
}

/** 외곽 상자의 꼭짓점 8개 (형상을 받기 전 대략 맞출 때) */
export function boxCorners(box: THREE.Box3): THREE.Vector3[] {
  const corners: THREE.Vector3[] = [];
  for (const x of [box.min.x, box.max.x])
    for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
  return corners;
}

/** points 를 화면에 비춘 범위가 가로·세로 중 좁은 쪽의 fill(0~1) 만큼을 차지하고, 화면 가운데에 오도록 카메라를 놓는다.
 * 각도는 viewDirection() 그대로이고, 돌려 볼 때의 중심(돌려 보는 기준점)을 돌려준다.
 * 화면 비율까지 따지므로 모바일의 세로 화면에서도 같은 비율로 찬다 */
export function fitCamera(camera: THREE.PerspectiveCamera, points: THREE.Vector3[], fill: number): THREE.Vector3 {
  const box = new THREE.Box3().setFromPoints(points);
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1);
  const dir = viewDirection();
  camera.near = radius / 50;
  camera.far = radius * 60;
  camera.updateProjectionMatrix();
  const p = new THREE.Vector3();
  /** 화면에 비친 범위: 가로·세로 반폭(화면 비율로 맞춘 것 중 큰 쪽)과 가운데 */
  const measure = (dist: number) => {
    camera.position.copy(center).addScaledVector(dir, dist);
    camera.lookAt(center);
    camera.updateMatrixWorld();
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const c of points) {
      p.copy(c).project(camera);
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
    return { half: Math.max((maxX - minX) / 2, (maxY - minY) / 2), cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 };
  };
  const search = () => {
    let lo = radius * 0.3;
    let hi = radius * 40;
    for (let i = 0; i < 40; i++) {
      const mid = (lo + hi) / 2;
      if (measure(mid).half > fill) lo = mid;
      else hi = mid;
    }
    return hi;
  };
  // 거리를 맞추고, 화면에서 치우친 만큼 기준점을 옮긴 뒤 한 번 더 맞춘다
  for (let pass = 0; pass < 2; pass++) {
    const dist = search();
    const m = measure(dist);
    const halfH = dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const halfW = halfH * camera.aspect;
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
    center.addScaledVector(right, m.cx * halfW).addScaledVector(up, m.cy * halfH);
  }
  measure(search());
  return center;
}
