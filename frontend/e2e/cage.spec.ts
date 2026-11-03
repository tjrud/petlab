import { expect, type Page, test } from "@playwright/test";

import { signup, stubTurnstile } from "./support";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const RUN = Date.now().toString(36).slice(-5);

test.beforeEach(async ({ page }) => {
  await stubTurnstile(page);
});

const xPos = (page: Page) => page.getByLabel("가로 위치 (mm)");
const status = (page: Page) => page.getByText(/^케이지 \d+×\d+×\d+mm · 구조물 \d+개$/);

test("가상 케이지: 에셋 놓기·끌어 옮기기·되돌리기·회전·케이지 크기·저장", async ({ page }) => {
  await page.goto("/cage");
  await expect(page.getByRole("heading", { level: 1, name: "가상 케이지 공간 설계" })).toBeVisible();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 0개");

  // 기본 구성: 쳇바퀴는 케이지 높이에 맞는 크기로 (기본 케이지는 높이 50cm 라 28cm 쳇바퀴가 들어가요, 높이 경고 없음)
  await page.getByRole("button", { name: /기본 구성 한 번에 넣기/ }).click();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 5개");
  await expect(page.getByText(/쳇바퀴 높이 .*케이지 높이/)).toHaveCount(0);
  // 벽·모서리부터 채워서 겹치거나 끼임 틈·출입구 막힘이 생기지 않아요
  await expect(page.getByText("오류 0")).toBeVisible();
  await expect(page.getByText("경고 0")).toBeVisible();
  // 3D 위 치수 글자
  await expect(page.getByText("가로 1000mm · 앞")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/cage-starter.png`, fullPage: true });

  // 새로 만들기 (저장하지 않은 변경이 있어 확인 창이 뜬다)
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "새로 만들기" }).click();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 0개");

  // 하나 놓으면 벽·모서리부터 채우고(뒤-왼쪽 모서리) 선택돼요
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await expect(page.getByRole("heading", { level: 3, name: "땅굴 상자" })).toBeVisible();
  await expect(xPos(page)).toHaveValue("150");
  await expect(page.getByLabel("세로 위치 (mm)")).toHaveValue("400");
  // 뒤 벽에 붙은 채로 돌려도 케이지 안에 있던 것은 안쪽으로 밀려 들어와요 (밖으로 나가지 않음)
  await page.locator("body").press("r");
  await expect(page.getByLabel("회전 (°)")).toHaveValue("90");
  await expect(page.getByLabel("세로 위치 (mm)")).toHaveValue("350");
  await expect(page.getByText("땅굴 상자가 케이지 밖으로 나가 있어요.")).toHaveCount(0);
  // 돌리기 전으로 되돌려 다음 단계를 이어가요
  await page.getByRole("button", { name: "↶ 되돌리기" }).click();
  await expect(page.getByLabel("회전 (°)")).toHaveValue("0");
  await expect(xPos(page)).toHaveValue("150");
  // 위치를 직접 입력해 가운데로
  await xPos(page).fill("500");
  await xPos(page).press("Enter");
  await page.getByLabel("세로 위치 (mm)").fill("250");
  await page.getByLabel("세로 위치 (mm)").press("Enter");
  await expect(xPos(page)).toHaveValue("500");

  // 위에서 보기: 화면 가운데가 케이지 가운데. 끌어서 오른쪽으로 옮겨요
  await page.getByRole("button", { name: "위에서" }).click();
  const canvas = page.locator("canvas");
  const box = (await canvas.boundingBox())!;
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.waitForTimeout(500);
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) await page.mouse.move(cx + i * 8, cy, { steps: 2 });
  await page.mouse.up();
  await expect.poll(async () => Number(await xPos(page).inputValue())).toBeGreaterThan(510);

  // 되돌리기 → 제자리
  await page.getByRole("button", { name: "↶ 되돌리기" }).click();
  await expect(xPos(page)).toHaveValue("500");

  // 키보드: R 은 90° 회전, 방향키는 1cm 이동
  await page.locator("body").press("r");
  await expect(page.getByLabel("회전 (°)")).toHaveValue("90");
  await page.locator("body").press("ArrowRight");
  await expect(xPos(page)).toHaveValue("510");

  // 위치를 직접 입력해 벽 밖으로 → 오류
  await xPos(page).fill("20");
  await xPos(page).press("Enter");
  await expect(page.getByText("땅굴 상자가 케이지 밖으로 나가 있어요.").first()).toBeVisible();

  // 케이지 크기 바꾸기
  await page.getByRole("tab", { name: "케이지 크기" }).click();
  await page.getByRole("button", { name: "대형 80×50×40" }).click();
  await expect(status(page)).toHaveText("케이지 800×500×400mm · 구조물 1개");
  await page.getByLabel("케이지 가로 (mm)").fill("150");
  await expect(page.getByText("가로는 200~2000mm 사이로 입력해 주세요.")).toBeVisible();
  await expect(page.getByRole("button", { name: "크기 적용" })).toBeDisabled();
  await page.getByLabel("케이지 가로 (mm)").fill("700");
  await page.getByRole("button", { name: "크기 적용" }).click();
  await expect(status(page)).toHaveText("케이지 700×500×400mm · 구조물 1개");
  // 종 규칙의 최소 바닥 기준(100×50cm)보다 작으면 경고
  await expect(page.getByText("케이지 바닥 70×50cm가 최소 기준 100×50cm보다 작아요. 더 넓은 케이지를 권장해요.")).toBeVisible();
  await page.getByRole("button", { name: "벽 안쪽으로 모두 옮기기" }).click();
  await expect(page.getByText(/케이지 밖으로 나가 있어요/)).toHaveCount(0);

  // 로그인 전에는 저장 대신 로그인 안내. 가입하고 돌아오면 작업이 그대로 있어요 (브라우저 임시 저장)
  await expect(page.getByRole("link", { name: "로그인하고 저장" })).toBeVisible();
  await signup(page, { username: `cage_${RUN}`, nickname: `케이지${RUN}`, password: "password-123" }, { next: "/cage" });
  await page.goto("/cage");
  await expect(status(page)).toHaveText("케이지 700×500×400mm · 구조물 1개");

  await page.getByLabel("배치안 이름").fill("거실 케이지");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("새 배치안으로 저장했어요.")).toBeVisible();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeDisabled();

  // 새로 고침하면 계정에서 다시 불러와요
  await page.reload();
  await expect(page.getByLabel("배치안 이름")).toHaveValue("거실 케이지");
  await expect(status(page)).toHaveText("케이지 700×500×400mm · 구조물 1개");
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await expect(page.getByText("거실 케이지")).toBeVisible();
  await expect(page.getByRole("button", { name: "열려 있음" })).toBeDisabled();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/cage-saved.png`, fullPage: true });
});

test("저장한 배치안을 연 채로 새로 만들기·새 배치안으로 저장·삭제해도 옛 배치안이 다시 열리지 않는다", async ({ page }) => {
  // 주소(?layout=)가 바뀌는 사이의 렌더에서 옛 배치안을 다시 불러오던 문제를 막아요
  const gets: string[] = [];
  page.on("request", (r) => {
    const m = r.method() === "GET" && /\/layouts\/([0-9a-f]{32})$/.exec(new URL(r.url()).pathname);
    if (m) gets.push(m[1]);
  });
  const layoutId = () => /[?&]layout=([0-9a-f]{32})/.exec(page.url())?.[1] ?? null;
  const settle = async () => {
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(300);
  };

  await signup(page, { username: `cagerace_${RUN}`, nickname: `케경합${RUN}`, password: "password-123" }, { next: "/cage" });
  await page.goto("/cage");
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await page.getByLabel("배치안 이름").fill("배치 A");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("새 배치안으로 저장했어요.")).toBeVisible();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const a = layoutId()!;

  // 1) A 를 연 채로 '새 배치안으로 저장' → 주소·화면 모두 새 배치안 B 이고 A 를 다시 불러오지 않아요
  await page.getByRole("button", { name: "밥그릇 추가" }).click();
  await page.getByLabel("배치안 이름").fill("배치 B");
  gets.length = 0;
  await page.getByRole("button", { name: "새 배치안으로 저장" }).click();
  await expect(page.getByText("새 배치안으로 저장했어요.")).toBeVisible();
  await expect.poll(layoutId).not.toBe(a);
  const b = layoutId()!;
  await settle();
  expect(gets).toEqual([]);
  expect(layoutId()).toBe(b);
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 B");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 2개");
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeDisabled();
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await expect(page.getByRole("button", { name: "열려 있음" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "열기" })).toHaveCount(1);

  // 2) B 를 연 채로 '새로 만들기' → 빈 새 배치안이 그대로 남아요
  gets.length = 0;
  await page.getByRole("button", { name: "새로 만들기" }).click();
  await expect(page).toHaveURL(/\/cage$/);
  await settle();
  expect(gets).toEqual([]);
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 0개");
  await expect(page.getByLabel("배치안 이름")).toHaveValue("새 배치안");
  // 새로 고쳐도 빈 새 배치안 (임시 저장이 옛 배치안을 가리키지 않아요)
  await page.reload();
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 0개");
  await expect(page).toHaveURL(/\/cage$/);

  // 3) A 를 열고, 열린 A 를 목록에서 지우면 오류 없이 저장 전 새 배치안으로 남아요
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await page.getByRole("button", { name: "열기" }).first().click();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const opened = layoutId()!;
  await expect(page.getByRole("button", { name: "열려 있음" })).toBeDisabled();
  const name = await page.getByLabel("배치안 이름").inputValue();
  const shown = await status(page).textContent();
  gets.length = 0;
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: `${name} 삭제` }).click();
  await expect(page).toHaveURL(/\/cage$/);
  await settle();
  expect(gets).not.toContain(opened);
  await expect(page.getByText("배치안을 찾을 수 없습니다.")).toHaveCount(0);
  await expect(status(page)).toHaveText(shown!);
  await expect(page.getByLabel("배치안 이름")).toHaveValue(name);
  await expect(page.getByRole("button", { name: `${name} 삭제` })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeEnabled();
});
