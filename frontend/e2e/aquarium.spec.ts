// 어항(담수 관상어·새우): 종을 고르면 크기·수조 칸이 바뀌고, 모의 해석기로 물속 동굴을 설계해
// 결과 화면에 수조 낱말·물속 무게 안내·출력 안전 안내가 나오는지. 가상 케이지는 어항 종을 받지 않는다.
import { expect, type Page, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };
const POST_HREF = "/community/4f64bf7ac33d43e89d5d034a93ca2760";

async function login(page: Page, next = "/design") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("아이디").fill(ADMIN.username);
  await page.getByLabel("비밀번호").fill(ADMIN.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === next);
}

const sizeRadio = (page: Page, key: string) => page.locator(`input[name="size"][value="${key}"]`);
/** 크기 고르기: 라디오는 화면에서 숨기고 이름표(label)를 누른다 */
const pickSize = (page: Page, key: string) => page.locator("label", { has: sizeRadio(page, key) }).click();
/** 결과 화면의 구조물 목록 (검증 안내에도 구조물 이름이 들어간 버튼이 있어 목록 안에서 찾는다) */
const itemList = (page: Page, title = /^구조물 \(\d+\)$/) => page.getByRole("region", { name: title });

test("어항: 종을 바꾸면 크기·수조 칸이 바뀌고, 물속 동굴을 설계하면 결과 화면이 수조 기준으로 보인다", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  // 종 목록이 오기 전에는 고를 크기가 없어 다음으로 넘어가지 않는다 (목록 응답을 잠시 붙잡아 둔다)
  let release = () => {};
  const gate = new Promise<void>((r) => (release = r));
  await page.route("**/species", async (route) => {
    await gate;
    await route.continue();
  });
  await login(page);
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  const next = wizard.getByRole("button", { name: "다음" });
  await expect(next).toBeDisabled();
  release();
  await expect(next).toBeEnabled(); // 기본값 햄스터 골든
  await page.unroute("**/species");

  // 햄스터 드워프를 고른 뒤 어항으로 바꾸면 크기는 어항의 첫 크기(새우)로 바뀐다 (이전 종의 크기가 남지 않는다)
  await pickSize(page, "dwarf");
  await expect(sizeRadio(page, "dwarf")).toBeChecked();
  await wizard.getByRole("combobox", { name: "종", exact: true }).selectOption("aquarium");
  await expect(sizeRadio(page, "shrimp")).toBeChecked();
  await expect(sizeRadio(page, "dwarf")).toHaveCount(0);
  await expect(next).toBeEnabled();

  // 수조 낱말·프리셋·물 깊이 안내
  await expect(wizard.getByText("수조 크기와 물 깊이 (mm)")).toBeVisible();
  await expect(wizard.getByLabel("케이지 가로 (mm)")).toHaveCount(0);
  await expect(wizard.getByText("가로·세로는 수조 안쪽 치수로, 물 깊이는 바닥재 위부터 수면까지 재 주세요.")).toBeVisible();
  for (const name of ["30큐브 30×30×30cm", "45×30×30cm", "60×30×36cm", "60×45×45cm", "90×45×45cm"]) {
    await expect(wizard.getByRole("button", { name, exact: true })).toBeVisible();
  }
  await wizard.getByRole("button", { name: "60×30×36cm", exact: true }).click();
  await expect(wizard.getByLabel("수조 가로 (mm)")).toHaveValue("600");
  await expect(wizard.getByLabel("수조 세로 (mm)")).toHaveValue("300");
  await expect(wizard.getByLabel("물 깊이 (mm)")).toHaveValue("280");

  // 출력 안전 안내 (종 규칙의 안내 문구 + 커뮤니티 글)
  const wizardNotice = wizard.getByTestId("aquarium-print-notice");
  await expect(wizardNotice.getByRole("heading", { name: "어항에 넣을 출력물 안전 안내" })).toBeVisible();
  await expect(wizardNotice.getByText("어항 수질에 안전하다고 증명된 3D 출력 소재는 없어요", { exact: false })).toBeVisible();
  await expect(wizardNotice.getByRole("link")).toHaveAttribute("href", POST_HREF);

  // 새우는 5마리 미만이면 무리 안내. 마릿수 상한은 종마다 (어항 200)
  await expect(wizard.getByText("새우는 무리 지어 사는 동물이라 5마리 이상 함께 키우기를 권합니다.")).toBeVisible();
  await pickSize(page, "nano_fish");
  await expect(sizeRadio(page, "nano_fish")).toBeChecked();
  const count = wizard.getByLabel("마릿수");
  await count.fill("201");
  await expect(wizard.getByText("마릿수는 1~200 사이로 입력해 주세요.")).toBeVisible();
  await expect(next).toBeDisabled();
  await count.fill("10");
  await expect(wizard.getByText("마릿수는 1~200 사이로 입력해 주세요.")).toHaveCount(0);
  await expect(wizard.getByText("나노 어종은 무리를 지어야 안정됩니다", { exact: false })).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/aquarium-wizard.png`, fullPage: true });
  await next.click();

  // 2. 요구사항: 어항 예시만 (경사로·모래 목욕 예시는 없다)
  await expect(page.getByText("· 10마리 · 수조 600×300mm · 물 깊이 280mm", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "완만한 경사로를 하나 만들어 주세요" })).toHaveCount(0);
  await page.getByRole("button", { name: "네온 테트라 무리가 지나갈 터널과 동굴을 만들어 주세요" }).click();
  await expect(page.getByLabel("요구사항")).toHaveValue("네온 테트라 무리가 지나갈 터널과 동굴을 만들어 주세요");
  const meshLoaded = page.waitForResponse((r) => r.url().includes("/parts/") && r.status() === 200);
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();

  // 결과 화면: 물속 동굴 + 터널, 수조 낱말, 참고 안내, 내려받기 옆 출력 안전 안내
  await page.waitForURL(/\/designs\/[0-9a-f]+$/);
  const items = itemList(page);
  await expect(items.getByRole("button", { name: /물속 동굴 #\d/ })).toBeVisible();
  await expect(items.getByRole("button", { name: /터널 #\d/ })).toBeVisible();
  const viewer = page.getByTestId("viewer");
  await expect(viewer.locator("canvas")).toBeVisible();
  await expect(viewer.getByText("수조 600 × 300 mm · 물 깊이 280 mm")).toBeVisible();
  await expect(viewer.getByText("물 (바닥재 위~수면)")).toBeVisible();
  await expect(viewer.getByText(/케이지/)).toHaveCount(0);
  await expect(page.getByText("수조 600×300mm · 물 깊이 280mm").first()).toBeVisible(); // 제목 줄

  const validation = page.getByRole("region", { name: "안전·출력 검증" });
  await expect(validation.getByText("통과", { exact: true })).toBeVisible();
  await expect(
    validation.getByText("수조 적합, 물 깊이, 겹침, 끼임 틈새, 벽 두께, 넘어짐, 서포트 없는 출력을 모두 확인했어요."),
  ).toBeVisible();
  // 물속 무게·터널 공기 빼기는 '자동 보정'이 아니라 '참고'로 보인다
  await expect(validation.getByRole("heading", { name: "참고 (2)" })).toBeVisible();
  await expect(validation.getByText("출력물의 물속 무게는 모두 합쳐 약", { exact: false })).toBeVisible();
  await expect(validation.getByText("수평으로 놓으면 꼭대기를 따라 공기가 남아 뜰 수 있어요", { exact: false })).toBeVisible();
  await expect(validation.getByRole("heading", { name: /자동 보정한 내용/ })).toHaveCount(0);

  const download = page.getByRole("region", { name: "받기" });
  const notice = download.getByTestId("aquarium-print-notice");
  await expect(notice.getByRole("heading", { name: "어항에 넣을 출력물 안전 안내" })).toBeVisible();
  await expect(notice.getByText("채움 100%", { exact: false })).toBeVisible();
  await expect(notice.getByRole("link")).toHaveAttribute("href", POST_HREF);

  // 물속 동굴의 파라미터 이름
  await items.getByRole("button", { name: /물속 동굴 #\d/ }).click();
  await expect(items.getByText("수조 기준에 맞춰 구성했습니다", { exact: false })).toBeVisible();
  await expect(page.locator("dt", { hasText: /^꼭대기 구멍$/ })).toBeVisible();
  await expect(page.locator("dt", { hasText: /^지붕 경사$/ })).toBeVisible();
  await expect(page.locator("dd", { hasText: /^45°$/ })).toBeVisible();

  // 수정 요청 예시도 어항용 (환기구가 없다)
  await expect(page.getByRole("button", { name: "환기구를 10개로 늘려 주세요" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "출입구를 더 넓게 해 주세요" })).toBeVisible();

  // 내려받기
  const stlHref = await download.getByRole("link", { name: /STL/ }).getAttribute("href");
  const stl = await page.request.get(stlHref!);
  expect(stl.status()).toBe(200);
  expect((await stl.body()).length).toBeGreaterThan(1000);
  await meshLoaded;
  await page.waitForTimeout(1500); // 렌더가 끝날 때까지 기다려 그 사이 난 pageerror 도 잡는다
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/aquarium-design.png`, fullPage: true });
  expect(pageErrors).toEqual([]);
});

test("메인의 어항 예시를 누르면 어항 종을 고른 채 설계하기가 열린다", async ({ page }) => {
  await login(page, "/");
  await page.getByRole("link", { name: "새우가 숨을 수 있는 작은 동굴을 만들어 주세요" }).click();
  await page.waitForURL((url) => url.pathname === "/design");
  const params = new URL(page.url()).searchParams;
  expect(params.get("prompt")).toBe("새우가 숨을 수 있는 작은 동굴을 만들어 주세요");
  expect(params.get("species")).toBe("aquarium");
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  await expect(wizard.getByRole("combobox", { name: "종", exact: true })).toHaveValue("aquarium");
  await expect(sizeRadio(page, "shrimp")).toBeChecked();
  await expect(wizard.getByText("적어 주신 요청")).toBeVisible();
  await expect(wizard.getByLabel("물 깊이 (mm)")).toBeVisible();
});

test("영어 화면: 어항 수조 칸·출력 안내·결과 화면이 영어", async ({ page, context }) => {
  await login(page);
  await context.addCookies([{ name: "lang", value: "en", url: "http://localhost:3000" }]);
  await page.goto("/design");
  await expect(page).toHaveURL(/\/en\/design$/);
  const wizard = page.getByRole("region", { name: "Tell us about your habitat" });
  await wizard.getByRole("combobox", { name: "Species", exact: true }).selectOption("aquarium");
  await expect(sizeRadio(page, "shrimp")).toBeChecked();
  await expect(wizard.getByText("Tank size and water depth (mm)")).toBeVisible();
  await expect(wizard.getByLabel("Tank width (mm)")).toBeVisible();
  await expect(wizard.getByLabel("Tank depth (mm)")).toBeVisible();
  await expect(wizard.getByLabel("Water depth (mm)")).toBeVisible();
  await wizard.getByRole("button", { name: "60×30×36cm", exact: true }).click();
  const wizardNotice = wizard.getByTestId("aquarium-print-notice");
  await expect(wizardNotice.getByRole("heading", { name: "Print safety for aquarium pieces" })).toBeVisible();
  await expect(wizardNotice).not.toHaveText(/[가-힣]/); // 안내 항목도 서버가 영어로 보낸다
  await wizard.getByLabel("Number of pets").fill("5");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Make a small cave where shrimp can hide" }).click();
  await page.getByRole("button", { name: "Get a custom design" }).click();
  await page.waitForURL(/\/en\/designs\/[0-9a-f]{32}/);
  await expect(itemList(page, /^Structures \(\d+\)$/).getByRole("button", { name: /Underwater cave #1/ })).toBeVisible();
  await expect(page.getByTestId("viewer").getByText("Tank 600 × 300 mm · Water depth 280 mm")).toBeVisible();
  const validation = page.getByRole("region", { name: "Safety & print check" });
  await expect(validation.getByRole("heading", { name: "Notes (1)" })).toBeVisible();
  await expect(validation).not.toHaveText(/[가-힣]/);
  const download = page.getByRole("region", { name: "Download" });
  await expect(download.getByRole("heading", { name: "Print safety for aquarium pieces" })).toBeVisible();
  await expect(download).not.toHaveText(/[가-힣]/);
});

test("가상 케이지는 어항 종을 고를 수 없고, 임시 저장에 남은 어항 종은 기본값으로 바뀐다", async ({ page }) => {
  await page.goto("/cage");
  const pick = page.getByLabel("반려동물 종·크기 (검토 기준)");
  await expect(pick).toBeEnabled();
  await expect(pick.locator("option")).toHaveText(["햄스터 · 드워프 (정글리안·캠벨·로보로브스키)", "햄스터 · 골든 (시리안)"]);
  await expect(pick.locator("option", { hasText: "어항" })).toHaveCount(0);

  // 가상 케이지 화면이 떠 있으면 지금 상태를 임시 저장에 쓰므로, 다른 화면에서 심는다
  await page.goto("/explore");
  await page.evaluate(() =>
    window.localStorage.setItem(
      "nestforge:cage-draft:v1",
      JSON.stringify({
        name: "어항 임시 저장", species: "aquarium", size: "nano_fish", petId: null, layoutId: null,
        cage: { width_mm: 600, depth_mm: 300, height_mm: 280 },
        items: [],
      }),
    ),
  );
  await page.goto("/cage");
  await expect(
    page.getByText("가상 케이지는 케이지에서 키우는 동물만 지원해요. 검토 기준 종·크기를 기본값으로 바꿨어요."),
  ).toBeVisible();
  await expect(pick).toHaveValue("hamster/syrian");
});
