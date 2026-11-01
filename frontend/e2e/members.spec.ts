import { expect, type Page, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const RUN = Date.now().toString(36).slice(-5); // 실행마다 다른 아이디 (같은 DB 를 재사용해도 겹치지 않게)

async function signup(page: Page, username: string, nickname: string, password: string, next = "/") {
  await page.goto(`/signup?next=${encodeURIComponent(next)}`);
  await page.getByLabel("아이디").fill(username);
  await page.getByLabel("닉네임").fill(nickname);
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("button", { name: "가입하기" }).click();
  await page.waitForURL((url) => url.pathname === next);
  await expect(page.getByRole("banner").getByText(nickname)).toBeVisible();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.waitForURL((url) => url.pathname === "/");
  await expect(page.getByRole("banner").getByRole("link", { name: "로그인" })).toBeVisible();
}

test("로그인하지 않으면 회원 기능 대신 안내가 보이고, 커뮤니티는 읽을 수 있다", async ({ page }) => {
  await page.goto("/designs");
  await expect(page.getByText("로그인하면 내 설계 내역을 볼 수 있어요")).toBeVisible();
  await page.goto("/me");
  await expect(page.getByText("로그인하고 내 정보를 관리해 보세요")).toBeVisible();
  await page.goto("/community/new");
  await expect(page.getByText("로그인하고 글을 써 보세요")).toBeVisible();
  await page.goto("/community");
  await expect(page.getByRole("heading", { level: 1, name: "커뮤니티" })).toBeVisible();
});

test("회원가입: 입력 확인과 중복 아이디", async ({ page }) => {
  const username = `dup_${RUN}`;
  await signup(page, username, `중복검사${RUN}`, "password-123");
  await logout(page);

  await page.goto("/signup");
  await page.getByLabel("아이디").fill(username);
  await page.getByLabel("닉네임").fill(`다른닉${RUN}`);
  await page.getByLabel("비밀번호", { exact: true }).fill("password-123");
  await page.getByLabel("비밀번호 확인").fill("password-999");
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page.getByText("비밀번호가 서로 달라요. 다시 확인해 주세요.")).toBeVisible();
  await page.getByLabel("비밀번호 확인").fill("password-123");
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "이미 사용 중인 아이디예요." })).toBeVisible();
  await expect(page).toHaveURL(/\/signup/);
});

test("회원가입 → 반려동물 등록 → 반려동물로 설계 → 내 설계 → 커뮤니티 공유 → 다른 회원의 댓글·읽기 전용 보기", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const a = { username: `kong_${RUN}`, nickname: `콩이맘${RUN}`, password: "hamster-love-123" };
  const b = { username: `tunnel_${RUN}`, nickname: `터널아빠${RUN}`, password: "tunnel-dad-456" };

  // 1. 회원가입 (가입하면 바로 로그인)
  await signup(page, a.username, a.nickname, a.password);
  await expect(page.getByRole("heading", { name: "내 공간" })).toBeVisible();

  // 2. 내 정보 → 반려동물 등록
  await page.goto("/me");
  await expect(page.getByRole("heading", { level: 1, name: "내 정보" })).toBeVisible();
  await page.getByRole("button", { name: "반려동물 등록" }).first().click();
  await page.getByLabel("이름").fill("콩이");
  await page.getByLabel("종").selectOption("hamster");
  await page.getByLabel("크기").selectOption("syrian");
  await page.getByLabel("암컷").check();
  await page.getByRole("button", { name: "중형 60×40×30cm" }).click();
  await page.getByRole("button", { name: "저장" }).click();
  const petCard = page.getByRole("article", { name: "콩이" });
  await expect(petCard).toBeVisible();

  // 3. "이 아이로 설계하기" → 종·크기·케이지가 채워진 설계 화면
  await petCard.getByRole("link", { name: "이 아이로 설계하기" }).click();
  await page.waitForURL(/\/design\?pet=[0-9a-f]{32}/);
  await expect(page.getByRole("heading", { name: "사육 환경을 알려 주세요" })).toBeVisible();
  // (이전에 연 화면이 숨김 상태로 남아 있어 같은 이름이 있을 수 있으므로 설계 영역 안에서 찾는다)
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  await expect(wizard.getByLabel("내 반려동물")).not.toHaveValue("");
  await expect(wizard.getByLabel("케이지 가로 (mm)")).toHaveValue("600");
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처와 터널을 한쪽에 몰아서 넣고 싶어요");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await page.waitForURL(/\/designs\/[0-9a-f]{32}/);
  await expect(page.getByRole("heading", { level: 1, name: "은신처와 터널을 한쪽에 몰아서 넣고 싶어요" })).toBeVisible();
  await expect(page.getByTestId("design-version")).toHaveText("v1");
  const designUrl = new URL(page.url()).pathname;

  // 4. 내 설계 내역에 반려동물 이름과 함께 보인다
  await page.goto("/designs");
  const card = page.getByRole("main").getByRole("link", { name: /은신처와 터널을 한쪽에 몰아서/ });
  await expect(card).toBeVisible();
  await expect(card.getByText("콩이")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/designs-history.png`, fullPage: true });

  // 5. 커뮤니티에 공유 (글에 설계 첨부)
  await page.goto(designUrl);
  await page.getByRole("link", { name: "커뮤니티에 공유" }).click();
  await page.waitForURL(/\/community\/new\?design=/);
  await expect(page.getByLabel("설계 첨부")).not.toHaveValue("");
  await page.getByLabel("제목", { exact: true }).fill(`콩이네 배치 공유 ${RUN}`);
  await page.getByLabel("내용", { exact: true }).fill("한쪽에 몰아 두니 가운데가 넓어졌어요.\n<b>굵게</b> 는 글자 그대로 보여야 해요.");
  await page.getByRole("button", { name: "등록" }).click();
  await page.waitForURL(/\/community\/[0-9a-f]{32}$/);
  const postUrl = new URL(page.url()).pathname;
  await expect(page.getByRole("heading", { level: 1, name: `콩이네 배치 공유 ${RUN}` })).toBeVisible();
  await expect(page.getByText("<b>굵게</b> 는 글자 그대로 보여야 해요.", { exact: false })).toBeVisible();
  await expect(page.locator("article b")).toHaveCount(0); // HTML 로 해석하지 않는다
  await expect(page.getByRole("link", { name: "3D로 보기" })).toBeVisible();
  await logout(page);

  // 6. 다른 회원: 커뮤니티 목록 → 글 → 댓글
  await signup(page, b.username, b.nickname, b.password, "/community");
  await page.getByRole("main").getByRole("link", { name: new RegExp(`콩이네 배치 공유 ${RUN}`) }).click();
  await page.waitForURL(postUrl);
  await expect(page.getByRole("button", { name: "수정" })).toHaveCount(0); // 남의 글
  await page.getByLabel("댓글", { exact: true }).fill("배치 좋네요! 저도 따라 해 볼게요.");
  await page.getByRole("button", { name: "댓글 등록" }).click();
  await expect(page.getByRole("heading", { name: "댓글 1" })).toBeVisible();
  await expect(page.getByText("배치 좋네요! 저도 따라 해 볼게요.")).toBeVisible();

  // 7. 공유된 설계는 읽기 전용으로 볼 수 있고 내려받을 수 있다
  await page.getByRole("link", { name: "3D로 보기" }).click();
  await page.waitForURL(/\/designs\/[0-9a-f]{32}/);
  await expect(page.getByText(`${a.nickname}님이 커뮤니티에 공유한 설계예요`, { exact: false })).toBeVisible();
  await expect(page.getByTestId("viewer").locator("canvas")).toBeVisible();
  await expect(page.getByLabel("수정할 내용")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "커뮤니티에 공유" })).toHaveCount(0);
  const stlHref = await page.getByRole("link", { name: /STL/ }).getAttribute("href");
  expect((await page.request.get(stlHref!)).status()).toBe(200);

  // 8. 내 설계 내역은 비어 있다 (남의 설계는 내 것이 아님)
  await page.goto("/designs");
  await expect(page.getByText("아직 만든 설계가 없어요")).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("로그인이 풀려도 쓰던 글은 그대로 남고, 다시 로그인하면 이어서 쓸 수 있다", async ({ page, context }) => {
  const u = { username: `draft_${RUN}`, nickname: `초안${RUN}`, password: "draft-pass-789" };
  await signup(page, u.username, u.nickname, u.password, "/community/new");
  const title = page.getByRole("main").getByRole("textbox", { name: "제목", exact: true });
  const body = page.getByRole("main").getByRole("textbox", { name: "내용", exact: true });
  await title.fill(`쓰던 제목 ${RUN}`);
  await body.fill("한참 쓰던 긴 내용");

  await context.clearCookies(); // 세션 만료·다른 기기에서 비밀번호 변경과 같은 상황
  await page.getByRole("button", { name: "등록" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "쓰던 내용은 그대로 두었어요" })).toBeVisible();
  await expect(title).toHaveValue(`쓰던 제목 ${RUN}`); // 폼이 로그인 안내로 바뀌지 않는다
  await expect(body).toHaveValue("한참 쓰던 긴 내용");

  await page.getByRole("link", { name: "다시 로그인하기" }).click();
  await page.waitForURL(/\/login/);
  await page.locator("#login-username").fill(u.username);
  await page.locator("#login-password").fill(u.password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/community/new");
  await expect(title).toHaveValue(`쓰던 제목 ${RUN}`);
  await expect(body).toHaveValue("한참 쓰던 긴 내용");
  await page.getByRole("button", { name: "등록" }).click();
  await page.waitForURL(/\/community\/[0-9a-f]{32}$/);
  await expect(page.getByRole("heading", { level: 1, name: `쓰던 제목 ${RUN}` })).toBeVisible();
});

test("설계 결과로 이동하는 중 다른 곳을 눌러도 설계 버튼이 멈춰 있지 않다", async ({ page }) => {
  await signup(page, `wiz_${RUN}`, `마법사${RUN}`, "wizard-pass-321", "/design");
  const wizard = page.getByRole("region", { name: "사육 환경을 알려 주세요" });
  await wizard.getByLabel("케이지 가로 (mm)").fill("600");
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처 하나");
  // 결과 화면(/designs/{id}) 데이터 요청을 늦춰 두고, 그 사이 상단 '설계하기'를 다시 누른다
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => (release = r));
  await page.route(/\/designs\/[0-9a-f]{32}(\?.*)?$/, async (route) => {
    if (route.request().headers()["rsc"] || route.request().headers()["next-router-state-tree"]) await gate;
    await route.continue();
  });
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await expect(page.getByRole("button", { name: /결과 화면을 여는 중|AI가 설계하고 있어요/ })).toBeVisible();
  await page.getByRole("banner").getByRole("link", { name: "설계하기" }).click();
  release();
  await page.waitForLoadState("networkidle");
  // 어느 화면에 있든 버튼이 '진행 중'으로 굳어 있지 않아야 한다
  await expect(page.getByRole("button", { name: /결과 화면을 여는 중|AI가 설계하고 있어요/ })).toHaveCount(0, { timeout: 10_000 });
});
