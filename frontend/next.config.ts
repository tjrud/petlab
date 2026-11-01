import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    // 백엔드 API 주소. Vercel 배포에서는 같은 출처의 /api 가 백엔드 서비스로 연결된다(vercel.json rewrites).
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.VERCEL ? "/api" : "http://localhost:8000"),
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
