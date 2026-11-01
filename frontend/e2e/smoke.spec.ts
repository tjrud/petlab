import { expect, type Page, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };

async function login(page: Page) {
  await page.goto("/login?next=/");
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/");
}

test("관리자 인증: 사이트는 공개, 설계 기능은 로그인 후에만", async ({ page, request }) => {
  // 로그인 없이 API 호출 → 401
  const r = await request.get("http://localhost:8000/species");
  expect(r.status()).toBe(401);
  // 첫 화면은 누구나 열 수 있고, 설계 폼 대신 로그인 안내가 보인다 (자동으로 이동하지 않음)
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /구조물을 설계해 드려요/ })).toBeVisible();
  await expect(page.getByText("관리자 로그인 후 사용할 수 있어요")).toBeVisible();
  await expect(page.getByRole("heading", { name: "사육 환경을 알려 주세요" })).toHaveCount(0);
  await page.getByRole("main").getByRole("link", { name: "관리자 로그인" }).click();
  await page.waitForURL(/\/login\?next=%2F$/);
  await expect(page.getByRole("heading", { name: "관리자 로그인" })).toBeVisible();
  await expect(page.getByLabel("아이디")).toHaveValue(""); // 아이디를 미리 채워 두지 않는다
  // 틀린 비밀번호
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill("wrong-password");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.getByText("아이디 또는 비밀번호가 올바르지 않아요.")).toBeVisible();
  // 올바른 비밀번호 → 원래 화면으로
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/");
  await expect(page.getByRole("heading", { name: "사육 환경을 알려 주세요" })).toBeVisible();
  await expect(page.getByText("관리자 admin")).toBeVisible();
  // 로그아웃 → 로그인 화면 (현재 기록을 바꿔치기해 뒤로 가도 로그인 전 화면이 다시 보이지 않는다)
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.waitForURL(/\/login$/);
  await expect(page.getByText("관리자 admin")).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "사육 환경을 알려 주세요" })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByText("관리자 로그인 후 사용할 수 있어요")).toBeVisible();
});

test("로그인 후 이동 경로는 같은 사이트 안으로만", async ({ page }) => {
  for (const next of [
    "/\\evil.example/x",
    "/\t/evil.example",
    "//evil.example",
    "https://evil.example/",
    "/..//evil.example",
    "/.//evil.example",
    "/%2e%2e//evil.example",
    "/a/..//evil.example",
  ]) {
    await page.goto(`/login?next=${encodeURIComponent(next)}`);
    await page.getByLabel("아이디").fill(ADMIN.username);
    await page.getByLabel("비밀번호").fill(ADMIN.password);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page.waitForURL((url) => url.origin === "http://localhost:3000" && url.pathname === "/");
    await page.context().clearCookies();
  }
  // 같은 사이트 경로는 그대로 돌아간다
  await page.goto(`/login?next=${encodeURIComponent("/order?design=abc")}`);
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/order" && url.search === "?design=abc");
});

test("사육 환경 등록 → 요구사항 → 3D 뷰어 → 다운로드 → 제작 신청", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await login(page);
  await expect(page.getByRole("heading", { name: "사육 환경을 알려 주세요" })).toBeVisible();

  // 1. 사육 환경
  await page.getByText("골든 (시리안)").click();
  await page.getByRole("button", { name: "중형 60×40×30cm" }).click();
  await page.getByRole("button", { name: "다음" }).click();

  // 2. 요구사항
  await page.getByLabel("요구사항").fill("은신처를 왼쪽에 넣고 환기구는 8개로 해 주세요");
  // 뷰어가 구조물 메시(STL)를 실제로 받아오는지 — 요청이 빨리 끝날 수 있으므로 먼저 대기를 건다
  const meshLoaded = page.waitForResponse((r) => r.url().includes("/parts/") && r.status() === 200);
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();

  // 3~4. 설계 결과 + 3D 뷰어
  await page.waitForURL(/\/designs\/[0-9a-f]+$/);
  await expect(page.getByRole("heading", { name: "맞춤 설계 v1" })).toBeVisible();
  await expect(page.getByTestId("viewer").locator("canvas")).toBeVisible();
  await expect(page.getByText("통과", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /은신처 #1/ })).toBeVisible();
  await meshLoaded;
  await page.waitForTimeout(1500); // 렌더 완료 대기
  expect(pageErrors).toEqual([]);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/design-v1.png`, fullPage: true });

  // 구조물 선택 → 상세 파라미터
  await page.getByRole("button", { name: /은신처 #1/ }).click();
  await expect(page.getByText("환기구 개수")).toBeVisible();
  await expect(page.locator("dd", { hasText: /^8개$/ })).toBeVisible();
  await expect(page.getByTestId("viewer").getByText("은신처 #1")).toBeVisible(); // 3D 뷰어 안 선택 라벨
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/design-selected.png`, fullPage: true });

  // 6. 다운로드 링크가 실제 파일을 내려주는지
  const stlHref = await page.getByRole("link", { name: /STL/ }).getAttribute("href");
  const threeMfHref = await page.getByRole("link", { name: /3MF/ }).getAttribute("href");
  const stl = await page.request.get(stlHref!);
  expect(stl.status()).toBe(200);
  expect((await stl.body()).length).toBeGreaterThan(1000);
  const tmf = await page.request.get(threeMfHref!);
  expect(tmf.headers()["content-type"]).toContain("model/3mf");

  // 제작·배송 신청 → 대기 화면
  await page.getByRole("link", { name: "제작·배송 신청하기" }).click();
  await page.getByLabel("이메일", { exact: true }).fill("tester@example.com");
  await page.getByRole("checkbox", { name: /알림을 받기 위해/ }).check();
  await page.getByRole("button", { name: "대기 명단에 등록하기" }).click();
  await expect(page.getByRole("heading", { name: "대기 등록 완료" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/waitlist.png` });
});

test("검증 실패 설계는 내려받기 대신 안내를 보여준다", async ({ page }) => {
  await login(page);
  await page.getByText("골든 (시리안)").click();
  await page.getByLabel("케이지 높이 (mm)").fill("130");
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처 하나 넣어 주세요");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await page.waitForURL(/\/designs\//);
  await expect(page.getByText(/문제 \d+건/)).toBeVisible();
  await expect(page.getByText("해결이 필요한 문제", { exact: false })).toBeVisible();
  await expect(page.getByText("검증 문제를 해결해야 파일을 내려받을 수 있어요", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: /STL/ })).toHaveCount(0);
});

test("수정 루프: 추가 프롬프트로 v2 생성, 이전 버전 유지·전환", async ({ page }) => {
  await login(page);
  await page.getByText("골든 (시리안)").click();
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처를 왼쪽에 넣어 주세요");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await page.waitForURL(/\/designs\//);
  await expect(page.getByRole("heading", { name: "맞춤 설계 v1" })).toBeVisible();

  const sizeOf = async () => (await page.getByRole("button", { name: /은신처 #1/ }).innerText()).match(/(\d+)×/)![1];
  const v1Width = Number(await sizeOf());

  // 수정 → v2
  await page.getByLabel("수정할 내용").fill("조금 더 크게 해 주세요");
  await page.getByRole("button", { name: "v1 기준으로 다시 설계" }).click();
  await expect(page.getByRole("heading", { name: "맞춤 설계 v2" })).toBeVisible();
  expect(Number(await sizeOf())).toBeGreaterThan(v1Width);
  const versions = page.getByRole("region", { name: /설계 버전/ });
  await expect(versions.getByRole("button")).toHaveCount(2);
  await expect(page.getByLabel("수정할 내용")).toHaveValue(""); // 성공 시 입력란 비움
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/design-v2.png`, fullPage: true });

  // v1 으로 전환 → 원래 값 유지
  await versions.getByRole("button", { name: /^v1/ }).click();
  await expect(page.getByRole("heading", { name: "맞춤 설계 v1" })).toBeVisible();
  expect(Number(await sizeOf())).toBe(v1Width);
  await expect(page.getByText("v1을 보고 있어요", { exact: false })).toBeVisible();

  // v1 기준으로 다시 수정 → v3 (v1·v2 유지)
  await page.getByLabel("수정할 내용").fill("더 작게 해 주세요");
  await page.getByRole("button", { name: "v1 기준으로 다시 설계" }).click();
  await expect(page.getByRole("heading", { name: "맞춤 설계 v3" })).toBeVisible();
  expect(Number(await sizeOf())).toBeLessThan(v1Width);
  await expect(versions.getByRole("button")).toHaveCount(3);
});

test("여러 구조물: 은신처와 터널을 한쪽에 몰아서", async ({ page }) => {
  await login(page);
  await page.getByText("골든 (시리안)").click();
  await page.getByRole("button", { name: "대형 80×50×40cm" }).click();
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByRole("button", { name: "은신처와 터널을 한쪽에 몰아서 넣고 싶어요" }).click();
  const meshes: string[] = [];
  page.on("response", (r) => {
    if (r.url().includes("/parts/") && r.status() === 200) meshes.push(r.url());
  });
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await page.waitForURL(/\/designs\//);
  await expect(page.getByRole("button", { name: /은신처 #1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^터널 #2 \d/ })).toBeVisible();
  await expect(page.getByText("통과", { exact: true })).toBeVisible();
  await expect.poll(() => meshes.length).toBe(2);
  await page.getByRole("button", { name: /^터널 #2 \d/ }).click();
  await expect(page.getByText("터널 내경", { exact: false }).or(page.getByText("내경"))).toBeVisible();
  await page.waitForTimeout(1500);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/design-mixed.png`, fullPage: true });

  const href = await page.getByRole("link", { name: /STL \(zip\)/ }).getAttribute("href");
  const zip = await page.request.get(href!);
  expect(zip.headers()["content-type"]).toBe("application/zip");
});
