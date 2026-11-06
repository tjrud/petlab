import { expect, type Page, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };

/** 크기 size mm 정사면체 바이너리 STL */
function tetraStl(size = 120): Buffer {
  const v = [
    [0, 0, 0],
    [size, 0, 0],
    [0, size, 0],
    [0, 0, size],
  ];
  const faces = [
    [0, 2, 1],
    [0, 1, 3],
    [0, 3, 2],
    [1, 2, 3],
  ];
  const buf = Buffer.alloc(84 + faces.length * 50);
  buf.writeUInt32LE(faces.length, 80);
  faces.forEach((f, i) => {
    const o = 84 + i * 50 + 12;
    f.forEach((vi, k) => v[vi].forEach((c, j) => buf.writeFloatLE(c, o + k * 12 + j * 4)));
  });
  return buf;
}

async function adminLogin(page: Page, next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((u) => u.pathname === next.split("?")[0]);
}

const status = (page: Page) => page.getByText(/^케이지 \d+×\d+×\d+mm · 구조물 \d+개$/);

test("메뉴 순서: 설계하기·가상 케이지·내 설계·탐색·커뮤니티, 내 정보는 오른쪽 끝. 탐색은 추천이 먼저", async ({ page }) => {
  await page.goto("/");
  const main = page.getByRole("navigation", { name: "주 메뉴" }).first();
  await expect(main.getByRole("link")).toHaveText(["설계하기", "가상 케이지", "내 설계", "탐색", "커뮤니티"]);
  await expect(page.getByRole("navigation", { name: "내 정보 메뉴" }).getByRole("link", { name: "내 정보" })).toBeVisible();
  // 예전 주소는 탐색으로
  await page.goto("/market");
  await expect(page).toHaveURL(/\/explore$/);
  await expect(page.getByRole("heading", { level: 1, name: "탐색" })).toBeVisible();
  await expect(page.getByRole("link", { name: "추천" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("로그인하면 내 설계와 반려동물에 맞춘 추천이 보여요.")).toBeVisible();
  await page.getByRole("link", { name: "가상 케이지 배치" }).click();
  await expect(page).toHaveURL(/category=layout/);
});

test("가상 케이지: 내 STL 올려 놓기 → 배치 저장 → 탐색에 공유 → 내 가상 케이지로 담기, 배경색", async ({ page }) => {
  await adminLogin(page, "/cage");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 0개");

  // 내 파일: STL 을 올리면 크기와 함께 목록에 나오고, 누르면 케이지에 놓인다
  await page.getByRole("button", { name: "내 파일", exact: true }).click();
  await page.getByLabel("케이지에 놓을 파일 올리기").setInputFiles({ name: "my-house.stl", mimeType: "model/stl", buffer: tetraStl(120) });
  const fileBtn = page.getByRole("button", { name: "my-house.stl 놓기" });
  await expect(fileBtn).toBeVisible({ timeout: 30_000 });
  await expect(fileBtn).toContainText("12×12×12cm");
  await fileBtn.click();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  await expect(page.getByRole("heading", { level: 3, name: "my-house" })).toBeVisible();

  // 배경색: 남색으로 바꾸면 3D 화면 배경이 바뀌고, 새로 고침해도 남는다
  await page.getByText("배경", { exact: true }).click();
  await page.getByRole("button", { name: "배경 남색" }).click();
  const scene = page.locator("canvas").locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]");
  await expect(scene).toHaveCSS("background-color", "rgb(30, 41, 59)");

  // 저장 → 탐색에 공유
  await page.getByLabel("배치안 이름").fill("파일 넣은 배치");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("새 배치안으로 저장했어요.")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/cage-myfile.png`, fullPage: true });
  await page.getByRole("link", { name: "탐색에 공유" }).click();
  await page.waitForURL(/\/explore\/new\?layout=/);
  await expect(page.getByRole("img", { name: /케이지 1000×500mm 배치를 위에서 본 그림, 구조물 1개/ })).toBeVisible();
  await expect(page.getByLabel("제목", { exact: true })).toHaveValue("파일 넣은 배치");
  await expect(page.getByLabel("분류")).toHaveValue("layout");
  await page.getByLabel("소개", { exact: true }).fill("STL 은신처를 넣은 배치예요.");
  await page.getByRole("button", { name: "탐색에 올리기" }).click();
  await page.waitForURL(/\/explore\/[0-9a-f]{32}$/);
  await expect(page.getByRole("heading", { level: 2, name: "가상 케이지 배치" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/explore-layout.png`, fullPage: true });

  // 내 가상 케이지로 담기 → 새 배치안으로 저장되어 열린다
  await page.getByRole("button", { name: "내 가상 케이지로 담기" }).click();
  await page.waitForURL(/\/cage\?layout=[0-9a-f]{32}$/);
  await expect(page.getByLabel("배치안 이름")).toHaveValue("파일 넣은 배치 (탐색)");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  await expect(scene).toHaveCSS("background-color", "rgb(30, 41, 59)");

  // 탐색 목록의 가상 케이지 배치 분류에 보인다
  await page.goto("/explore?category=layout");
  await expect(page.getByRole("link", { name: /파일 넣은 배치/ }).first()).toBeVisible();
});
