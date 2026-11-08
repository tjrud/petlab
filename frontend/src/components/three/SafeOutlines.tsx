"use client";

// 메시의 바깥 윤곽선을 원본 형상을 건드리지 않고 그린다.
// drei <Outlines> 는 부모 메시의 형상에 toCreasedNormals 를 쓰는데, 인덱스 없는 형상(STL·RoundedBox·ExtrudeGeometry)이면
// 복사하지 않고 원본 법선을 덮어써 면 음영이 망가진다. 그래서 위치(와 인덱스)만 함께 쓰고 법선은 따로 가진
// 보이지 않는 형상을 부모 안에 넣고, <Outlines> 는 그 형상에 붙인다.
//
// 쓰는 법: <mesh geometry={...}><material /><SafeOutlines color thickness /></mesh>

import { Outlines } from "@react-three/drei";
import { createPortal, useThree } from "@react-three/fiber";
import { useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";

import { outlineGeometry } from "@/components/three/FileMesh";

const HIDDEN = new THREE.MeshBasicMaterial({ visible: false });

export default function SafeOutlines({ color, thickness }: { color: string; /** CSS 픽셀 */ thickness: number }) {
  const anchor = useRef<THREE.Group>(null);
  const dpr = useThree((s) => s.viewport.dpr);
  const [hull, setHull] = useState<THREE.Mesh | null>(null);
  const source = useRef<THREE.BufferGeometry | null>(null);

  // 부모 메시의 형상이 바뀌면(크기 조절 등) 윤곽선 형상도 다시 만든다. 그릴 때마다 확인하되 형상이 같으면 바로 끝나므로
  // 갱신이 꼬리를 물지 않는다
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const parent = anchor.current?.parent as THREE.Mesh | undefined;
    const geometry = parent?.geometry;
    if (!anchor.current || !geometry || geometry === source.current) return;
    source.current = geometry;
    const mesh = new THREE.Mesh(outlineGeometry(geometry), HIDDEN);
    mesh.raycast = () => {}; // 고르기·끌기에 끼어들지 않게
    anchor.current.add(mesh);
    setHull((old) => {
      if (old) {
        old.removeFromParent();
        old.geometry.dispose();
      }
      return mesh;
    });
  });

  useLayoutEffect(
    () => () => {
      setHull((old) => {
        old?.removeFromParent();
        old?.geometry.dispose();
        return null;
      });
    },
    [],
  );

  return (
    <group ref={anchor}>
      {hull &&
        createPortal(
          // 두께는 그리기 버퍼 픽셀 단위라 기기 픽셀 비율을 곱한다. 깊이를 뒤로 밀어 얇은 곳에서 앞면을 뚫지 않게
          <Outlines angle={0} thickness={thickness * dpr} color={color} polygonOffset polygonOffsetFactor={10} />,
          hull,
        )}
    </group>
  );
}
