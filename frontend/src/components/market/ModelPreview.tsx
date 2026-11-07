"use client";

// 탐색 작품의 STL·3MF 를 3D 로 미리 본다 (끌어서 돌리고, 휠로 확대). 단위는 mm 로 본다.

import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense, useEffect, useState } from "react";

import { formatBytes } from "@/components/market/common";
import { LoadedMesh, MeshErrorBoundary, type MeshFormat } from "@/components/three/FileMesh";
import { api } from "@/lib/api";
import type { MarketFile } from "@/lib/types";

/** 파일은 Z-up(mm), three.js 는 Y-up 이라 X 축으로 -90° 돌린다 */
const Z_UP_TO_Y_UP: [number, number, number] = [-Math.PI / 2, 0, 0];

function Loaded({ onLoaded }: { onLoaded: () => void }) {
  useEffect(onLoaded, [onLoaded]);
  return null;
}

const cm = (mm: number) => (mm / 10).toFixed(mm % 10 === 0 ? 0 : 1);

export default function ModelPreview({ file, className = "" }: { file: MarketFile; className?: string }) {
  const [state, setState] = useState<{ url: string; status: "loading" | "ok" | "error" }>({ url: "", status: "loading" });
  const url = file.mesh_url ? api.marketUrl(file.mesh_url) : "";
  const status = state.url === url ? state.status : "loading";
  const [w, d, h] = file.dims_mm ?? [100, 100, 100];
  const S = Math.max(w, d, h, 10);
  // 물체 전체(외접구)가 화면에 들어오는 거리에서 비스듬히 위를 본다
  const radius = Math.max(Math.hypot(w, d, h) / 2, 5);
  const FOV = 40;
  const dist = (radius / Math.sin(((FOV / 2) * Math.PI) / 180)) * 1.15;
  const dir = [0.62, 0.5, 0.82]; // 길이 약 1: 오른쪽·위·앞
  const camera = {
    position: [dir[0] * dist, h / 2 + dir[1] * dist, dir[2] * dist] as [number, number, number],
    fov: FOV,
    near: radius / 50,
    far: dist * 20,
  };

  if (!url) return null;
  return (
    <div className={`relative overflow-hidden rounded-xl bg-[#f5efe6] ${className}`}>
      <Canvas camera={camera} className="h-full w-full" aria-label={`${file.filename} 3D 미리보기`}>
        <color attach="background" args={["#f5efe6"]} />
        <hemisphereLight args={["#ffffff", "#b8a48c", 1.4]} />
        <directionalLight position={[S, S * 2, S * 1.5]} intensity={1.6} />
        <group rotation={Z_UP_TO_Y_UP}>
          <MeshErrorBoundary key={url} fallback={null} onError={() => setState({ url, status: "error" })}>
            <Suspense fallback={null}>
              <LoadedMesh
                url={url}
                format={file.format as MeshFormat}
                material={() => <meshStandardMaterial color="#c9a27e" roughness={0.75} metalness={0} />}
              />
              <Loaded onLoaded={() => setState((s) => (s.url === url && s.status === "ok" ? s : { url, status: "ok" }))} />
            </Suspense>
          </MeshErrorBoundary>
          <gridHelper args={[S * 3, 30, "#d6c7b2", "#e7dccd"]} rotation={[Math.PI / 2, 0, 0]} />
        </group>
        <OrbitControls makeDefault target={[0, h / 2, 0]} minDistance={radius * 0.6} maxDistance={dist * 4} />
      </Canvas>
      {status !== "ok" && (
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
      {status === "ok" && (
        <p className="pointer-events-none absolute left-3 top-3 rounded-lg bg-white/85 px-2.5 py-1 text-xs text-stone-600 shadow-sm">
          {file.dims_mm ? `${cm(w)}×${cm(d)}×${cm(h)}cm · ` : ""}끌어서 돌리고, 휠로 확대해요
        </p>
      )}
    </div>
  );
}
