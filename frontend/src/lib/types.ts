// 백엔드 API 스키마 (backend/app/schemas.py) 와 맞춘 타입

export type Role = "member" | "admin";

export type User = { id: string; username: string; nickname: string; role: Role; created_at: string };

export type AuthStatus = {
  auth_enabled: boolean;
  authenticated: boolean;
  user: User | null;
  signup_enabled: boolean;
};

export type Me = {
  user: User;
  stats: { pets: number; designs: number; posts: number };
  /** 최근 24시간 설계 사용량. 관리자는 limit/remaining 이 null (상한 없음) */
  design_quota: { used: number; limit: number | null; remaining: number | null };
};

export type Cage = { width_mm: number; depth_mm: number; height_mm: number };

export type SizeOption = {
  key: string;
  display_name: string;
  max_recommended_count: number;
  count_warning_ko: string;
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
  versions: VersionSummary[];
  current: Version;
  /** 수정·공유는 소유자(또는 관리자)만. 커뮤니티에 공유된 남의 설계는 false (읽기 전용) */
  is_owner: boolean;
  shared: boolean;
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

export type PostSummary = {
  id: string;
  title: string;
  excerpt: string;
  author: Author;
  created_at: string;
  comment_count: number;
  has_design: boolean;
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
  comments: Comment[];
  can_edit: boolean;
  can_delete: boolean;
};
