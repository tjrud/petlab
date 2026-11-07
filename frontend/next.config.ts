import type { NextConfig } from "next";

// 백엔드 API 주소. Vercel 배포에서는 같은 출처의 /api 가 백엔드 서비스로 연결된다(vercel.json rewrites).
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.VERCEL ? "/api" : "http://localhost:8000");
const API_ORIGIN = /^https?:\/\//.test(API_BASE_URL) ? new URL(API_BASE_URL).origin : "";

// 올린 파일(Vercel Blob)과 회원가입 CAPTCHA(Cloudflare Turnstile)만 바깥에서 불러온다
const BLOB = "https://*.public.blob.vercel-storage.com";
const TURNSTILE = "https://challenges.cloudflare.com";
const DEV = process.env.NODE_ENV !== "production";

const CSP = [
  "default-src 'self'",
  // Next.js 가 페이지에 넣는 인라인 스크립트 때문에 'unsafe-inline' 이 필요하다
  `script-src 'self' 'unsafe-inline' ${TURNSTILE}${DEV ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${BLOB} ${API_ORIGIN}`.trim(),
  "font-src 'self' data:",
  `connect-src 'self' ${BLOB} ${TURNSTILE} ${API_ORIGIN}`.trim(),
  `frame-src ${TURNSTILE}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_API_BASE_URL: API_BASE_URL },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  // "둥지마당"(/market)이 "탐색"(/explore)으로 바뀌었다. 예전 주소(커뮤니티 글의 링크 등)는 새 주소로 보낸다
  async redirects() {
    return [
      { source: "/market", destination: "/explore", permanent: true },
      { source: "/market/:path*", destination: "/explore/:path*", permanent: true },
    ];
  },
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
