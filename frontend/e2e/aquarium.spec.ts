// 어항(담수 관상어·새우): 종을 고르면 크기·수조 칸이 바뀌고, 모의 해석기로 물속 동굴을 설계해
// 결과 화면에 수조 낱말·물속 무게 안내·출력 안전 안내가 나오는지. 가상 케이지는 어항 종을 받지 않는다.
import { expect, type Page, test } from "@playwright/test";

import { signup } from "./support";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const ADMIN = { username: "admin", password: "e2e-admin-password" };
const POST_HREF = "/community/4f64bf7ac33d43e89d5d034a93ca2760";
const API = "http://localhost:8000";
const RUN = Date.now().toString(36).slice(-5); // 실행마다 다른 아이디 (같은 DB 를 재사용해도 겹치지 않게)

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
  await expect(
    wizard.getByText(
      "가로·세로는 수조 안쪽 치수(유리 안쪽 사이)로, 물 깊이는 바닥재 위부터 수면까지 재 주세요. 바닥·부피 기준은 유리 두께를 더한 겉 크기로 비교해요.",
    ),
  ).toBeVisible();
  // 크기 구분 안내: 몸길이 기준과 아주 작은 종은 합사 수조 (서버 size_hint_ko)
  await expect(wizard.getByTestId("size-hint")).toContainText("꼬리지느러미를 뺀 길이");
  await expect(wizard.getByTestId("size-hint")).toContainText("'합사 수조'");
  for (const name of ["30큐브 30×30×30cm", "45×30×30cm", "60×30×36cm", "60×45×45cm", "90×45×45cm"]) {
    await expect(wizard.getByRole("button", { name, exact: true })).toBeVisible();
  }
  // 버튼 이름은 겉 크기, 채우는 값은 안쪽 치수(유리 6mm 를 뺀다)와 물 깊이(바닥 유리·바닥재 5cm·윗여유 3cm 를 뺀다)
  await wizard.getByRole("button", { name: "60×30×36cm", exact: true }).click();
  await expect(wizard.getByLabel("수조 가로 (mm)")).toHaveValue("588");
  await expect(wizard.getByLabel("수조 세로 (mm)")).toHaveValue("288");
  await expect(wizard.getByLabel("물 깊이 (mm)")).toHaveValue("274");

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

  // 2. 요구사항: 어항 예시만 (경사로·모래 목욕 예시는 없다). 동물 이름이 든 예시는 고른 크기 구분(나노 어종)의 것만
  await expect(page.getByText("· 10마리 · 수조 588×288mm · 물 깊이 274mm", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "완만한 경사로를 하나 만들어 주세요" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "코리도라스용으로 앞뒤가 뚫린 동굴 두 개" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "새우가 숨을 수 있는 작은 동굴을 만들어 주세요" })).toHaveCount(0);
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
  await expect(viewer.getByText("수조 588 × 288 mm · 물 깊이 274 mm")).toBeVisible();
  await expect(viewer.getByText("물 (바닥재 위~수면)")).toBeVisible();
  await expect(viewer.getByText(/케이지/)).toHaveCount(0);
  await expect(page.getByText("수조 588×288mm · 물 깊이 274mm").first()).toBeVisible(); // 제목 줄

  const validation = page.getByRole("region", { name: "안전·출력 검증" });
  await expect(validation.getByText("통과", { exact: true })).toBeVisible();
  await expect(
    validation.getByText("수조 적합, 물 깊이, 겹침, 끼임 틈새, 벽 두께, 넘어짐, 서포트 없는 출력을 모두 확인했어요."),
  ).toBeVisible();
  // 물속 무게·터널 공기 빼기는 '자동 보정'이 아니라 '참고'로 보인다.
  // 60×30×36cm 수조(겉 크기로 어림 64.8L)는 100L 보다 작아 나노 어종 권장 부피 안내도 참고로 붙는다
  await expect(validation.getByRole("heading", { name: "참고 (3)" })).toBeVisible();
  await expect(validation.getByText("54L는 최소 기준일 뿐이에요.", { exact: false })).toBeVisible();
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
  await expect(page.locator("dt", { hasText: /^지붕 기울기$/ })).toBeVisible();
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

test("메인 예시는 종(어항은 크기까지)을 정해 열어, 전에 고른 어항이 햄스터 예시에 남지 않는다", async ({ page }) => {
  // 설계하기 화면은 다른 화면에 다녀와도 숨김 상태로 남아 있어 고른 종이 그대로다: 예시가 종을 정해 주어야 한다
  await login(page, "/");
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  const speciesSelect = wizard.getByRole("combobox", { name: "종", exact: true });
  const openExample = async (name: string) => {
    if (new URL(page.url()).pathname !== "/") {
      await page.getByRole("link", { name: "NestForge 홈" }).click(); // 화면 안 이동 (새로 고침하지 않는다)
      await page.waitForURL((url) => url.pathname === "/");
    }
    await page.getByRole("link", { name, exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/design" && url.searchParams.get("prompt") === name);
  };
  /** 다음을 눌러 요구사항 단계의 요약 줄을 본다 (들어올 때의 효과가 모두 적용된 뒤) */
  const summaryAfterNext = async (text: string) => {
    await wizard.getByRole("button", { name: "다음" }).click();
    await expect(page.getByText(text, { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "이전" }).click();
  };

  // 햄스터 예시: 종을 정해 열지만 기본 크기(골든)는 그대로
  await openExample("완만한 경사로를 하나 만들어 주세요");
  expect(new URL(page.url()).searchParams.get("species")).toBe("hamster");
  await expect(speciesSelect).toHaveValue("hamster");
  await summaryAfterNext("햄스터 골든 (시리안) · 1마리 · 케이지");

  // 어항 예시는 문장에 나온 새우의 크기 구분까지 정한다 (어항에서 다른 크기를 골라 두었어도)
  await openExample("새우가 숨을 수 있는 작은 동굴을 만들어 주세요");
  expect(new URL(page.url()).searchParams.get("size")).toBe("shrimp");
  await expect(speciesSelect).toHaveValue("aquarium");
  await expect(sizeRadio(page, "shrimp")).toBeChecked();
  await pickSize(page, "nano_fish");
  await expect(sizeRadio(page, "nano_fish")).toBeChecked();
  await openExample("새우가 숨을 수 있는 작은 동굴을 만들어 주세요");
  await expect(sizeRadio(page, "shrimp")).toBeChecked();

  // 그 뒤 햄스터 예시를 누르면 햄스터 케이지로 돌아온다 (어항 동굴로 설계하지 않는다)
  await openExample("완만한 경사로를 하나 만들어 주세요");
  await expect(speciesSelect).toHaveValue("hamster");
  await expect(wizard.getByLabel("케이지 가로 (mm)")).toBeVisible();
  await expect(wizard.getByLabel("물 깊이 (mm)")).toHaveCount(0);
  await wizard.getByRole("button", { name: "다음" }).click();
  await expect(page.getByLabel("요구사항")).toHaveValue("완만한 경사로를 하나 만들어 주세요");
  await expect(page.getByRole("button", { name: "모래 목욕용 통을 하나 만들고 싶어요" })).toBeVisible(); // 케이지 예시
  await page.getByRole("button", { name: "이전" }).click();

  // 같은 종의 예시를 다시 누르면 고른 크기를 그대로 둔다
  await pickSize(page, "syrian");
  await openExample("케이지 한쪽에 놓을 긴 터널이 필요해요");
  await summaryAfterNext("햄스터 골든 (시리안) · 1마리 · 케이지");
});

test("반려동물을 고른 뒤 다른 종으로 바꾸면 반려동물 연결을 끊고, 반려동물 없이 설계한다", async ({ page }) => {
  await signup(page, { username: `aqpet_${RUN}`, nickname: `어항${RUN}`, password: "aqua-pet-pass-321" }, { next: "/" });
  const created = await page.request.post(`${API}/me/pets`, {
    data: { name: "콩이", species: "hamster", size: "syrian", cage: { width_mm: 600, depth_mm: 400, height_mm: 300 } },
  });
  expect(created.status()).toBe(201);
  const petId = ((await created.json()) as { id: string }).id;

  // "이 아이로 설계하기"로 들어오면 반려동물로 채운다. 크기를 바꿔도 연결은 그대로
  await page.goto(`/design?pet=${petId}`);
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  const petSelect = wizard.getByRole("combobox", { name: "내 반려동물" });
  const speciesSelect = wizard.getByRole("combobox", { name: "종", exact: true });
  const unlinked = wizard.getByText("종을 바꿔서 반려동물 연결을 해제했어요. 아래 값을 확인해 주세요.");
  await expect(petSelect).toHaveValue(petId);
  await pickSize(page, "dwarf");
  await expect(petSelect).toHaveValue(petId);
  await expect(unlinked).toHaveCount(0);

  // 종을 어항으로 바꾸면 연결을 끊고 알린다 (서버는 종이 다른 반려동물로 사육 환경을 만들지 않는다)
  await speciesSelect.selectOption("aquarium");
  await expect(petSelect).toHaveValue("");
  await expect(unlinked).toBeVisible();
  await wizard.getByRole("button", { name: "60×30×36cm", exact: true }).click();
  await wizard.getByLabel("마릿수").fill("10");
  await wizard.getByRole("button", { name: "다음" }).click();
  await expect(page.getByText("어항 (담수 관상어·새우) 새우", { exact: false })).toBeVisible();
  await expect(page.getByText("콩이 ·", { exact: false })).toHaveCount(0);
  await page.getByRole("button", { name: "새우가 숨을 수 있는 작은 동굴을 만들어 주세요" }).click();
  const habitatSent = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/habitats");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  expect((await habitatSent).postDataJSON()).toMatchObject({ species: "aquarium", size: "shrimp", pet_id: null });
  await page.waitForURL(/\/designs\/[0-9a-f]{32}$/);
  await expect(itemList(page).getByRole("button", { name: /물속 동굴 #1/ })).toBeVisible();

  // 메인의 어항 예시(?species=aquarium)로 종이 바뀔 때도 같다
  await page.goto(`/design?pet=${petId}`);
  await expect(petSelect).toHaveValue(petId);
  await expect(speciesSelect).toHaveValue("hamster");
  await page.getByRole("link", { name: "NestForge 홈" }).click();
  await page.waitForURL((url) => url.pathname === "/");
  await page.getByRole("link", { name: "새우가 숨을 수 있는 작은 동굴을 만들어 주세요" }).click();
  await page.waitForURL((url) => url.pathname === "/design");
  await expect(speciesSelect).toHaveValue("aquarium");
  await expect(petSelect).toHaveValue("");
  await expect(unlinked).toBeVisible();

  // 그래도 서버가 종이 다르다고 거절하면(다른 탭에서 반려동물의 종을 고친 경우 등) 연결을 끊고, 다시 누르면 설계된다
  await page.goto(`/design?pet=${petId}`);
  await expect(petSelect).toHaveValue(petId);
  await page.route(`${API}/habitats`, (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 422,
          json: { detail: { code: "pet_species_mismatch", message_ko: "반려동물 정보와 종이 다릅니다." } },
        })
      : route.continue(),
  );
  await wizard.getByRole("button", { name: "다음" }).click();
  await page.getByRole("button", { name: "완만한 경사로를 하나 만들어 주세요" }).click();
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await expect(
    page.getByRole("alert").getByText("고른 반려동물과 종이 달라서 반려동물 연결을 해제했어요. 다시 누르면 반려동물 연결 없이 설계해요."),
  ).toBeVisible();
  await page.unroute(`${API}/habitats`);
  const retried = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/habitats");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  expect((await retried).postDataJSON()).toMatchObject({ species: "hamster", pet_id: null });
  await page.waitForURL(/\/designs\/[0-9a-f]{32}$/);
});

test("어항 요구사항 예시는 고른 크기 구분의 동물만 이름을 든다", async ({ page }) => {
  await login(page);
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  await wizard.getByRole("combobox", { name: "종", exact: true }).selectOption("aquarium");
  await wizard.getByRole("button", { name: "60×30×36cm", exact: true }).click();
  await wizard.getByLabel("마릿수").fill("10");
  const chip = (name: string) => page.getByRole("button", { name, exact: true });
  const SHRIMP = "새우가 숨을 수 있는 작은 동굴을 만들어 주세요";
  const NEON = "네온 테트라 무리가 지나갈 터널과 동굴을 만들어 주세요";
  const CORY = "코리도라스용으로 앞뒤가 뚫린 동굴 두 개";
  const MIXED = "새우와 작은 물고기가 함께 숨을 수 있는 동굴을 만들어 주세요";
  const cases: [string, string, string[]][] = [
    ["shrimp", SHRIMP, [NEON, CORY, MIXED]],
    ["nano_fish", NEON, [SHRIMP, CORY, MIXED]],
    // 코리도라스 동굴을 새우 기준(구멍 20mm)으로 만들지 않게: 코리도라스 예시는 소형 어종에서만
    ["small_fish", CORY, [SHRIMP, NEON, MIXED]],
    ["community", MIXED, [SHRIMP, NEON, CORY]],
  ];
  for (const [size, shown, hidden] of cases) {
    await pickSize(page, size);
    await wizard.getByRole("button", { name: "다음" }).click();
    await expect(chip(shown)).toBeVisible();
    for (const name of hidden) await expect(chip(name)).toHaveCount(0);
    // 동물 이름이 없는 예시는 어느 크기 구분에서나 하나 이상 보인다
    await expect(chip("앞뒤가 뚫린 동굴을 하나 만들어 주세요").or(chip("터널 하나와 동굴 하나를 만들어 주세요")).first()).toBeVisible();
    await page.getByRole("button", { name: "이전" }).click();
  }
});

test("메인 그림의 이름표: 물속 동굴·은신처는 한 줄로, 다른 이름표와 겹치지 않는다 (좁은 화면·영어 포함)", async ({ page }) => {
  for (const [path, cave, hideout] of [
    ["/", "물속 동굴", "은신처"],
    ["/en", "Underwater cave", "Hideout"],
  ] as const) {
    // 그림은 md(768px) 이상에서 보인다. 영어 이름표가 가장 긴 좁은 폭부터 넓은 폭까지
    for (const width of [768, 800, 834, 900, 1024, 1400]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      const chips = page.locator('section[aria-labelledby="hero-title"] div[aria-hidden] > span');
      await expect(chips).toHaveCount(5);
      const boxes = await chips.evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return { text: e.textContent?.trim() ?? "", left: r.left, top: r.top, right: r.right, bottom: r.bottom, height: r.height };
        }),
      );
      for (const label of [cave, hideout]) {
        const a = boxes.find((b) => b.text === label);
        expect(a, `${path} ${width}px: ${label}`).toBeDefined();
        expect(a!.height, `${path} ${width}px: ${label} 한 줄`).toBeLessThan(45);
        for (const b of boxes) {
          if (b === a) continue;
          const overlap = Math.min(a!.right, b.right) > Math.max(a!.left, b.left) && Math.min(a!.bottom, b.bottom) > Math.max(a!.top, b.top);
          expect(overlap, `${path} ${width}px: ${label} × ${b.text}`).toBe(false);
        }
      }
    }
  }
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
  await expect(wizard.getByTestId("size-hint")).toContainText("Body length means the adult length without the tail fin.");
  await wizard.getByLabel("Number of pets").fill("5");
  await page.getByRole("button", { name: "Next" }).click();
  // 영어 크기 이름에 동물 이름이 들어 있어 종 이름을 다시 붙이지 않는다
  await expect(
    page.getByText("Shrimp (cherry, bee and other dwarf shrimp only) · 5 animal(s) · Tank 588×288mm · Water depth 274mm"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Make a small cave where shrimp can hide" }).click();
  await page.getByRole("button", { name: "Get a custom design" }).click();
  await page.waitForURL(/\/en\/designs\/[0-9a-f]{32}/);
  await expect(itemList(page, /^Structures \(\d+\)$/).getByRole("button", { name: /Underwater cave #1/ })).toBeVisible();
  await expect(page.getByTestId("viewer").getByText("Tank 588 × 288 mm · Water depth 274 mm")).toBeVisible();
  // 물속 동굴의 지붕 기울기는 Roof slope (집의 지붕 경사 Roof pitch 와 다른 사전 열쇠)
  await itemList(page, /^Structures \(\d+\)$/).getByRole("button", { name: /Underwater cave #1/ }).click();
  await expect(page.locator("dt", { hasText: /^Roof slope$/ })).toBeVisible();
  await expect(page.locator("dt", { hasText: /^Roof pitch$/ })).toHaveCount(0);
  const validation = page.getByRole("region", { name: "Safety & print check" });
  await expect(validation.getByRole("heading", { name: "Notes (1)" })).toBeVisible();
  await expect(validation).not.toHaveText(/[가-힣]/);
  const download = page.getByRole("region", { name: "Download" });
  await expect(download.getByRole("heading", { name: "Print safety for aquarium pieces" })).toBeVisible();
  await expect(download).not.toHaveText(/[가-힣]/);
});

test("영어 화면: 햄스터 집의 지붕 경사는 main 그대로 Roof pitch (물속 동굴의 Roof slope 와 섞이지 않는다)", async ({ page }) => {
  await login(page, "/");
  const h = await page.request.post(`${API}/habitats`, {
    data: { species: "hamster", size: "syrian", count: 1, cage: { width_mm: 1000, depth_mm: 500, height_mm: 500 } },
  });
  expect(h.status()).toBe(201);
  const d = await page.request.post(`${API}/designs`, {
    data: { habitat_id: (await h.json()).id, prompt: "경사 지붕 집을 만들어 주세요" },
  });
  expect(d.status()).toBe(201);
  const { id } = (await d.json()) as { id: string };

  await page.goto(`/en/designs/${id}`);
  // 구조물 이름표는 서버 카탈로그(main 그대로 "집" → "house")가 번역한다
  await itemList(page, /^Structures \(\d+\)$/).getByRole("button", { name: /^house #1/i }).click();
  await expect(page.locator("dt", { hasText: /^Roof pitch$/ })).toBeVisible();
  await expect(page.locator("dd", { hasText: /^50°$/ })).toBeVisible();
  await expect(page.locator("dt", { hasText: /^Roof slope$/ })).toHaveCount(0);

  await page.goto(`/designs/${id}`);
  await itemList(page).getByRole("button", { name: /^집 #1/ }).click();
  await expect(page.locator("dt", { hasText: /^지붕 경사$/ })).toBeVisible();
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
