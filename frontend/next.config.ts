import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    // 백엔드 API 주소. Vercel 배포에서는 같은 출처의 /api 가 백엔드 서비스로 연결된다(vercel.json rewrites).
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.VERCEL ? "/api" : "http://localhost:8000"),
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
