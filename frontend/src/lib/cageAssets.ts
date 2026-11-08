// 가상 케이지 기본 에셋 카탈로그.
//
// 시중에서 흔히 쓰는 햄스터 용품 크기를 기준으로 한 대표 치수예요 (실제 제품마다 다르니 배치 검토용 근사치).
// 치수는 사용 자세 기준 [가로(x), 세로(y), 높이(z)] mm, 회전 0° 일 때 앞(관찰 면)이 -y 쪽이에요.
// 서버는 에셋 키만 저장하므로, 키를 바꾸거나 지우면 저장된 배치안에서 그 항목을 불러오지 못해요 (새 키를 추가하세요).

export type AssetCategory = "hide" | "play" | "climb" | "feed" | "care" | "floor";

export type Side = "front" | "back" | "left" | "right";

/** 화면이 그리는 모양 (components/cage/AssetModel.tsx) */
export type AssetShape =
  | "house"
  | "multi_room"
  | "log_arch"
  | "tunnel"
  | "wheel"
  | "platform"
  | "ramp"
  | "bridge"
  | "stone"
  | "tray"
  | "corner_house"
  | "bowl"
  | "water_stand"
  | "plate"
  | "bedding"
  | "mesh";

export type CageAsset = {
  key: string;
  name: string;
  category: AssetCategory;
  shape: AssetShape;
  /** [가로, 세로, 높이] mm */
  size: [number, number, number];
  color: string;
  description: string;
  /** 드나드는 면. 앞에 동물이 지나갈 공간이 비어 있어야 해요 */
  accessSides?: Side[];
  /** 출입구(또는 터널 안쪽) 폭 mm: 종별 최소 폭과 비교해요 */
  entranceMm?: number;
  /** 터널처럼 몸 전체가 지나가는 통로면 true (터널 최소 내경 기준으로 비교) */
  isTunnel?: boolean;
  /** 터널 길이 mm: 종별 최대 길이(몸길이의 2배)와 비교해요 */
  tunnelLengthMm?: number;
  /** 동물이 올라가는 높이 mm (플랫폼·경사로·다리·디딤돌): 종별 최대 높이와 비교해요 */
  climbHeightMm?: number;
  /** 넘어 들어가야 하는 턱 높이 mm (목욕통·땅굴 상자): 종별 최대 턱 높이와 비교해요 */
  stepHeightMm?: number;
  /** 은신처 출입구 개수: 종별 최소 개수와 비교해요 (출입구가 하나면 막다른 곳이 돼요) */
  entranceCount?: number;
  /** 모래목욕통 안쪽 [가로, 세로] mm: 종별 최소 크기와 비교해요 */
  sandBathInnerMm?: [number, number];
  /**
   * 바닥재: 케이지 바닥 전체를 덮는 층 (size 의 높이 = 깊이, 가로·세로는 카탈로그 미리보기용).
   * 한 번에 하나만 깔고, 겹침·자리 찾기에서 빼요. 다른 구조물은 바닥재 위에 놓여요
   */
  floorLayer?: { flakeColor: string };
  /** 내가 올린 STL·3MF 파일 (shape "mesh"): 3D 로 불러올 주소와 형식. 크기는 파일의 외곽 크기 */
  mesh?: { url: string; format: "stl" | "3mf"; fileId: string };
};

export const CATEGORIES: { key: AssetCategory; label: string }[] = [
  { key: "hide", label: "은신처" },
  { key: "play", label: "놀이·운동" },
  { key: "climb", label: "지형·층" },
  { key: "feed", label: "급식·급수" },
  { key: "care", label: "위생·휴식" },
  { key: "floor", label: "바닥재" },
];

export const CAGE_ASSETS: CageAsset[] = [
  // 은신처
  {
    key: "hideout_house",
    name: "나무 은신처",
    category: "hide",
    shape: "house",
    size: [180, 140, 130],
    color: "#d9a066",
    description: "지붕 있는 1인용 집. 앞쪽 아치 출입구",
    accessSides: ["front"],
    entranceMm: 75,
    entranceCount: 1,
  },
  {
    key: "hideout_multi",
    name: "다방 은신처",
    category: "hide",
    shape: "multi_room",
    size: [300, 200, 140],
    color: "#c98f55",
    description: "방이 나뉜 큰 은신처. 앞쪽 출입구 2개",
    accessSides: ["front"],
    entranceMm: 75,
    entranceCount: 2,
  },
  {
    key: "hideout_log",
    name: "통나무 아치",
    category: "hide",
    shape: "log_arch",
    size: [220, 130, 100],
    color: "#a8753f",
    description: "앞뒤가 뚫린 반원형 굴",
    accessSides: ["front", "back"],
    entranceMm: 80,
    entranceCount: 2,
  },
  {
    key: "hideout_corner",
    name: "코너 은신처",
    category: "hide",
    shape: "corner_house",
    size: [170, 170, 120],
    color: "#e0b27c",
    description: "모서리에 붙여 쓰는 삼각 지붕 집",
    accessSides: ["front"],
    entranceMm: 75,
    entranceCount: 1,
  },
  // 놀이·운동
  {
    key: "wheel_210",
    name: "21cm 쳇바퀴",
    category: "play",
    shape: "wheel",
    size: [230, 130, 250],
    color: "#7fb0a0",
    description: "지름 21cm 바퀴 + 받침대. 앞쪽으로 타고 내려요",
    accessSides: ["front"],
  },
  {
    key: "wheel_280",
    name: "28cm 쳇바퀴",
    category: "play",
    shape: "wheel",
    size: [300, 140, 320],
    color: "#5f9c8a",
    description: "지름 28cm 바퀴 + 받침대. 앞쪽으로 타고 내려요",
    accessSides: ["front"],
  },
  {
    key: "tunnel_straight",
    name: "일자 터널",
    category: "play",
    shape: "tunnel",
    size: [300, 100, 100],
    color: "#8fb8d0",
    description: "양 끝(좌우)이 뚫린 원통 터널. 안지름 80mm",
    accessSides: ["left", "right"],
    entranceMm: 80,
    isTunnel: true,
    tunnelLengthMm: 300,
  },
  {
    key: "dig_box",
    name: "땅굴 상자",
    category: "play",
    shape: "tray",
    size: [300, 200, 150],
    color: "#c4a484",
    description: "깊게 파고들 수 있는 바닥재 상자. 앞쪽 턱 30mm",
    stepHeightMm: 30,
  },
  // 지형·층
  {
    key: "platform",
    name: "2층 플랫폼",
    category: "climb",
    shape: "platform",
    size: [250, 180, 150],
    color: "#b99ad6",
    description: "다리 4개로 받친 높이 15cm 선반 (아래는 비워 둬요)",
    climbHeightMm: 150,
  },
  {
    key: "ramp",
    name: "경사로",
    category: "climb",
    shape: "ramp",
    size: [250, 90, 100],
    color: "#a487c7",
    description: "왼쪽이 낮고 오른쪽 끝이 10cm 높이",
    accessSides: ["left"],
    climbHeightMm: 100,
  },
  {
    key: "bridge",
    name: "아치 다리",
    category: "climb",
    shape: "bridge",
    size: [300, 100, 80],
    color: "#c9a27a",
    description: "나무 조각을 엮은 휘어지는 다리. 좌우로 건너요",
    accessSides: ["left", "right"],
    climbHeightMm: 80,
  },
  {
    key: "stone_step",
    name: "디딤돌",
    category: "climb",
    shape: "stone",
    size: [120, 100, 60],
    color: "#a8a29e",
    description: "높이 6cm 돌. 올라서거나 건너뛰어요",
    climbHeightMm: 60,
  },
  // 급식·급수
  {
    key: "bowl",
    name: "밥그릇",
    category: "feed",
    shape: "bowl",
    size: [100, 100, 35],
    color: "#f2c6a0",
    description: "지름 10cm 도자기 그릇",
  },
  {
    key: "water_stand",
    name: "스탠드 급수기",
    category: "feed",
    shape: "water_stand",
    size: [100, 100, 180],
    color: "#9ccbe8",
    description: "받침대에 세우는 물병. 앞쪽 꼭지로 마셔요",
    accessSides: ["front"],
  },
  // 위생·휴식
  {
    key: "sand_bath",
    name: "모래목욕통",
    category: "care",
    shape: "tray",
    size: [240, 220, 70],
    color: "#e6cf8f",
    description: "모래를 담는 낮은 통. 안쪽 22×20cm, 턱 높이 30mm",
    stepHeightMm: 30,
    sandBathInnerMm: [224, 204],
  },
  {
    key: "toilet_corner",
    name: "코너 화장실",
    category: "care",
    shape: "corner_house",
    size: [160, 160, 110],
    color: "#f0e2b6",
    description: "모서리용 덮개형 화장실. 앞쪽 출입구",
    accessSides: ["front"],
    entranceMm: 75,
  },
  {
    key: "cooling_plate",
    name: "쿨링 대리석",
    category: "care",
    shape: "plate",
    size: [200, 150, 15],
    color: "#e7e5e4",
    description: "더운 날 엎드려 쉬는 얇은 판",
  },
  // 바닥재 (바닥 전체)
  {
    key: "bedding_shavings_5",
    name: "톱밥 바닥재 5cm",
    category: "floor",
    shape: "bedding",
    size: [300, 200, 50],
    color: "#e8d2a4",
    description: "바닥 전체에 5cm 깔아요. 구조물은 바닥재 위에 놓여요",
    floorLayer: { flakeColor: "#cfae78" },
  },
  {
    key: "bedding_shavings_15",
    name: "톱밥 바닥재 15cm",
    category: "floor",
    shape: "bedding",
    size: [300, 200, 150],
    color: "#e8d2a4",
    description: "굴을 팔 수 있게 15cm 깊게 깔아요. 그만큼 위 공간이 줄어요",
    floorLayer: { flakeColor: "#cfae78" },
  },
  {
    key: "bedding_paper_5",
    name: "종이 깔짚 5cm",
    category: "floor",
    shape: "bedding",
    size: [300, 200, 50],
    color: "#f2ede3",
    description: "먼지가 적은 종이 깔짚을 바닥 전체에 5cm 깔아요",
    floorLayer: { flakeColor: "#dcd3c2" },
  },
];

const BY_KEY = new Map(CAGE_ASSETS.map((a) => [a.key, a]));

export function getAsset(key: string): CageAsset | undefined {
  return BY_KEY.get(key) ?? FILE_ASSETS.get(key);
}

// ── 파일 에셋 (탐색에 올라온 STL·3MF) ──
// 배치안에는 "file_<파일 ID>" 키로 저장하고, 화면은 파일 정보를 받아 이 표에 넣은 뒤 다른 에셋처럼 쓴다.

export const FILE_ASSET_PREFIX = "file_";
const FILE_ASSETS = new Map<string, CageAsset>();

export const fileAssetKey = (fileId: string) => `${FILE_ASSET_PREFIX}${fileId}`;
export const fileIdOf = (key: string) => (key.startsWith(FILE_ASSET_PREFIX) ? key.slice(FILE_ASSET_PREFIX.length) : null);

/** 파일 정보로 에셋을 만들어 넣는다 (3D 로 볼 수 없는 SKP·크기를 모르는 파일은 넣지 않는다). 넣었으면 그 에셋 */
export function registerFileAsset(f: {
  id: string;
  filename: string;
  format: string;
  dims_mm: [number, number, number] | null;
  mesh_url: string | null;
}, meshUrl: (path: string) => string): CageAsset | null {
  if (!f.dims_mm || !f.mesh_url || (f.format !== "stl" && f.format !== "3mf")) return null;
  const key = fileAssetKey(f.id);
  const asset: CageAsset = {
    key,
    name: f.filename.replace(/\.[^.]+$/, "") || "내 파일",
    category: "hide",
    shape: "mesh",
    size: [f.dims_mm[0], f.dims_mm[1], f.dims_mm[2]],
    color: "#b8a6e0",
    description: `올린 ${f.format.toUpperCase()} 파일 (실제 크기)`,
    mesh: { url: meshUrl(f.mesh_url), format: f.format, fileId: f.id },
  };
  FILE_ASSETS.set(key, asset);
  return asset;
}

/** 바닥 전체를 덮는 바닥재인지 */
export function isFloorLayer(a: CageAsset | undefined): boolean {
  return a?.floorLayer !== undefined;
}

/** 깔아 둔 바닥재의 깊이 mm (없으면 0). 구조물은 이 높이 위에 놓여요 */
export function beddingDepth(items: { asset: string }[]): number {
  let depth = 0;
  for (const it of items) {
    const a = getAsset(it.asset);
    if (a?.floorLayer) depth = Math.max(depth, a.size[2]);
  }
  return depth;
}
