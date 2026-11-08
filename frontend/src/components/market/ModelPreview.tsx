"use client";

// 탐색 작품의 STL·3MF 를 3D 로 미리 본다 (끌어서 돌리고, 한 번 누른 뒤에는 확대·축소). 단위는 mm 로 본다.
// - 밝은 쿨그레이 배경 + 채도를 올린 나무색 모델 + 진한 모서리 선으로 형태를 또렷하게
// - 환경광 + 주광(부드러운 그림자) + 보조광·역광, 바닥 접촉 그림자
// - 모델의 외곽 상자가 화면의 약 2/3 를 채우게, 위에서 약 32° 내려다보는 각도로 맞춘다
// - 처음 불러오면 3~4초 천천히 돌다가 멈춘다 (만지면 바로 멈춤, 움직임 줄이기 설정이면 돌지 않음)
// 화면이 바뀔 때만 다시 그린다 (돌고 있을 때만 매 프레임). WebGL 을 쓸 수 없으면 안내 문구로 바꾼다.

import { ContactShadows, Grid, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";

import { formatBytes } from "@/components/market/common";
import { keepOnlyPreview, LoadedMesh, MeshErrorBoundary, type MeshFormat, type MeshPart } from "@/components/three/FileMesh";
import { api } from "@/lib/api";
import { boxCorners, EDGE_STYLE, fitCamera, MODEL_COLOR, OUTLINE_STYLE, PREVIEW_BG, samplePoints } from "@/lib/previewLook";
import type { MarketFile } from "@/lib/types";

/** 파일은 Z-up(mm), three.js 는 Y-up 이라 X 축으로 -90° 돌린다 (앞쪽 -Y 가 화면 쪽 +Z 가 된다) */
const Z_UP_TO_Y_UP: [number, number, number] = [-Math.PI / 2, 0, 0];

/** 외곽 상자가 화면(가로·세로 중 좁은 쪽)에서 차지하는 비율 */
const FILL = 0.66;
const AUTO_ROTATE_MS = 3500;
/** 자동 회전 속도: 시간 기준이라 화면 주사율과 관계없이 3.5초에 약 35° */
const AUTO_ROTATE_RAD_PER_S = THREE.MathUtils.degToRad(10);
const UP = new THREE.Vector3(0, 1, 0);

/** 돌려 보는 기준점을 축으로 카메라를 천천히 돌린다 (프레임 수가 아니라 흐른 시간만큼) */
function AutoRotate({ on }: { on: boolean }) {
  const offset = useRef(new THREE.Vector3());
  useFrame((state, dt) => {
    const controls = state.controls as unknown as { target: THREE.Vector3; update: () => void } | null;
    if (!on || !controls) return;
    const cam = state.camera;
    offset.current.copy(cam.position).sub(controls.target).applyAxisAngle(UP, AUTO_ROTATE_RAD_PER_S * Math.min(dt, 0.1));
    cam.position.copy(controls.target).add(offset.current);
    controls.update();
  });
  return null;
}

const cm = (mm: number) => (mm / 10).toFixed(mm % 10 === 0 ? 0 : 1);

function Loaded({ onLoaded }: { onLoaded: () => void }) {
  useEffect(onLoaded, [onLoaded]);
  return null;
}

/** 형상이 화면의 FILL 안에 들어오는 거리로 카메라를 놓는다. 형상을 받기 전에는 외곽 상자(Y-up: 가로 x, 높이 y,
 * 깊이 z, 바닥 y=0)로 대략, 받은 뒤에는 실제 꼭짓점으로 맞춘다. 사용자가 돌려 보기 전에는 화면 크기가 바뀔 때마다 다시 맞춘다 */
function FitCamera({
  size,
  points,
  touched,
}: {
  size: [number, number, number];
  points: THREE.Vector3[] | null;
  touched: React.RefObject<boolean>;
}) {
  const get = useThree((s) => s.get);
  const hasControls = useThree((s) => !!s.controls);
  const view = useThree((s) => s.size);
  const [w, d, h] = size;
  useLayoutEffect(() => {
    const state = get();
    const camera = state.camera as THREE.PerspectiveCamera;
    const controls = state.controls as unknown as { target: THREE.Vector3; update: () => void } | null;
    if (touched.current || !controls || view.width === 0 || view.height === 0) return;
    camera.aspect = view.width / view.height;
    const target = points ?? boxCorners(new THREE.Box3(new THREE.Vector3(-w / 2, 0, -d / 2), new THREE.Vector3(w / 2, h, d / 2)));
    const center = fitCamera(camera, target, FILL);
    controls.target.copy(center);
    controls.update();
    state.invalidate();
  }, [get, hasControls, view.width, view.height, w, d, h, points, touched]);
  return null;
}

export default function ModelPreview({
  file,
  className = "",
  onUnavailable,
}: {
  file: MarketFile;
  className?: string;
  /** 이 브라우저에서 3D 를 그릴 수 없을 때 (WebGL 없음) */
  onUnavailable?: () => void;
}) {
  const [active, setActive] = useState(false);
  const [glFailed, setGlFailed] = useState(false);
  const [state, setState] = useState<{ url: string; status: "loading" | "ok" | "error" }>({ url: "", status: "loading" });
  const [rotating, setRotating] = useState(false);
  /** 실제 형상의 꼭짓점 (카메라를 맞추는 데 쓴다) */
  const [points, setPoints] = useState<THREE.Vector3[] | null>(null);
  const onParts = useCallback((parts: MeshPart[]) => {
    const toYUp = new THREE.Matrix4().makeRotationX(-Math.PI / 2);
    setPoints(samplePoints(parts.map((p) => ({ geometry: p.geometry, toWorld: toYUp.clone().multiply(p.matrix) }))));
  }, []);
  /** 사용자가 한 번이라도 돌려 봤는지 (그 뒤로는 카메라를 다시 맞추지 않는다) */
  const touched = useRef(false);
  const url = file.mesh_url ? api.marketUrl(file.mesh_url) : "";
  const status = state.url === url ? state.status : "loading";
  const [w, d, h] = file.dims_mm ?? [100, 100, 100];
  const radius = Math.max(Math.hypot(w, d, h) / 2, 5);
  const S = Math.max(w, d, h, 10);

  useEffect(() => {
    if (url) keepOnlyPreview(url, file.format as MeshFormat);
  }, [url, file.format]);

  // 처음 불러오면 잠깐 천천히 돈다 (형상이 들어온 때에 한 번)
  const rotateTimer = useRef<number | null>(null);
  const autoStarted = useRef(false);
  useEffect(
    () => () => {
      if (rotateTimer.current !== null) window.clearTimeout(rotateTimer.current);
    },
    [],
  );
  const onLoaded = () => {
    setState((s) => (s.url === url && s.status === "ok" ? s : { url, status: "ok" }));
    if (autoStarted.current || touched.current) return;
    autoStarted.current = true;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    setRotating(true);
    rotateTimer.current = window.setTimeout(() => setRotating(false), AUTO_ROTATE_MS);
  };

  const stopAuto = () => {
    touched.current = true;
    setRotating(false);
  };

  if (!url) return null;
  const unavailable = (
    <p className="grid h-full place-items-center p-6 text-center text-sm text-stone-600">
      이 브라우저에서는 3D 미리보기를 볼 수 없어요. 파일을 내려받아 확인해 주세요.
    </p>
  );
  // 카메라는 오른쪽 앞에서 본다. 주광은 왼쪽 앞 위에서 비춰 그림자가 보이는 쪽(오른쪽 뒤) 바닥에 떨어지게 하고,
  // 보조광은 오른쪽에서 약하게, 역광은 뒤에서 윤곽을 살린다
  const key: [number, number, number] = [-radius * 1.3, radius * 2.4, radius * 1.4];
  const sh = radius * 1.6;
  const footprint = Math.max(Math.hypot(w, d), 10);
  return (
    <div
      className={`relative overflow-hidden rounded-xl ${className}`}
      style={{ backgroundColor: PREVIEW_BG }}
      data-rotating={rotating ? "true" : "false"}
      onPointerDown={() => {
        setActive(true);
        stopAuto();
      }}
      onWheel={() => active && stopAuto()}
    >
      <MeshErrorBoundary
        fallback={unavailable}
        onError={() => {
          setGlFailed(true);
          onUnavailable?.();
        }}
      >
        <Canvas
          frameloop={rotating ? "always" : "demand"}
          dpr={[1, 1.5]}
          shadows="percentage"
          camera={{ fov: 35, position: [S, S, S] }}
          className="h-full w-full"
          aria-label={`${file.filename} 3D 미리보기`}
        >
          <color attach="background" args={[PREVIEW_BG]} />
          <hemisphereLight args={["#ffffff", "#d9c9b4", 1.1]} />
          <ambientLight intensity={0.25} />
          <directionalLight
            position={key}
            intensity={2.2}
            castShadow
            shadow-mapSize={[2048, 2048]}
            shadow-bias={-0.0004}
            shadow-normalBias={radius * 0.004}
            shadow-radius={6}
            shadow-camera-left={-sh}
            shadow-camera-right={sh}
            shadow-camera-top={sh}
            shadow-camera-bottom={-sh}
            shadow-camera-near={radius * 0.1}
            shadow-camera-far={radius * 8}
          />
          <directionalLight position={[radius * 2, radius * 0.9, radius * 0.8]} intensity={0.55} />
          <directionalLight position={[radius * 0.4, radius * 1.4, -radius * 2.2]} intensity={0.75} />

          <MeshErrorBoundary key={url} fallback={null} onError={() => setState({ url, status: "error" })}>
            <Suspense fallback={null}>
              <group rotation={Z_UP_TO_Y_UP}>
                <LoadedMesh
                  url={url}
                  format={file.format as MeshFormat}
                  edges={EDGE_STYLE}
                  outline={OUTLINE_STYLE}
                  onParts={onParts}
                  selfShadow={false}
                  material={() => <meshStandardMaterial color={MODEL_COLOR} roughness={0.62} metalness={0} />}
                />
              </group>
              {/* 바닥에 닿는 곳의 진한 그림자. 한 번만 그리되, 형상이 화면에 들어온 뒤(꼭짓점을 받은 뒤) 다시 그린다 */}
              <ContactShadows
                key={points ? "ready" : "init"}
                position={[0, 0.2, 0]}
                scale={footprint * 2.4}
                far={Math.max(h * 0.5, 5)}
                blur={3}
                opacity={0.6}
                resolution={1024}
                frames={1}
                color="#2b2118"
              />
              <Loaded onLoaded={onLoaded} />
            </Suspense>
          </MeshErrorBoundary>
          {/* 주광 그림자를 받는 투명 바닥 */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]} receiveShadow>
            <planeGeometry args={[radius * 10, radius * 10]} />
            <shadowMaterial transparent opacity={0.22} />
          </mesh>
          {/* 옅은 격자: 모델(원점)에서 멀어질수록 사라진다. 칸 1cm, 굵은 선 10cm */}
          <Grid
            position={[0, -0.05, 0]}
            infiniteGrid
            cellSize={10}
            cellThickness={0.5}
            cellColor="#dde2e8"
            sectionSize={100}
            sectionThickness={0.9}
            sectionColor="#cdd4dc"
            fadeDistance={radius * 3.5}
            fadeStrength={2}
            fadeFrom={0}
          />
          <FitCamera size={[w, d, h]} points={points} touched={touched} />
          <AutoRotate on={rotating} />
          {/* 휠 확대는 미리보기를 한 번 누른 뒤에만 (그 전에는 휠로 페이지가 내려가게) */}
          <OrbitControls
            makeDefault
            enableZoom={active}
            dampingFactor={0.12}
            onStart={stopAuto}
            minDistance={radius * 0.6}
            maxDistance={radius * 12}
            maxPolarAngle={Math.PI / 2 - 0.05}
          />
        </Canvas>
      </MeshErrorBoundary>
      {!glFailed && status !== "ok" && (
        <p
          role="status"
          className={`absolute inset-x-3 bottom-3 rounded-lg px-3 py-2 text-xs shadow-sm ${
            status === "error" ? "bg-red-50/95 text-red-700" : "bg-white/90 text-stone-600"
          }`}
        >
          {status === "error"
            ? "3D 파일을 불러오지 못했어요. 내려받아 확인해 주세요."
            : `3D 파일을 불러오는 중이에요 (${formatBytes(file.size)})`}
        </p>
      )}
      {!glFailed && status === "ok" && (
        <p className="pointer-events-none absolute left-3 top-3 rounded-lg bg-white/90 px-2.5 py-1 text-xs text-stone-600 shadow-sm">
          {file.dims_mm ? `${cm(w)}×${cm(d)}×${cm(h)}cm · ` : ""}
          {active ? "끌어서 돌리고, 확대·축소할 수 있어요" : "끌어서 돌려 볼 수 있어요"}
        </p>
      )}
    </div>
  );
}
