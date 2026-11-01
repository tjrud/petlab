// 백엔드 API 스키마 (backend/app/schemas.py) 와 맞춘 타입

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
  habitat: Habitat;
  versions: VersionSummary[];
  current: Version;
};
