"use client";

// 메시의 바깥 윤곽선을 원본 형상을 건드리지 않고 그린다.
// drei <Outlines> 는 부모 메시의 형상에 toCreasedNormals 를 쓰는데, 인덱스 없는 형상(STL·RoundedBox·ExtrudeGeometry)이면
// 복사하지 않고 원본 법선을 덮어써 면 음영이 망가진다. 그래서 법선만 따로 가진 보이지 않는 형상을 부모 안에 넣고,
// <Outlines> 는 그 형상에 붙인다 (윤곽선 형상은 원본 형상마다 한 번만 만들어 함께 쓴다).
//
// 쓰는 법: <mesh geometry={...}><material /><SafeOutlines color thickness /></mesh>

import { Outlines } from "@react-three/drei";
import { createPortal, useThree } from "@react-three/fiber";
import { useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";

import { acquireOutlineGeometry, NO_RAYCAST, releaseOutlineGeometry } from "@/components/three/FileMesh";

const HIDDEN = new THREE.MeshBasicMaterial({ visible: false });

export default function SafeOutlines({ color, thickness }: { color: string; /** CSS 픽셀 */ thickness: number }) {
  const anchor = useRef<THREE.Group>(null);
  const dpr = useThree((s) => s.viewport.dpr);
  /** 부모 메시의 지금 형상 (크기 조절 등으로 형상이 바뀌면 따라 바꾼다) */
  const [source, setSource] = useState<THREE.BufferGeometry | null>(null);
  const [hull, setHull] = useState<THREE.Mesh | null>(null);

  // 그릴 때마다 부모 형상을 확인한다. 같으면 아무것도 하지 않으므로 갱신이 꼬리를 물지 않는다
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const g = (anchor.current?.parent as THREE.Mesh | undefined)?.geometry ?? null;
    if (g !== source) setSource(g);
  });

  // 윤곽선 형상의 수명은 원본 형상에 묶는다. 화면에서 가려졌다 다시 보일 때(Activity)·StrictMode 에서도 정리와 생성이 짝을 이룬다
  useLayoutEffect(() => {
    const parent = anchor.current;
    if (!source || !parent) return;
    const mesh = new THREE.Mesh(acquireOutlineGeometry(source), HIDDEN);
    mesh.raycast = NO_RAYCAST; // 고르기·끌기에 끼어들지 않게 (자식인 Outlines 까지)
    parent.add(mesh);
    setHull(mesh);
    return () => {
      mesh.removeFromParent();
      releaseOutlineGeometry(source);
      setHull(null);
    };
  }, [source]);

  return (
    <group ref={anchor}>
      {hull &&
        createPortal(
          // 두께는 그리기 버퍼 픽셀 단위라 기기 픽셀 비율을 곱한다. 깊이를 뒤로 밀어 얇은 곳에서 앞면을 뚫지 않게
          <Outlines key={hull.uuid} angle={0} thickness={thickness * dpr} color={color} polygonOffset polygonOffsetFactor={10} />,
          hull,
        )}
    </group>
  );
}
