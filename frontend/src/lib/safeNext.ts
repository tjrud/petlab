/** 로그인 후 돌아갈 경로. 같은 출처의 경로만 허용한다 (외부 주소로 보내는 open redirect 방지).
 *  브라우저는 경로 안의 역슬래시·탭·줄바꿈을 정규화해 "/\\evil.com" 같은 값을 외부 주소로 해석하므로,
 *  접두사 검사 대신 실제 URL 로 해석해 출처를 비교하고, 돌려줄 값도 다시 확인한다. */
export function safeNext(raw: string | null, origin: string): string {
  if (!raw || !raw.startsWith("/") || /[\\\u0000-\u001f\u007f]/.test(raw)) return "/";
  let url: URL;
  try {
    url = new URL(raw, origin);
  } catch {
    return "/";
  }
  // "/..//evil.com" 처럼 점 세그먼트가 접히면 경로가 "//evil.com" 이 되어 다른 사이트 주소로 해석된다.
  // 실제로 돌려줄 값을 다시 검사한다.
  const out = url.pathname + url.search + url.hash;
  if (url.origin !== origin || url.pathname.startsWith("//") || url.pathname.startsWith("/login")) return "/";
  if (new URL(out, origin).origin !== origin) return "/";
  return out;
}

/** 로그인·회원가입 화면으로 가는 링크(?next=)는 모두 이것으로 만든다. next 는 인코딩해 붙이고, 비었으면 붙이지 않는다
 *  (실제 이동 전에는 safeNext 로 다시 검사한다). */
export function withNext(path: "/login" | "/signup", next: string | null): string {
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}
