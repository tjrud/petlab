import type { AuthStatus, Cage, Design, Habitat, SpeciesResponse } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** 사용자에게 그대로 보여줄 수 있는 메시지(message_ko)를 담은 오류 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public messageKo: string,
    public code?: string,
    public details?: unknown,
  ) {
    super(messageKo);
  }
}

const FALLBACK_MESSAGE = "서버와 통신하지 못했어요. 잠시 후 다시 시도해 주세요.";

/** 관리자 로그인이 필요한 API 를 로그인 없이 호출했을 때 로그인 화면으로 보낸다. */
function redirectToLogin() {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  const next = window.location.pathname + window.location.search;
  // 전체 새로고침으로 이동 (현재 화면 상태를 버리고 로그인 후 원래 경로로 돌아온다).
  // React 컴포넌트 밖의 공용 함수라 router 를 쓸 수 없다.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.href = `/login?next=${encodeURIComponent(next)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include", // 관리자 세션 쿠키 (로컬 개발처럼 출처가 달라도 전송)
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, FALLBACK_MESSAGE);
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* 본문 없음 */
    }
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail) && "message_ko" in detail) {
      const d = detail as { message_ko: string; code?: string; errors?: unknown };
      if (res.status === 401 && d.code === "auth_required") redirectToLogin();
      throw new ApiError(res.status, d.message_ko, d.code, d.errors);
    }
    if (res.status === 422) {
      throw new ApiError(422, "입력값을 확인해 주세요.", "validation_error", detail);
    }
    throw new ApiError(res.status, FALLBACK_MESSAGE);
  }
  return (await res.json()) as T;
}

export const api = {
  authStatus: () => request<AuthStatus>("/auth/me"),
  login: (username: string, password: string) =>
    request<AuthStatus>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request<AuthStatus>("/auth/logout", { method: "POST" }),
  species: () => request<SpeciesResponse>("/species"),
  createHabitat: (body: { species: string; size: string; count: number; cage: Cage }) =>
    request<Habitat>("/habitats", { method: "POST", body: JSON.stringify(body) }),
  createDesign: (habitatId: string, prompt: string) =>
    request<Design>("/designs", { method: "POST", body: JSON.stringify({ habitat_id: habitatId, prompt }) }),
  getDesign: (id: string, version?: number) =>
    request<Design>(`/designs/${encodeURIComponent(id)}${version ? `?version=${version}` : ""}`),
  reviseDesign: (id: string, prompt: string, baseVersion?: number) =>
    request<Design>(`/designs/${encodeURIComponent(id)}/revise`, {
      method: "POST",
      body: JSON.stringify({ prompt, base_version: baseVersion ?? null }),
    }),
  joinWaitlist: (email: string, designId?: string, version?: number) =>
    request<{ ok: boolean; message_ko: string }>("/waitlist", {
      method: "POST",
      body: JSON.stringify({ email, design_id: designId ?? null, version: version ?? null }),
    }),
  exportUrl: (id: string, format: "stl" | "3mf", version: number) =>
    `${API_BASE}/designs/${encodeURIComponent(id)}/export?format=${format}&version=${version}`,
  meshUrl: (path: string) => `${API_BASE}${path}`,
};
