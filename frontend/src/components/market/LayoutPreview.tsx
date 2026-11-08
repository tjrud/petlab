// 가상 케이지 배치 예시를 위에서 본 그림 (탐색 작품 보기·올리기). 앞(관찰 면)이 아래쪽

import { useT } from "@/i18n/client";
import { fileIdOf, getAsset, isFloorLayer } from "@/lib/cageAssets";
import { footprint } from "@/lib/cageLayout";
import type { LayoutSnapshot } from "@/lib/types";

export default function LayoutPreview({ layout, className = "" }: { layout: Pick<LayoutSnapshot, "cage" | "items">; className?: string }) {
  const t = useT();
  const { width_mm: W, depth_mm: D } = layout.cage;
  const pad = Math.max(W, D) * 0.03;
  const bedding = layout.items.map((it) => getAsset(it.asset)).find((a) => isFloorLayer(a));
  // SVG 의 y 는 아래로 커지므로 케이지 y(뒤쪽) 를 뒤집는다
  const pts = (poly: { x: number; y: number }[]) => poly.map((p) => `${p.x},${D - p.y}`).join(" ");
  return (
    <svg
      viewBox={`${-pad} ${-pad} ${W + pad * 2} ${D + pad * 2}`}
      className={className}
      role="img"
      aria-label={t("케이지 {w}×{d}mm 배치를 위에서 본 그림, 구조물 {n}개", {
        w: W,
        d: D,
        n: layout.items.filter((it) => !isFloorLayer(getAsset(it.asset))).length,
      })}
    >
      <rect x={0} y={0} width={W} height={D} fill={bedding?.color ?? "#f6ead3"} stroke="#6b8fb5" strokeWidth={Math.max(W, D) * 0.004} />
      <rect x={0} y={D - Math.max(4, D * 0.012)} width={W} height={Math.max(4, D * 0.012)} fill="#f59e0b" />
      {layout.items.map((it) => {
        const a = getAsset(it.asset);
        if (a && isFloorLayer(a)) return null;
        if (!a) {
          // 불러오지 못한 파일 에셋 등: 자리만 표시
          return (
            <circle key={it.id} cx={it.x_mm} cy={D - it.y_mm} r={Math.min(W, D) * 0.04} fill={fileIdOf(it.asset) ? "#b8a6e0" : "#d6d3d1"} stroke="#78716c" strokeWidth={1} />
          );
        }
        return <polygon key={it.id} points={pts(footprint(it, a))} fill={a.color} stroke="#57534e" strokeOpacity={0.5} strokeWidth={Math.max(W, D) * 0.003} />;
      })}
    </svg>
  );
}
