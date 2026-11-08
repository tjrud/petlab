import { expect, test } from "@playwright/test";

import { signup, stubTurnstile } from "./support";

const RUN = Date.now().toString(36).slice(-5);

test.beforeEach(async ({ page }) => {
  await stubTurnstile(page);
});

test("언어 바꾸기: 한국어 ↔ English, 고른 언어는 다음 방문에도 이어진다", async ({ page }) => {
  for (const path of ["/", "/explore", "/community", "/cage"]) {
    await page.goto(path);
    await expect(page.locator("html")).toHaveAttribute("lang", "ko");
    await page.getByRole("button", { name: "영어로 보기" }).click();
    await page.waitForURL((u) => u.pathname === (path === "/" ? "/en" : `/en${path}`));
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    const nav = page.getByRole("navigation", { name: "Main menu" });
    await expect(nav.getByRole("link", { name: "My designs" })).toHaveAttribute("href", "/en/designs");
    // 영어를 고른 뒤 접두어 없는 주소로 오면 영어 주소로 보낸다
    await page.goto("/designs");
    await expect(page).toHaveURL(/\/en\/designs$/);
    await page.goto(path === "/" ? "/en" : `/en${path}`);
    await page.getByRole("button", { name: "View in Korean" }).click();
    await page.waitForURL((u) => u.pathname === path);
    await expect(page.locator("html")).toHaveAttribute("lang", "ko");
    await expect(page.getByRole("navigation", { name: "주 메뉴" }).getByRole("link", { name: "내 설계" })).toBeVisible();
  }
  // 한국어로 돌아오면 접두어 없는 주소가 다시 한국어로 열린다
  await page.goto("/designs");
  await expect(page).toHaveURL(/localhost:3000\/designs$/);
  // 쿼리는 그대로 옮긴다
  await page.goto("/design?prompt=%ED%84%B0%EB%84%90");
  await page.getByRole("button", { name: "영어로 보기" }).click();
  await page.waitForURL((u) => u.pathname === "/en/design" && u.searchParams.get("prompt") === "터널");
  await page.goto("/en");
  await page.getByRole("button", { name: "View in Korean" }).click();
  await page.waitForURL((u) => u.pathname === "/");
});

test("영어 화면: 회원가입 후 영어로 설계하면 서버 문구와 설계 설명도 영어", async ({ page, context }) => {
  await signup(page, { username: `eng_${RUN}`, nickname: `Eng${RUN}`, password: "english-pass-321" }, { next: "/" });
  await context.addCookies([{ name: "lang", value: "en", url: "http://localhost:3000" }]);
  await page.goto("/design");
  await expect(page).toHaveURL(/\/en\/design$/);
  const wizard = page.getByRole("region", { name: "Tell us about your habitat" });
  await wizard.getByLabel("Cage Width (mm)").fill("600");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Request").fill("A hideout with two entrances");
  await page.getByRole("button", { name: "Get a custom design" }).click();
  await page.waitForURL(/\/en\/designs\/[0-9a-f]{32}/);
  await expect(page.getByText("Hideout #1").first()).toBeVisible();
  await expect(page.getByText(/\[Dev mock interpreter\]/)).toBeVisible();
  // 지운 설계 주소: 서버 오류 문구도 영어
  const r = await page.request.get("http://localhost:8000/designs/0123456789abcdef0123456789abcdef", { headers: { "X-Lang": "en" } });
  expect(r.status()).toBe(404);
  expect((await r.json()).detail.message_ko).not.toMatch(/[가-힣]/);
});

test("없는 주소는 두 언어 안내가 있는 404 페이지", async ({ page }) => {
  const res = await page.goto("/no-such-page");
  expect(res?.status()).toBe(404);
  await expect(page.getByText("페이지를 찾을 수 없어요")).toBeVisible();
  await expect(page.getByText("Page not found")).toBeVisible();
});
