// 백엔드 API 스키마 (backend/app/schemas.py) 와 맞춘 타입

import type { ParamValue } from "@/lib/templates";

export type Role = "member" | "admin";

export type User = {
  id: string;
  username: string;
  nickname: string;
  role: Role;
  created_at: string;
  /** 이 기능 전에 가입한 회원은 없을 수 있다. 관리자는 null */
  email: string | null;
  /** 관리자는 늘 true */
  email_verified: boolean;
};

/** 회원가입 보안 확인 (Cloudflare Turnstile) */
export type CaptchaConfig = { provider: "turnstile"; site_key: string };

export type AuthStatus = {
  auth_enabled: boolean;
  authenticated: boolean;
  user: User | null;
  signup_enabled: boolean;
  /** 서버가 이메일 인증을 요구하는지 (인증 전 회원은 설계·글쓰기·댓글·제작 신청을 못 한다) */
  email_verification: boolean;
  /** 회원가입에 보안 확인이 필요하면 설정, 아니면 null */
  captcha: CaptchaConfig | null;
};

/** 회원가입·이메일 변경 응답: 로그인 상태와 인증 메일 발송 결과 (이메일 인증을 쓰지 않으면 null) */
export type AuthStatusWithMail = AuthStatus & { verification_email_sent: boolean | null };

export type SignupInput = {
  username: string;
  nickname: string;
  password: string;
  email?: string;
  captcha_token?: string;
};

export type VerifyEmailResult = { ok: true; message_ko: string };

export type ResendVerificationResult = { sent: boolean; email: string; message_ko: string };

export type Me = {
  user: User;
  stats: { pets: number; designs: number; posts: number };
  /** 최근 24시간 설계 사용량. 관리자는 limit/remaining 이 null (상한 없음) */
  design_quota: { used: number; limit: number | null; remaining: number | null };
};

export type Cage = { width_mm: number; depth_mm: number; height_mm: number };

/** 사육 환경 종류: 케이지 / 어항 (어항이면 사육 환경의 높이는 물 깊이: 바닥재 위~수면) */
export type HabitatKind = "cage" | "aquarium";

/** 가상 케이지 배치 검토에 쓰는 종·크기별 규칙 값 (backend/rules/species.yaml). 케이지 종에만 있다 */
export type LayoutRules = {
  gap_safe_max_mm: number;
  gap_passable_min_mm: number;
  entrance_min_diameter_mm: number;
  tunnel_min_inner_diameter_mm: number;
  /** 터널 권장 최대 길이 mm (이 크기 구분에서 가장 작은 개체 몸길이의 2배, 독일 동물보호연맹 기준). 옛 서버 응답에는 없을 수 있고, 기준이 없으면 null */
  tunnel_max_length_mm?: number | null;
  /** 오르는 구조물 최대 높이 mm (경사로를 만들 수 없는 종이면 null) */
  max_climb_height_mm: number | null;
  /** 한 번에 넘는 최대 턱 높이 mm (기준이 없으면 null) */
  max_step_height_mm: number | null;
  /** 은신처 출입구 최소 개수 (혼자 키울 때) */
  hideout_min_entrances: number;
  /** 은신처 출입구 최소 개수 (여러 마리를 함께 키울 때, 서로 피할 수 있도록) */
  hideout_min_entrances_group?: number;
  /** 모래목욕통 최소 안쪽 크기 [가로, 세로] mm (모래목욕통을 만들 수 없는 종이면 null) */
  sand_bath_min_inner_mm: [number, number] | null;
  /** 사육장 최소 바닥 기준 [긴 변, 짧은 변] mm (기준이 없으면 null) */
  enclosure_min_floor_mm: [number, number] | null;
};

/** 어항 크기 구분의 기준 (케이지 종은 null) */
export type AquaticRules = {
  /** 동굴 안쪽 천장 최소 경사 ° */
  ceiling_min_slope_deg: number;
  /** 구조물 위에 남겨야 하는 최소 물 깊이 mm */
  structure_top_clearance_mm: number;
  /** 수조 부피를 어림할 때 더하는 바닥재 두께 mm */
  substrate_depth_assumed_mm: number;
  /** 수조 부피를 어림할 때 더하는 수면 위 여유 mm */
  air_gap_mm: number;
  /**
   * 수조 유리 두께 어림 mm. 입력은 수조 안쪽 치수인데 바닥·부피 기준은 겉 크기라, 비교할 때만 더한다
   * (옛 서버 응답에는 없을 수 있어요 → 0)
   */
  glass_thickness_assumed_mm?: number;
  /** 수조 최소 부피 L */
  min_volume_l: number;
  /** 마리당 필요한 부피 L (출처가 없으면 null: 마릿수 비례 부피는 보지 않는다) */
  volume_l_per_animal: number | null;
  /** 구조물 높이 ÷ 바닥 짧은 변 최대 비율 (넘어짐) */
  max_height_to_base_ratio: number;
};

export type SizeOption = {
  key: string;
  display_name: string;
  /** 권장 최대 마릿수와 넘을 때의 경고 (없으면 null) */
  max_recommended_count: number | null;
  count_warning_ko: string | null;
  /** 권장 최소 마릿수와 모자랄 때의 경고 (없으면 null, 옛 서버 응답에는 없을 수 있어요) */
  min_recommended_count?: number | null;
  min_count_warning_ko?: string | null;
  /** 사육장 최소 바닥 기준 [긴 변, 짧은 변] mm (없으면 null) */
  enclosure_min_floor_mm: [number, number] | null;
  /** 가상 케이지 검토 기준 (어항 종은 null) */
  layout_rules: LayoutRules | null;
  /** 어항 기준 (케이지 종은 null, 옛 서버 응답에는 없을 수 있어요) */
  aquatic?: AquaticRules | null;
};

export type SpeciesOption = {
  key: string;
  display_name: string;
  sizes: SizeOption[];
  /** 사육 환경 (옛 서버 응답에는 없을 수 있어요 → 케이지) */
  habitat?: HabitatKind;
  /** 이 종에 만들 수 있는 구조물 (템플릿 키) */
  templates?: string[];
  /** 입력할 수 있는 최대 마릿수 (없으면 10) */
  max_count?: number;
  /** 출력·설치 안내 (영어 화면이면 서버가 항목마다 번역해 보낸다) */
  print_notes_ko?: string[];
  /** 크기 구분을 고를 때 보일 안내 (어항: 몸길이 기준·아주 작은 종). 없으면 null, 영어 화면이면 서버가 번역해 보낸다 */
  size_hint_ko?: string | null;
};

export type SpeciesResponse = {
  rules_reviewed: boolean;
  llm_provider: "anthropic" | "mock";
  storage_persistent: boolean;
  species: SpeciesOption[];
};

export type Habitat = {
  id: string;
  pet_id: string | null;
  species: string;
  species_name_ko: string;
  size: string;
  size_name_ko: string;
  count: number;
  cage: Cage;
  created_at: string;
  /** 사육 환경 종류 (옛 서버 응답에는 없을 수 있어요 → 케이지) */
  habitat_kind?: HabitatKind;
};

export type Placement = { x_mm: number; y_mm: number; rotation_deg: number };

/** 출력 파트 하나 (집처럼 조립형 구조물은 본체·지붕·층판 등 여러 개) */
export type ItemPart = { key: string; name_ko: string; size_mm: number[] };

/** 장식 명세: 무늬 또는 글귀 각인 (backend/app/templates/decor.py) */
export type PatternDecor = {
  kind: "pattern";
  pattern: "stripes" | "dots" | "scales" | "brick" | "wave" | "honeycomb";
  density: 1 | 2 | 3;
  direction: 0 | 45 | 90;
  depth_mm: number;
  face: "walls" | "front" | "back" | "left" | "right" | "roof";
  mode: "engrave" | "relief";
};
export type TextDecor = {
  kind: "text";
  text: string;
  face: "front" | "back" | "left" | "right" | "roof";
  height_mm: number;
  depth_mm: number;
};
export type Decor = PatternDecor | TextDecor;

export type Item = {
  index: number;
  template: string;
  label_ko: string;
  /** 집(house) 템플릿은 부품별로 중첩된 값, 면 목록(string[]), 참/거짓도 들어 있다 */
  params: Record<string, ParamValue>;
  reason_ko: string;
  placement: Placement | null;
  size_mm: number[];
  /** 출력 자세 크기 (파트가 여럿이면 본체) */
  print_size_mm: number[];
  mesh_url: string | null;
  /** 출력 파트. 옛 서버 응답에는 없을 수 있어요 (그러면 본체 하나) */
  parts?: ItemPart[];
  /** 장식 (무늬·글귀 각인). 없으면 null. 줄이거나 뺀 경우는 검증 이슈(decor_reduced·decor_skipped)로 온다 */
  decor?: Decor | null;
};

export type Severity = "error" | "warning" | "info";

export type Issue = {
  code: string;
  severity: Severity;
  message_ko: string;
  item_index: number | null;
  related_index: number | null;
  auto_fixed: boolean;
  details: Record<string, unknown>;
};

export type Validation = {
  passed: boolean;
  summary: { errors: number; warnings: number; auto_fixed: number };
  issues: Issue[];
};

export type VersionSummary = {
  version: number;
  prompt: string;
  passed: boolean;
  provider: string;
  created_at: string;
};

export type Version = {
  version: number;
  prompt: string;
  provider: string;
  summary_ko: string;
  notes_ko: string[];
  items: Item[];
  validation: Validation;
  export_allowed: boolean;
  created_at: string;
};

export type Design = {
  id: string;
  title: string;
  habitat: Habitat;
  /** 소유자는 모든 버전. 다른 사람(관리자 포함)에게는 커뮤니티 글에 첨부된 버전만 온다 */
  versions: VersionSummary[];
  /** 다른 사람에게는 기본으로 가장 최근에 공유된 버전 */
  current: Version;
  /** 수정·공유는 실제 소유자만. 남의 설계는 관리자가 보더라도 false (읽기 전용) */
  is_owner: boolean;
  shared: boolean;
  /** 커뮤니티 글에 첨부된 버전 번호 (오름차순, 없으면 빈 배열). 이 버전들만 다른 사람이 볼 수 있다 */
  shared_versions: number[];
  owner_nickname: string | null;
};

export type DesignListItem = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  version_count: number;
  latest_version: number;
  latest_passed: boolean;
  habitat: Habitat;
  pet_name: string | null;
  shared: boolean;
};

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number };

export type PetSex = "male" | "female" | "unknown";

export type Pet = {
  id: string;
  name: string;
  species: string;
  species_name_ko: string;
  size: string;
  size_name_ko: string;
  sex: PetSex;
  birth_date: string | null; // YYYY-MM-DD
  notes: string | null;
  cage: Cage | null;
  created_at: string;
  updated_at: string;
  /** 사육 환경 종류 (옛 서버 응답에는 없을 수 있어요 → 케이지) */
  habitat_kind?: HabitatKind;
};

export type PetInput = {
  name: string;
  species: string;
  size: string;
  sex: PetSex;
  birth_date: string | null;
  notes: string | null;
  cage: Cage | null;
};

export type Author = { nickname: string; role: Role };

/** 글 사진 (사이트에 함께 배포한 파일, 촬영자·라이선스·원본 주소를 함께 보여 준다) */
export type PostImage = {
  src: string;
  alt: string;
  width: number;
  height: number;
  credit: string;
  license: string;
  source_url: string;
};

export type PostSummary = {
  id: string;
  title: string;
  excerpt: string;
  author: Author;
  created_at: string;
  comment_count: number;
  has_design: boolean;
  /** 첫 사진 (없으면 null) */
  thumbnail: PostImage | null;
  /** 공유 작품 소개 글이면 그 작품 ID */
  market_item_id: string | null;
};

export type Comment = { id: string; body: string; author: Author; created_at: string; can_delete: boolean };

export type SharedDesign = {
  id: string;
  version: number;
  title: string;
  summary_ko: string;
  item_labels: string[];
  passed: boolean;
  habitat: Habitat;
};

export type Post = {
  id: string;
  title: string;
  body: string;
  author: Author;
  created_at: string;
  updated_at: string;
  design: SharedDesign | null;
  /** 운영팀 글의 사진 (없으면 빈 배열) */
  images: PostImage[];
  /** 공유 작품 소개 글이면 그 작품 요약 */
  market_item: MarketItemBrief | null;
  /** 최근 댓글 최대 200개 (오래된 것부터). 전체 개수는 comment_total */
  comments: Comment[];
  comment_total: number;
  can_edit: boolean;
  can_delete: boolean;
};

// ── 가상 케이지 배치안 ──

/** 배치한 에셋 하나. 좌표는 케이지 좌표계(mm, 원점=앞-왼쪽 바닥 모서리)의 에셋 바닥 중심, 회전은 위에서 볼 때 반시계 방향 */
export type LayoutItem = { id: string; asset: string; x_mm: number; y_mm: number; rotation_deg: number };

export type CageLayoutSummary = {
  id: string;
  name: string;
  species: string;
  size: string;
  size_name_ko: string;
  pet_id: string | null;
  cage: Cage;
  item_count: number;
  created_at: string;
  updated_at: string;
  /** 사육 환경 종류 (가상 케이지는 케이지 종만 저장해요. 옛 서버 응답에는 없을 수 있어요) */
  habitat_kind?: HabitatKind;
};

export type CageLayout = CageLayoutSummary & { items: LayoutItem[] };

export type CageLayoutInput = {
  name: string;
  species: string;
  size: string;
  cage: Cage;
  pet_id: string | null;
  items: LayoutItem[];
};

// ── 탐색 ──

export type MarketCategory = "hideout" | "tunnel" | "ramp" | "sand_bath" | "cage" | "layout" | "etc";

export type MarketConfig = {
  uploads_enabled: boolean;
  chunk_bytes: number;
  max_model_bytes: number;
  max_image_bytes: number;
  model_formats: string[];
  image_formats: string[];
  categories: { key: MarketCategory; name_ko: string }[];
};

export type MarketFile = {
  id: string;
  kind: "model" | "image";
  filename: string;
  format: string;
  size: number;
  sha256: string;
  /** "/" 로 시작하면 API 기준 경로, 아니면 공개 주소 */
  download_url: string;
  view_url: string | null;
  /** STL·3MF: 외곽 크기 [x, y, z] mm (SKP 는 null) */
  dims_mm: [number, number, number] | null;
  /** STL·3MF: 3D 로 불러올 주소 ("/" 로 시작하면 API 경로) */
  mesh_url: string | null;
  /** 3D 미리보기용 가벼운 메시(NFM1)와 그 크기 (있으면 원본 대신 받는다) */
  preview_url: string | null;
  preview_size: number | null;
  /** 작품에 붙었거나 공유한 배치에 들어 있어 누구나 볼 수 있는지 */
  attached: boolean;
};

/** 탐색에 공유한 가상 케이지 배치 (공유할 때의 배치안 사본) */
export type LayoutSnapshot = {
  name: string;
  species: string;
  size: string;
  size_name_ko: string;
  cage: Cage;
  items: LayoutItem[];
  /** 사육 환경 종류 (옛 서버 응답에는 없을 수 있어요 → 케이지) */
  habitat_kind?: HabitatKind;
};

export type MarketItemSummary = {
  id: string;
  title: string;
  category: MarketCategory;
  category_name_ko: string;
  author: Author;
  /** 파일 형식 (skp·3mf·stl) + NestForge 설계면 "nestforge" */
  formats: string[];
  image: MarketFile | null;
  has_design: boolean;
  has_layout: boolean;
  download_count: number;
  created_at: string;
  /** 추천 목록에서만: 추천한 까닭 */
  reason_ko?: string | null;
};

export type MarketItem = MarketItemSummary & {
  description: string;
  files: MarketFile[];
  design: SharedDesign | null;
  layout: LayoutSnapshot | null;
  post_id: string | null;
  updated_at: string;
  can_edit: boolean;
  can_delete: boolean;
};

export type MarketItemBrief = { id: string; title: string; formats: string[]; image: MarketFile | null };

export type MarketItemInput = {
  title: string;
  description: string;
  category: MarketCategory;
  file_ids: string[];
  image_file_id: string | null;
  layout_id: string | null;
  post_to_community: boolean;
};
