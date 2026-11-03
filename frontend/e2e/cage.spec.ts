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
  // 옛 배치안을 다시 불러오는 요청은 주소가 바뀌기 전 렌더의 효과에서 나가요. 그래서 주소가 바뀐 것을 먼저 확인하고
  // (각 단계의 toHaveURL·poll), 늦게 나가는 요청까지 잡도록 잠깐 더 기다린 뒤 요청 목록을 봐요
  const settle = () => page.waitForTimeout(500);

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

/** 요청을 붙잡아 두었다가 release() 하면 보내요 */
function gate() {
  let release!: () => void;
  const opened = new Promise<void>((r) => (release = r));
  return { opened, release };
}

test("로그인 확인이 늦어도 브라우저 임시 저장은 바로 되살리고, 그사이 새로 만든 배치는 덮어쓰지 않는다", async ({ page }) => {
  const gets: string[] = [];
  page.on("request", (r) => {
    const m = r.method() === "GET" && /\/layouts\/([0-9a-f]{32})$/.exec(new URL(r.url()).pathname);
    if (m) gets.push(m[1]);
  });
  await signup(page, { username: `cagelate_${RUN}`, nickname: `케늦음${RUN}`, password: "password-123" }, { next: "/cage" });
  await page.goto("/cage");
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await page.getByLabel("배치안 이름").fill("배치 A");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const a = /layout=([0-9a-f]{32})/.exec(page.url())![1];

  // 1) 로그인 확인(/auth/me)을 붙잡은 채 저장한 배치안 주소로 들어가 '새로 만들기' → 확인이 끝나도 새 배치가 그대로
  let g = gate();
  await page.route("**/auth/me", async (route) => {
    await g.opened;
    await route.continue();
  });
  await page.goto(`/cage?layout=${a}`);
  await expect(page.getByRole("heading", { level: 1, name: "가상 케이지 공간 설계" })).toBeVisible();
  await page.getByRole("button", { name: "새로 만들기" }).click();
  await expect(page).toHaveURL(/\/cage$/);
  await page.getByRole("button", { name: "밥그릇 추가" }).click();
  await page.getByLabel("배치안 이름").fill("새 작업");
  gets.length = 0;
  g.release();
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeVisible(); // 로그인 확인이 끝남
  await page.waitForTimeout(500);
  expect(gets).toEqual([]);
  await expect(page).toHaveURL(/\/cage$/);
  await expect(page.getByLabel("배치안 이름")).toHaveValue("새 작업");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");

  // 2) 로그인 확인을 붙잡은 채 /cage 로 들어오면 임시 저장('새 작업')을 바로 되살리고, 그 뒤의 작업을 덮어쓰지 않아요
  g = gate();
  await page.goto("/cage");
  await expect(page.getByLabel("배치안 이름")).toHaveValue("새 작업");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "새로 만들기" }).click();
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await page.getByRole("button", { name: "밥그릇 추가" }).click();
  g.release();
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeVisible();
  await page.waitForTimeout(500);
  await expect(page.getByLabel("배치안 이름")).toHaveValue("새 배치안");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 2개");
  await page.unroute("**/auth/me");
});

test("배치안을 불러오는 중에 뒤로 가면 늦게 온 응답이 화면을 바꾸지 않고, 불러오기에 실패한 배치안은 '열기'로 다시 연다", async ({ page }) => {
  await signup(page, { username: `cageseq_${RUN}`, nickname: `케순서${RUN}`, password: "password-123" }, { next: "/cage" });
  await page.goto("/cage");
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await page.getByLabel("배치안 이름").fill("배치 A");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const a = /layout=([0-9a-f]{32})/.exec(page.url())![1];
  await page.getByRole("button", { name: "밥그릇 추가" }).click();
  await page.getByLabel("배치안 이름").fill("배치 B");
  await page.getByRole("button", { name: "새 배치안으로 저장" }).click();
  await expect.poll(() => /layout=([0-9a-f]{32})/.exec(page.url())?.[1]).not.toBe(a);
  const b = /layout=([0-9a-f]{32})/.exec(page.url())![1];

  // A 를 연 뒤, B 를 여는 응답을 붙잡아 둔 채 뒤로 가기(A) → 늦게 온 B 응답은 버려요
  await page.getByRole("button", { name: "새로 만들기" }).click();
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await page.getByRole("button", { name: "열기" }).nth(1).click(); // 목록은 최근 것부터: [B, A]
  await expect(page).toHaveURL(new RegExp(`layout=${a}$`));
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 A");
  const g = gate();
  let bServed = false;
  await page.route(`**/layouts/${b}`, async (route) => {
    await g.opened;
    await route.continue();
    bServed = true;
  });
  await page.getByRole("button", { name: "열기" }).first().click();
  await expect(page).toHaveURL(new RegExp(`layout=${b}$`));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`layout=${a}$`));
  g.release();
  await expect.poll(() => bServed).toBe(true);
  await page.waitForTimeout(500);
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 A");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  await expect(page.getByRole("button", { name: "열려 있음" })).toBeDisabled();
  await page.unroute(`**/layouts/${b}`);

  // 불러오기에 한 번 실패한 배치안(B)은 목록의 '열기'로 다시 열 수 있어요 (주소가 이미 B 라도)
  let failed = false;
  await page.route(`**/layouts/${b}`, async (route) => {
    if (failed) return route.continue();
    failed = true;
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "unavailable", message_ko: "잠시 뒤 다시 시도해 주세요." } }) });
  });
  await page.goto(`/cage?layout=${b}`);
  await expect(page.getByText("잠시 뒤 다시 시도해 주세요.")).toBeVisible();
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await page.getByRole("button", { name: "열기" }).first().click();
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 B");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 2개");
  await expect(page).toHaveURL(new RegExp(`layout=${b}$`));
  await page.unroute(`**/layouts/${b}`);
});

test("저장을 기다리는 사이 다른 화면에 다녀오거나 다른 배치안으로 돌아가도 화면·주소가 어긋나지 않는다", async ({ page }) => {
  const layoutOf = () => /[?&]layout=([0-9a-f]{32})/.exec(page.url())?.[1] ?? null;
  /** 다음 POST /layouts 하나를 붙잡아 두어요 */
  const holdNextCreate = async () => {
    const g = gate();
    await page.route(
      (u) => new URL(u).pathname.endsWith("/layouts"),
      async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        await g.opened;
        await route.continue();
      },
      { times: 1 },
    );
    const response = page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/layouts"));
    return { release: g.release, response };
  };
  /** 붙잡아 둔 저장을 보내고, 응답을 받은 뒤 화면이 그 결과를 처리할 때까지 기다려요 */
  const finish = async (hold: Awaited<ReturnType<typeof holdNextCreate>>) => {
    hold.release();
    expect((await hold.response).status()).toBe(201);
    await page.waitForTimeout(300);
  };
  const row = (name: string) => page.getByRole("listitem").filter({ has: page.getByText(name, { exact: true }) });

  await signup(page, { username: `cagenav_${RUN}`, nickname: `케이동${RUN}`, password: "password-123" }, { next: "/cage" });
  await page.goto("/cage");
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await page.getByLabel("배치안 이름").fill("배치 A");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const a = layoutOf()!;

  // 1) A 를 '새 배치안으로 저장'하는 동안 이어서 놓고 다른 화면(내 정보)에 갔다가 저장이 끝난 뒤 뒤로 가기
  //    → 새 배치안(C) 주소로 맞춰지고, 저장 뒤에 놓은 것도 그대로 (A 를 다시 불러오지 않음)
  await page.getByLabel("배치안 이름").fill("배치 C");
  let hold = await holdNextCreate();
  await page.getByRole("button", { name: "새 배치안으로 저장" }).click();
  await expect(page.getByRole("button", { name: "저장 중…" })).toBeVisible();
  await page.getByRole("button", { name: "밥그릇 추가" }).click();
  await page.getByRole("navigation", { name: "주 메뉴" }).getByRole("link", { name: "내 정보" }).click();
  await expect(page).toHaveURL(/\/me$/);
  await finish(hold);
  await expect(page).toHaveURL(/\/me$/); // 저장이 끝나도 /cage 로 끌려가지 않아요
  await page.goBack();
  await expect.poll(layoutOf).not.toBe(a);
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const c = layoutOf()!;
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 C");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 2개");
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeEnabled(); // 저장 뒤에 놓은 밥그릇 → 저장할 변경 있음

  // 2) A 를 연 채 '새 배치안으로 저장'하는 동안 뒤로 가기(C) → 저장이 끝나도 C 화면에 다른 이름·ID 가 붙지 않아요
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("저장했어요.", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await page.getByRole("button", { name: "열기" }).first().click(); // [C(열려 있음), A] → A
  await expect(page).toHaveURL(new RegExp(`layout=${a}$`));
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 A");
  await page.getByLabel("배치안 이름").fill("배치 D");
  hold = await holdNextCreate();
  await page.getByRole("button", { name: "새 배치안으로 저장" }).click();
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`layout=${c}$`));
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 C");
  // C 를 다 불러와도 저장은 아직 진행 중이에요
  await expect(page.getByRole("button", { name: "저장 중…" })).toBeVisible();
  await finish(hold);
  await expect(page.getByText('"배치 D" 배치안으로 저장했어요. 내 배치안에서 열 수 있어요.')).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`layout=${c}$`));
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 C");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 2개");
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeDisabled(); // C 는 저장한 그대로
  await expect(page.getByText("배치 D", { exact: true })).toBeVisible(); // 목록에는 새 배치안이 있어요

  // 3) C 를 '새 배치안으로 저장'하는 동안 메뉴의 '가상 케이지'를 눌러도(주소만 /cage, 화면은 그대로) 새 배치안(E)으로 이어져요.
  //    이어서 저장하면 E 가 바뀌고 C 는 그대로예요
  await page.getByLabel("배치안 이름").fill("배치 E");
  hold = await holdNextCreate();
  await page.getByRole("button", { name: "새 배치안으로 저장" }).click();
  await page.getByRole("navigation", { name: "주 메뉴" }).getByRole("link", { name: "가상 케이지" }).click();
  await expect(page).toHaveURL(/\/cage$/);
  await finish(hold);
  await expect(page.getByText("새 배치안으로 저장했어요.")).toBeVisible();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  const e = layoutOf()!;
  expect([a, c]).not.toContain(e);
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 E");
  await expect(row("배치 E").getByRole("button", { name: "열려 있음" })).toBeDisabled();
  await page.getByRole("tab", { name: "카탈로그" }).click();
  await page.getByRole("button", { name: "땅굴 상자 추가" }).click();
  await page.getByRole("tab", { name: "내 배치안" }).click();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("저장했어요.", { exact: true })).toBeVisible();
  await expect(row("배치 E")).toContainText("구조물 3개");
  await expect(row("배치 C")).toContainText("구조물 2개");

  // 4) A 를 '새 배치안으로 저장'하는 동안 뒤로(E, 불러오는 중) 갔다가 바로 앞으로(A) 오면 같은 배치가 그대로라 새 배치안(F)으로 이어져요
  await row("배치 A").getByRole("button", { name: "열기" }).click();
  await expect(page).toHaveURL(new RegExp(`layout=${a}$`));
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 A");
  const ge = gate();
  await page.route(`**/layouts/${e}`, async (route) => {
    await ge.opened;
    await route.continue();
  });
  await page.getByLabel("배치안 이름").fill("배치 F");
  hold = await holdNextCreate();
  await page.getByRole("button", { name: "새 배치안으로 저장" }).click();
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`layout=${e}$`));
  await page.goForward();
  await expect(page).toHaveURL(new RegExp(`layout=${a}$`));
  await finish(hold);
  ge.release();
  await page.waitForTimeout(300);
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  expect([a, c, e]).not.toContain(layoutOf());
  await expect(page.getByLabel("배치안 이름")).toHaveValue("배치 F");
  await expect(row("배치 F").getByRole("button", { name: "열려 있음" })).toBeDisabled();
  await expect(row("배치 A")).toContainText("구조물 1개");
  await page.unroute(`**/layouts/${e}`);
});

test("임시 저장이 이 계정에 없는 반려동물을 가리켜도 저장할 수 있다", async ({ page }) => {
  await signup(page, { username: `cagepet_${RUN}`, nickname: `케반려${RUN}`, password: "password-123" }, { next: "/cage" });
  // 가상 케이지 화면이 떠 있으면 빈 상태를 임시 저장에 쓰므로, 다른 화면에서 심어요
  await page.goto("/me");
  // 같은 브라우저를 쓰던 다른 계정의 임시 저장(반려동물 연결 포함)
  await page.evaluate(() =>
    window.localStorage.setItem(
      "nestforge:cage-draft:v1",
      JSON.stringify({
        name: "남의 임시 저장", species: "hamster", size: "syrian", petId: "f".repeat(32), layoutId: null,
        cage: { width_mm: 1000, depth_mm: 500, height_mm: 500 },
        items: [{ id: "x1", asset: "bowl", x_mm: 200, y_mm: 200, rotation_deg: 0 }],
      }),
    ),
  );
  // 내 반려동물 목록을 받지 못해도(서버 오류) 저장할 수 있어야 해요: 서버가 알려 주면 연결만 빼고 다시 저장
  await page.route("**/me/pets", (route) =>
    route.request().method() === "GET" ? route.fulfill({ status: 503, contentType: "application/json", body: "{}" }) : route.continue(),
  );
  await page.goto("/cage");
  await expect(page.getByLabel("배치안 이름")).toHaveValue("남의 임시 저장");
  await expect(status(page)).toHaveText("케이지 1000×500×500mm · 구조물 1개");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText("새 배치안으로 저장했어요. 연결된 반려동물을 찾을 수 없어 반려동물 연결은 빼고 저장했어요.")).toBeVisible();
  await expect(page).toHaveURL(/\/cage\?layout=[0-9a-f]{32}$/);
  await page.unroute("**/me/pets");
});
