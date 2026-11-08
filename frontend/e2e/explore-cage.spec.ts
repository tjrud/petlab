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

test("탐색: STL 을 올리면 미리보기 이미지를 자동으로 만들고, 상세에서 3D 로 보고 가상 케이지에 바로 놓는다", async ({ page }) => {
  await adminLogin(page, "/explore/new");
  await page.getByLabel("완성 파일 고르기").setInputFiles({ name: "round-house.stl", mimeType: "model/stl", buffer: tetraStl(90) });
  // 이미지를 고르지 않았으니 3D 모습으로 만든 이미지가 들어간다
  await expect(page.getByText("3D 파일로 만든 이미지")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("img", { name: "미리보기 이미지" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("NestForge 설계 함께 공유")).toHaveCount(0);
  await page.getByLabel("제목", { exact: true }).fill("둥근 집 STL");
  await page.getByLabel("소개", { exact: true }).fill("STL 미리보기 확인용이에요.");
  await page.getByRole("button", { name: "탐색에 올리기" }).click();
  await page.waitForURL(/\/explore\/[0-9a-f]{32}$/);
  const detailUrl = page.url();
  await expect(page.getByRole("img", { name: "둥근 집 STL 미리보기" })).toBeVisible();

  // 3D 미리보기: 원본 STL 이 아니라 서버가 만든 가벼운 미리보기 메시(NFM1)를 받는다
  const meshRequests: string[] = [];
  page.on("request", (rq) => {
    if (/\/market\/files\/[0-9a-f]{32}\/(mesh|preview)$/.test(rq.url())) meshRequests.push(new URL(rq.url()).pathname.split("/").pop()!);
  });
  await page.reload();
  await expect(page.getByRole("heading", { level: 2, name: "3D 미리보기" })).toBeVisible();
  await expect(page.getByText(/9×9×9cm · 끌어서 돌려 볼 수 있어요/)).toBeVisible({ timeout: 30_000 });
  expect(meshRequests).toContain("preview");
  expect(meshRequests).not.toContain("mesh");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/explore-3d-preview.png`, fullPage: true });

  // 가상 케이지에 놓아 보기 → 빈 자리에 놓이고 주소의 add 는 지워진다
  await page.getByRole("link", { name: "가상 케이지에 놓아 보기", exact: true }).click();
  await page.waitForURL(/\/cage$/);
  await expect(page.getByText('"round-house.stl" 파일을 빈 자리에 놓았어요. 마음에 들면 저장하세요.')).toBeVisible();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  await expect(page.getByRole("heading", { level: 3, name: "round-house" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/cage-from-explore.png`, fullPage: true });

  // 로그인하지 않은 사람도 놓아 볼 수 있다 (파일 목록의 '케이지에 놓기')
  await page.context().clearCookies();
  await page.goto(detailUrl);
  await page.getByRole("link", { name: "round-house.stl 케이지에 놓기" }).click();
  await page.waitForURL(/\/cage$/);
  await expect(page.getByText('"round-house.stl" 파일을 빈 자리에 놓았어요. 마음에 들면 저장하세요.')).toBeVisible();
  await expect(status(page)).toHaveText(/구조물 [12]개$/);
});

test("탐색: 이미지 없이 올린 작품은 올린 사람이 3D 모습으로 대표 이미지를 만든다", async ({ page }) => {
  await adminLogin(page, "/explore/new");
  await page.getByLabel("완성 파일 고르기").setInputFiles({ name: "plain.stl", mimeType: "model/stl", buffer: tetraStl(70) });
  await expect(page.getByText("3D 파일로 만든 이미지")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: /미리보기\.webp 빼기|미리보기\.png 빼기/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /미리보기\.(webp|png) 빼기/ }).click();
  await page.getByLabel("제목", { exact: true }).fill("이미지 없는 STL");
  await page.getByLabel("소개", { exact: true }).fill("대표 이미지를 나중에 만들어요.");
  await page.getByRole("button", { name: "탐색에 올리기" }).click();
  await page.waitForURL(/\/explore\/[0-9a-f]{32}$/);
  await expect(page.getByRole("img", { name: "이미지 없는 STL 미리보기" })).toHaveCount(0);
  await page.getByRole("button", { name: "이 3D 모습으로 대표 이미지 만들기" }).click();
  await expect(page.getByRole("img", { name: "이미지 없는 STL 미리보기" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "이 3D 모습으로 대표 이미지 만들기" })).toHaveCount(0);
  // 3D 파일로 자동으로 만든 이미지는 다시 만들 수 있다 (렌더 모습이 바뀌었을 때)
  const oldSrc = await page.getByRole("img", { name: "이미지 없는 STL 미리보기" }).getAttribute("src");
  await page.getByRole("button", { name: "이 3D 모습으로 대표 이미지 다시 만들기" }).click();
  await expect.poll(() => page.getByRole("img", { name: "이미지 없는 STL 미리보기" }).getAttribute("src"), { timeout: 30_000 }).not.toBe(oldSrc);
});

test("탐색 3D 미리보기: 처음 몇 초만 천천히 돌다 멈추고, 만지면 바로 멈춘다. 움직임 줄이기 설정이면 돌지 않는다", async ({ page, browser }) => {
  await adminLogin(page, "/explore/new");
  await page.getByLabel("완성 파일 고르기").setInputFiles({ name: "spin.stl", mimeType: "model/stl", buffer: tetraStl(80) });
  await expect(page.getByRole("img", { name: "미리보기 이미지" })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("제목", { exact: true }).fill("회전 확인");
  await page.getByLabel("소개", { exact: true }).fill("자동 회전 확인용이에요.");
  await page.getByRole("button", { name: "탐색에 올리기" }).click();
  await page.waitForURL(/\/explore\/[0-9a-f]{32}$/);
  const url = page.url();
  const canvas = page.getByLabel("spin.stl 3D 미리보기");
  const viewer = page.locator("[data-rotating]");
  const ready = page.getByText(/끌어서 돌려 볼 수 있어요/);
  /** 두 장을 잇달아 찍어 같은지 (그리는 속도가 느린 환경에서도 '멈췄는지'만 본다) */
  const still = async () => {
    const a = await canvas.screenshot();
    await page.waitForTimeout(600);
    return (await canvas.screenshot()).equals(a);
  };

  // 1) 처음에는 실제로 돌고, 3~4초 뒤 멈춘다
  await expect(ready).toBeVisible({ timeout: 30_000 });
  await expect(viewer).toHaveAttribute("data-rotating", "true");
  expect(await still()).toBe(false);
  await expect(viewer).toHaveAttribute("data-rotating", "false", { timeout: 10_000 });
  await expect.poll(still, { timeout: 20_000 }).toBe(true);

  // 2) 도는 중에 끌면 그 자리에서 멈춘다
  await page.goto(url);
  await expect(ready).toBeVisible({ timeout: 30_000 });
  await expect(viewer).toHaveAttribute("data-rotating", "true");
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2, { steps: 4 });
  await page.mouse.up();
  await expect(viewer).toHaveAttribute("data-rotating", "false", { timeout: 1_000 });
  await expect(page.getByText(/끌어서 돌리고, 확대·축소할 수 있어요/)).toBeVisible();
  await expect.poll(still, { timeout: 20_000 }).toBe(true);

  // 3) 움직임 줄이기 설정이면 처음부터 돌지 않는다
  const reduced = await browser.newContext({ reducedMotion: "reduce" });
  const r = await reduced.newPage();
  await r.goto(url);
  await expect(r.getByText(/끌어서 돌려 볼 수 있어요/)).toBeVisible({ timeout: 30_000 });
  await r.waitForTimeout(500);
  await expect(r.locator("[data-rotating]")).toHaveAttribute("data-rotating", "false");
  await reduced.close();
});

test("탐색 3D 미리보기: 가벼운 미리보기 메시를 받지 못하면 원본 파일로 보여 준다", async ({ page }) => {
  await adminLogin(page, "/explore/new");
  await page.getByLabel("완성 파일 고르기").setInputFiles({ name: "fallback.stl", mimeType: "model/stl", buffer: tetraStl(60) });
  await expect(page.getByRole("img", { name: "미리보기 이미지" })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("제목", { exact: true }).fill("대체 확인");
  await page.getByLabel("소개", { exact: true }).fill("미리보기 메시가 깨졌을 때");
  await page.getByRole("button", { name: "탐색에 올리기" }).click();
  await page.waitForURL(/\/explore\/[0-9a-f]{32}$/);
  const asked: string[] = [];
  await page.route(/\/market\/files\/[0-9a-f]{32}\/preview$/, (r) => r.fulfill({ status: 500, body: "x" }));
  page.on("request", (rq) => {
    if (/\/market\/files\/[0-9a-f]{32}\/mesh$/.test(rq.url())) asked.push("mesh");
  });
  await page.reload();
  // 작은 원본(10MB 이하)은 묻지 않고 바로 원본으로
  await expect(page.getByText(/6×6×6cm · 끌어서 돌려 볼 수 있어요/)).toBeVisible({ timeout: 30_000 });
  expect(asked).toContain("mesh");
});

test("가상 케이지: '화면 이동'을 켜면 빈 곳을 끌어 화면을 옮기고, 구조물은 그대로다", async ({ page }) => {
  await page.goto("/cage");
  await page.getByRole("button", { name: "다방 은신처 추가" }).click();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  const xBefore = await page.getByLabel("가로 위치 (mm)").inputValue();
  const canvas = page.locator("canvas");
  const box = (await canvas.boundingBox())!;
  const still = async () => {
    const a = await canvas.screenshot();
    await page.waitForTimeout(400);
    return (await canvas.screenshot()).equals(a);
  };
  await expect.poll(still, { timeout: 15_000 }).toBe(true);
  const before = await canvas.screenshot();

  const toggle = page.getByRole("button", { name: "화면 이동" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("빈 곳 끌기: 화면 이동")).toBeVisible();
  // 빈 곳(왼쪽 위 배경)을 끈다
  const sx = box.x + box.width * 0.12;
  const sy = box.y + box.height * 0.3;
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  for (let i = 1; i <= 8; i++) await page.mouse.move(sx + i * 15, sy + i * 6, { steps: 2 });
  await page.mouse.up();
  await expect.poll(still, { timeout: 15_000 }).toBe(true);
  expect((await canvas.screenshot()).equals(before)).toBe(false);
  await expect(page.getByLabel("가로 위치 (mm)")).toHaveValue(xBefore);

  // 시점 버튼을 다시 누르면 처음 화면으로
  await page.getByRole("button", { name: "3D", exact: true }).click();
  await expect.poll(still, { timeout: 15_000 }).toBe(true);
});
