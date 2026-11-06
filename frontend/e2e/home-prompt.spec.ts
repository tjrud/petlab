import { expect, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };

test("메인 입력창에 적은 요청이 로그인을 거쳐 설계하기 화면의 요구사항으로 이어진다", async ({ page }) => {
  await page.goto("/");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/home-hero.png` });
  const box = page.getByRole("searchbox", { name: "원하는 구조물" });
  await box.fill("은신처를 오른쪽 구석에, 앞쪽은 넓게");
  await box.press("Enter");
  await page.waitForURL((url) => url.pathname === "/design");
  expect(new URL(page.url()).searchParams.get("prompt")).toBe("은신처를 오른쪽 구석에, 앞쪽은 넓게");

  // 로그인하지 않았으면 로그인 안내 → 로그인 후 같은 주소(요청 포함)로 돌아온다
  await page.getByRole("main").getByRole("link", { name: "로그인", exact: true }).click();
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/design");

  await expect(page.getByText("적어 주신 요청")).toBeVisible();
  await expect(page.getByText("은신처를 오른쪽 구석에, 앞쪽은 넓게")).toBeVisible();
  await page.getByRole("button", { name: "다음" }).click();
  await expect(page.getByLabel("요구사항")).toHaveValue("은신처를 오른쪽 구석에, 앞쪽은 넓게");
});

test("메인 예시를 누르면 그 문장으로 설계하기가 열린다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "모래목욕통과 계단, 가운데는 비워 두기" }).click();
  await page.waitForURL((url) => url.pathname === "/design");
  expect(new URL(page.url()).searchParams.get("prompt")).toBe("모래목욕통과 계단, 가운데는 비워 두기");
});
