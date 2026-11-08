// 백엔드 API 스키마 (backend/app/schemas.py) 와 맞춘 타입

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

/** 가상 케이지 배치 검토에 쓰는 종·크기별 규칙 값 (backend/rules/species.yaml) */
export type LayoutRules = {
  gap_safe_max_mm: number;
  gap_passable_min_mm: number;
  entrance_min_diameter_mm: number;
  tunnel_min_inner_diameter_mm: number;
  /** 터널 권장 최대 길이 mm (이 크기 구분에서 가장 작은 개체 몸길이의 2배, 독일 동물보호연맹 기준). 옛 서버 응답에는 없을 수 있어요 */
  tunnel_max_length_mm?: number;
  max_climb_height_mm: number;
  max_step_height_mm: number;
  /** 은신처 출입구 최소 개수 (혼자 키울 때) */
  hideout_min_entrances: number;
  /** 은신처 출입구 최소 개수 (여러 마리를 함께 키울 때, 서로 피할 수 있도록) */
  hideout_min_entrances_group?: number;
  /** 모래목욕통 최소 안쪽 크기 [가로, 세로] mm */
  sand_bath_min_inner_mm: [number, number];
  /** 사육장 최소 바닥 기준 [긴 변, 짧은 변] mm */
  enclosure_min_floor_mm: [number, number];
};

export type SizeOption = {
  key: string;
  display_name: string;
  max_recommended_count: number;
  count_warning_ko: string;
  /** 사육장 최소 바닥 기준 [긴 변, 짧은 변] mm */
  enclosure_min_floor_mm: [number, number];
  layout_rules: LayoutRules;
};

export type SpeciesOption = { key: string; display_name: string; sizes: SizeOption[] };

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
};

export type Placement = { x_mm: number; y_mm: number; rotation_deg: number };

export type Item = {
  index: number;
  template: string;
  label_ko: string;
  params: Record<string, number>;
  reason_ko: string;
  placement: Placement | null;
  size_mm: number[];
  print_size_mm: number[];
  mesh_url: string | null;
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
