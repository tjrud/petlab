import { expect, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };

test("운영팀 글에 사진 넣기: 고른 순서대로 보이고, 출처가 표시되고, 목록에 썸네일", async ({ page }) => {
  await page.goto("/login?next=/community/new");
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/community/new");

  const title = `[가이드] 데구 ${Date.now().toString(36)}`;
  await page.getByLabel("제목").fill(title);
  await page.getByLabel("내용").fill("데구는 낮에 활동하고 무리 지어 사는 설치류예요.");
  await page.getByRole("button", { name: "등록", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();

  // 수정 화면에서 사진 두 장을 고른다 (고른 순서대로 1, 2)
  await page.getByRole("button", { name: "수정" }).click();
  await page.getByRole("button", { name: "말린 바나나를 먹는 데구" }).click();
  await page.getByRole("button", { name: "나무 위에 모여 있는 데구 무리" }).click();
  await expect(page.getByRole("button", { name: "말린 바나나를 먹는 데구 (1번째)" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "저장" }).click();

  const article = page.getByRole("article");
  await expect(article.getByRole("img", { name: "말린 바나나를 먹는 데구" })).toBeVisible();
  await expect(article.getByRole("img", { name: "나무 위에 모여 있는 데구 무리" })).toBeVisible();
  // 사진 출처: 촬영자와 라이선스 링크 (원본 페이지)
  await expect(article.getByText("사진: Pierre Camateros ·")).toBeVisible();
  const lic = article.getByRole("link", { name: "CC BY-SA 3.0" });
  await expect(lic).toHaveAttribute("href", "https://commons.wikimedia.org/wiki/File:Degu_eating_a_piece_of_dried_banana.jpg");
  // 이미지 파일이 실제로 배포되어 있다
  const loaded = await article.getByRole("img", { name: "말린 바나나를 먹는 데구" }).evaluate((img: HTMLImageElement) => img.naturalWidth);
  expect(loaded).toBeGreaterThan(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/post-images.png`, fullPage: true });

  // 목록에 첫 사진 썸네일
  await page.goto("/community");
  const row = page.getByRole("listitem").filter({ hasText: title });
  await expect(row.locator("img")).toHaveAttribute("src", "/community-images/degu-1.webp");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/post-list.png` });

  // 사진 빼기
  await row.getByRole("link").click();
  await page.getByRole("button", { name: "수정" }).click();
  await page.getByRole("button", { name: "말린 바나나를 먹는 데구 (1번째)" }).click();
  await page.getByRole("button", { name: "나무 위에 모여 있는 데구 무리 (1번째)" }).click();
  await page.getByRole("button", { name: "저장" }).click();
  await expect(page.getByRole("article").getByRole("img")).toHaveCount(0);
});
