import type {
  AuthStatus,
  Cage,
  Comment,
  Design,
  DesignListItem,
  Habitat,
  Me,
  Paged,
  Pet,
  PetInput,
  Post,
  PostSummary,
  SpeciesResponse,
} from "./types";

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

/** 로그인이 필요해서(또는 로그인 설정 문제로) 실패한 요청인지 */
export function isAuthError(e: unknown): boolean {
  return e instanceof ApiError && (e.code === "auth_required" || e.code === "auth_unavailable");
}

/**
 * 요청이 로그인 문제(isAuthError)로 실패하면 window 에 보내는 이벤트.
 * AuthProvider 가 받아서 로그인 상태를 서버에 다시 묻는다 (세션 만료·다른 기기에서 비밀번호 변경 등).
 */
export const AUTH_ERROR_EVENT = "nestforge:auth-error";

async function errorFrom(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* 본문 없음 */
  }
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "message_ko" in detail) {
    const d = detail as { message_ko: string; code?: string; errors?: unknown };
    return new ApiError(res.status, d.message_ko, d.code, d.errors);
  }
  if (res.status === 422) return new ApiError(422, "입력값을 확인해 주세요.", "validation_error", detail);
  return new ApiError(res.status, FALLBACK_MESSAGE);
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
    const err = await errorFrom(res);
    // /auth/* (로그인 상태 확인·로그인·로그아웃) 실패는 알리지 않는다: 다시 확인하는 요청이 또 이벤트를 보내 끝없이 되풀이되지 않게
    if (isAuthError(err) && !path.startsWith("/auth/") && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_ERROR_EVENT));
    }
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  // 회원
  authStatus: () => request<AuthStatus>("/auth/me"),
  login: (username: string, password: string) => request<AuthStatus>("/auth/login", json("POST", { username, password })),
  signup: (username: string, nickname: string, password: string) =>
    request<AuthStatus>("/auth/signup", json("POST", { username, nickname, password })),
  logout: () => request<AuthStatus>("/auth/logout", json("POST", {})),
  me: () => request<Me>("/me"),
  updateProfile: (nickname: string) => request<AuthStatus>("/me", json("PATCH", { nickname })),
  changePassword: (current_password: string, new_password: string) =>
    request<AuthStatus>("/me/password", json("POST", { current_password, new_password })),

  // 반려동물
  pets: () => request<Pet[]>("/me/pets"),
  createPet: (body: PetInput) => request<Pet>("/me/pets", json("POST", body)),
  updatePet: (id: string, body: PetInput) => request<Pet>(`/me/pets/${encodeURIComponent(id)}`, json("PUT", body)),
  deletePet: (id: string) => request<void>(`/me/pets/${encodeURIComponent(id)}`, json("DELETE")),

  // 설계
  species: () => request<SpeciesResponse>("/species"),
  createHabitat: (body: { species: string; size: string; count: number; cage: Cage; pet_id?: string | null }) =>
    request<Habitat>("/habitats", { method: "POST", body: JSON.stringify(body) }),
  listDesigns: (page = 1, pageSize = 12) =>
    request<Paged<DesignListItem>>(`/designs?page=${page}&page_size=${pageSize}`),
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

  // 커뮤니티 (읽기는 누구나)
  posts: (page = 1, pageSize = 20) => request<Paged<PostSummary>>(`/community/posts?page=${page}&page_size=${pageSize}`),
  post: (id: string) => request<Post>(`/community/posts/${encodeURIComponent(id)}`),
  createPost: (body: { title: string; body: string; design_id?: string | null; design_version?: number | null }) =>
    request<Post>("/community/posts", json("POST", body)),
  updatePost: (id: string, body: { title?: string; body?: string }) =>
    request<Post>(`/community/posts/${encodeURIComponent(id)}`, json("PATCH", body)),
  deletePost: (id: string) => request<void>(`/community/posts/${encodeURIComponent(id)}`, json("DELETE")),
  createComment: (postId: string, body: string) =>
    request<Comment>(`/community/posts/${encodeURIComponent(postId)}/comments`, json("POST", { body })),
  deleteComment: (id: string) => request<void>(`/community/comments/${encodeURIComponent(id)}`, json("DELETE")),

  exportUrl: (id: string, format: "stl" | "3mf", version: number) =>
    `${API_BASE}/designs/${encodeURIComponent(id)}/export?format=${format}&version=${version}`,
  meshUrl: (path: string) => `${API_BASE}${path}`,
};
