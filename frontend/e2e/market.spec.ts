import { expect, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };

/** SketchUp 파일 머리(UTF-16LE "SketchUp Model")를 가진 가짜 SKP. 3MB 조각 3개로 나뉘는 크기 */
function skp(size = 7 * 1024 * 1024 + 321): Buffer {
  const head = Buffer.concat([Buffer.from([0xff, 0xfe, 0xff, 0x0e]), Buffer.from("SketchUp Model", "utf16le")]);
  const body = Buffer.alloc(size - head.length);
  for (let i = 0; i < body.length; i += 4096) body[i] = i % 251;
  return Buffer.concat([head, body]);
}

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test("둥지마당: SKP 파일 나눠 올리기 → 작품 등록 → 내려받기, 목록·커뮤니티 소개 글", async ({ page, request }) => {
  await page.goto("/login?next=/market/new");
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((u) => u.pathname === "/market/new");

  const title = `다방 은신처 ${Date.now().toString(36)}`;
  await page.getByLabel("제목", { exact: true }).fill(title);
  await page.getByLabel("소개", { exact: true }).fill("SketchUp 2017로 만든 2칸짜리 은신처예요. 출입구 7cm.");

  // 확장자만 SKP 인 파일은 서버가 거절해요
  await page.getByLabel("완성 파일 고르기").setInputFiles({ name: "fake.skp", mimeType: "application/octet-stream", buffer: Buffer.from("not a sketchup file at all") });
  await expect(page.getByText("SKP 파일이 아니거나 손상된 파일이에요.")).toBeVisible();
  await page.getByRole("button", { name: "fake.skp 빼기" }).click();

  const data = skp();
  await page.getByLabel("완성 파일 고르기").setInputFiles({ name: "은신처.skp", mimeType: "application/octet-stream", buffer: data });
  await page.getByLabel("미리보기 이미지 고르기").setInputFiles({ name: "preview.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByText(/7\.0MB · SketchUp 모델 · 올림/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/preview\.png/)).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /커뮤니티에 소개 글도 올리기/ })).toBeChecked();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/market-new.png`, fullPage: true });
  await page.getByRole("button", { name: "둥지마당에 올리기" }).click();

  // 작품 화면: 파일·내려받기·커뮤니티 소개 글
  await page.waitForURL(/\/market\/[0-9a-f]{32}$/);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  const link = page.getByRole("link", { name: "은신처.skp 내려받기" });
  await expect(link).toBeVisible();
  const href = (await link.getAttribute("href"))!;
  const got = await request.get(href);
  expect(got.status()).toBe(200);
  expect(Buffer.compare(Buffer.from(await got.body()), data)).toBe(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/market-item.png`, fullPage: true });

  await page.getByRole("link", { name: "커뮤니티 소개 글에서 댓글 보기 →" }).click();
  await expect(page.getByRole("heading", { level: 1, name: `[둥지마당] ${title}` })).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(`둥지마당 작품.*${title}`) })).toBeVisible();

  // 목록 (로그인하지 않아도 보인다)
  await page.goto("/market");
  const card = page.getByRole("link", { name: new RegExp(title) });
  await expect(card).toBeVisible();
  await expect(card.getByText("SKP")).toBeVisible();
  await expect(card.getByText("내려받기 1")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/market-list.png`, fullPage: true });
  await page.goto("/market?category=tunnel");
  await expect(page.getByRole("link", { name: new RegExp(title) })).toHaveCount(0);
});
