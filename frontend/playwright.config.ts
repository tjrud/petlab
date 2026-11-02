import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

// E2E: 모의 해석기(LLM_PROVIDER=mock)와 임시 DB로 백엔드를 띄우고 프론트엔드(프로덕션 빌드)와 함께 테스트한다.
// 이메일은 파일로 저장하고(EMAIL_PROVIDER=file, 테스트가 outbox 에서 인증 링크를 읽는다),
// CAPTCHA 확인은 e2e/stubs/turnstile-verify.mjs 가 대신 답한다.
// 테스트 워커는 다른 프로세스라 process.pid 가 달라지므로, 처음 정한 경로를 환경변수로 넘겨 함께 쓴다.
const tmp = (process.env.E2E_TMP ??= path.join(os.tmpdir(), `kkomul-e2e-${process.pid}`));

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    launchOptions: { args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1400, height: 1000 } } }],
  webServer: [
    {
      command: "uv run uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        LLM_PROVIDER: "mock",
        // 배포와 같이 관리자 인증을 켠 상태로 테스트한다
        ADMIN_USERNAME: "admin",
        ADMIN_PASSWORD: "e2e-admin-password",
        SESSION_SECRET: "e2e-session-secret-0123456789abcdef0123",
        DATABASE_URL: `sqlite:///${tmp}/e2e.db`,
        MESH_CACHE_DIR: `${tmp}/meshes`,
        CORS_ORIGINS: "http://localhost:3000",
        SIGNUP_PER_IP_PER_HOUR: "1000", // 테스트마다 회원가입을 하므로 IP 제한을 넉넉하게
        // 이메일 인증 (메일은 파일 하나씩: e2e/support.ts 의 verifyLinkFor 가 읽는다)
        EMAIL_PROVIDER: "file",
        EMAIL_FROM: "NestForge <no-reply@nestforge.test>",
        EMAIL_OUTBOX_DIR: `${tmp}/outbox`,
        APP_BASE_URL: "http://localhost:3000",
        // 회원가입 CAPTCHA (Turnstile): 확인 요청은 아래 가짜 서버로 보낸다
        TURNSTILE_SITE_KEY: "e2e-site-key",
        TURNSTILE_SECRET_KEY: "e2e-secret-key",
        TURNSTILE_VERIFY_URL: "http://localhost:8099/siteverify",
      },
    },
    {
      // Turnstile 확인 서버 대신: 토큰이 "e2e-pass" 일 때만 통과
      command: "node e2e/stubs/turnstile-verify.mjs",
      url: "http://localhost:8099/health",
      reuseExistingServer: true,
      timeout: 30_000,
      env: { PORT: "8099" },
    },
    {
      command: "npm run build && npm run start -- --port 3000",
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 300_000,
      env: { NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000" },
    },
  ],
});
