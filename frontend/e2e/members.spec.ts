import { expect, test } from "@playwright/test";

import { emailOf, logout, signup, stubTurnstile, verifyEmail } from "./support";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const RUN = Date.now().toString(36).slice(-5); // 실행마다 다른 아이디 (같은 DB 를 재사용해도 겹치지 않게)

// 회원가입 화면의 CAPTCHA(Turnstile) 스크립트는 가짜 위젯으로 바꾼다 (e2e/support.ts)
test.beforeEach(async ({ page }) => {
  await stubTurnstile(page);
});

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
  await signup(page, { username, nickname: `중복검사${RUN}`, password: "password-123" }, { verify: false });
  await logout(page);

  await page.goto("/signup");
  await page.getByLabel("아이디").fill(username);
  await page.getByLabel("닉네임").fill(`다른닉${RUN}`);
  await page.getByLabel("이메일").fill(emailOf(`dup2_${RUN}`));
  await page.getByLabel("비밀번호", { exact: true }).fill("password-123");
  await page.getByLabel("비밀번호 확인").fill("password-999");
  // 칸을 벗어나면 불일치 안내가 나타나 아래 요소가 밀리므로, 먼저 벗어난 뒤 보안 확인을 누른다
  await page.getByLabel("비밀번호 확인").blur();
  await expect(page.getByText("비밀번호가 서로 달라요. 다시 확인해 주세요.")).toBeVisible();
  // 보안 확인 전에는 가입 버튼이 막혀 있다
  await expect(page.getByRole("button", { name: "가입하기" })).toBeDisabled();
  await page.getByLabel("로봇이 아니에요").check();
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page.getByText("비밀번호가 서로 달라요. 다시 확인해 주세요.")).toBeVisible();
  await page.getByLabel("비밀번호 확인").fill("password-123");
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "이미 사용 중인 아이디예요." })).toBeVisible();
  await expect(page).toHaveURL(/\/signup/);
  // 토큰은 한 번만 쓸 수 있으므로 거절된 뒤에는 보안 확인을 다시 해야 한다
  await expect(page.getByLabel("로봇이 아니에요")).not.toBeChecked();
  await expect(page.getByRole("button", { name: "가입하기" })).toBeDisabled();
});

test("회원가입 → 반려동물 등록 → 반려동물로 설계 → 내 설계 → 커뮤니티 공유 → 다른 회원의 댓글·읽기 전용 보기", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const a = { username: `kong_${RUN}`, nickname: `콩이맘${RUN}`, password: "hamster-love-123" };
  const b = { username: `tunnel_${RUN}`, nickname: `터널아빠${RUN}`, password: "tunnel-dad-456" };

  // 1. 회원가입 (가입하면 바로 로그인) → 메일의 링크로 이메일 인증
  await signup(page, a);
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
  await signup(page, b, { next: "/community" });
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
  await signup(page, u, { next: "/community/new" });
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
  await signup(page, { username: `wiz_${RUN}`, nickname: `마법사${RUN}`, password: "wizard-pass-321" }, { next: "/design" });
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

test("이메일 인증 전: 안내 띠가 보이고 설계·글쓰기가 막혀 있다가, 메일의 링크로 인증하면 설계할 수 있다", async ({ page }) => {
  const m = { username: `unv_${RUN}`, nickname: `인증전${RUN}`, password: "verify-later-123" };
  const email = await signup(page, m, { verify: false });

  const banner = page.getByRole("region", { name: "이메일 인증 안내" });
  await expect(banner).toContainText("이메일 인증을 마치면 설계·글쓰기·댓글을 쓸 수 있어요.");
  await expect(banner).toContainText(email);

  // 설계하기: 안내가 보이고, 요구사항까지 써도 설계 버튼은 막혀 있다
  await page.goto("/design");
  await expect(page.getByText("이메일 인증을 마치면 맞춤 설계를 받을 수 있어요.", { exact: false })).toBeVisible();
  await page.getByText("골든 (시리안)").click();
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처를 왼쪽에 넣어 주세요");
  await expect(page.getByRole("button", { name: "맞춤 설계 받기" })).toBeDisabled();

  // 글쓰기도 막혀 있다
  await page.goto("/community/new");
  await expect(page.getByText("이메일 인증을 마치면 글을 올릴 수 있어요.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "등록", exact: true })).toBeDisabled();

  // 메일의 링크로 인증하면 안내 띠가 사라지고 바로 설계할 수 있다
  await verifyEmail(page, email);
  await expect(banner).toHaveCount(0);
  await page.goto("/design");
  await page.getByText("골든 (시리안)").click();
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처를 왼쪽에 넣어 주세요");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await page.waitForURL(/\/designs\/[0-9a-f]{32}/);
  await expect(page.getByTestId("design-version")).toHaveText("v1");
});

test("CAPTCHA 가 거절되면 오류를 보여 주고 보안 확인을 다시 하게 한다", async ({ page }) => {
  // 가짜 위젯은 아이디에 capfail 이 있으면 통과하지 못하는 토큰("e2e-fail")을 보낸다
  await page.goto("/signup");
  await page.getByLabel("아이디").fill(`capfail_${RUN}`);
  await page.getByLabel("닉네임").fill(`캡차실패${RUN}`);
  await page.getByLabel("이메일").fill(emailOf(`capfail_${RUN}`));
  await page.getByLabel("비밀번호", { exact: true }).fill("captcha-fail-123");
  await page.getByLabel("비밀번호 확인").fill("captcha-fail-123");
  await page.getByLabel("로봇이 아니에요").check();

  const response = page.waitForResponse((r) => r.url().endsWith("/auth/signup") && r.request().method() === "POST");
  await page.getByRole("button", { name: "가입하기" }).click();
  const r = await response;
  expect(r.status()).toBe(400);
  const { detail } = (await r.json()) as { detail: { code: string; message_ko: string } };
  expect(detail.code).toBe("captcha_failed");

  await expect(page.getByRole("alert").filter({ hasText: detail.message_ko })).toBeVisible();
  await expect(page.getByLabel("로봇이 아니에요")).not.toBeChecked(); // 위젯을 처음 상태로 되돌렸다
  await expect(page.getByRole("button", { name: "가입하기" })).toBeDisabled();
  await expect(page).toHaveURL(/\/signup/);
});

test("인증 메일 다시 보내기: 곧바로 또 누르면 잠시 뒤에 보내라는 안내가 보인다", async ({ page }) => {
  const m = { username: `resend_${RUN}`, nickname: `재발송${RUN}`, password: "resend-mail-123" };
  await signup(page, m, { verify: false });

  const banner = page.getByRole("region", { name: "이메일 인증 안내" });
  const resend = banner.getByRole("button", { name: "인증 메일 다시 보내기" });
  // 첫 번째: 가입 메일을 막 보냈으므로 바로 1분 제한에 걸릴 수도 있다 (어느 쪽이든 끝날 때까지 기다린다)
  await resend.click();
  await expect(resend).toBeEnabled();

  const second = page.waitForResponse(
    (r) => r.url().endsWith("/auth/verify-email/resend") && r.request().method() === "POST",
  );
  await resend.click();
  const r = await second;
  expect(r.status()).toBe(429);
  const { detail } = (await r.json()) as { detail: { code: string; message_ko: string } };
  expect(detail.code).toBe("email_cooldown");
  await expect(banner.getByRole("alert")).toHaveText(detail.message_ko);
});

test("인증 링크가 잘못되면 안내를 보여 준다", async ({ page }) => {
  await page.goto("/verify-email?token=not-a-real-token-123");
  await expect(page.getByRole("heading", { name: "인증 링크가 올바르지 않거나 만료되었어요", exact: true })).toBeVisible();
  await page.goto("/verify-email");
  await expect(page.getByRole("heading", { name: "인증 링크가 올바르지 않아요", exact: true })).toBeVisible();
});
