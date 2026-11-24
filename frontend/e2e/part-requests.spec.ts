import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

import { logout, signup, stubTurnstile, submitLogin } from "./support";

// 부품 요청: 카탈로그에 없는 부품(쳇바퀴)을 적으면 설계 화면에 안내가 보이고, 관리자 화면에 수요로 쌓인다.
// 모의 해석기는 "쳇바퀴"를 missing_parts 로 돌려준다 (backend app/llm/mock.py MISSING_KEYWORDS).

const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const API = "http://localhost:8000";
const ADMIN = { username: "admin", password: "e2e-admin-password" };
const RUN = Date.now().toString(36).slice(-5); // 실행마다 다른 아이디 (같은 DB 를 재사용해도 겹치지 않게)
const WHEEL = "쳇바퀴";

type Row = { id: string; name_key: string; status: string; user_count: number; request_count: number };

/** 관리자 API 로 쳇바퀴 요청 줄을 읽는다 (없으면 null). 같은 DB 를 다시 쓰는 실행에서도 늘어난 만큼만 확인하려고 */
async function wheelRow(api: APIRequestContext): Promise<Row | null> {
  const r = await api.get(`${API}/admin/part-requests?status=all&q=${encodeURIComponent(WHEEL)}`);
  expect(r.status()).toBe(200);
  const { items } = (await r.json()) as { items: Row[] };
  return items.find((x) => x.name_key === WHEEL) ?? null;
}

async function adminLogin(page: Page, next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await submitLogin(page, ADMIN.username, ADMIN.password);
  await page.waitForURL((u) => u.pathname === next.split("?")[0]);
}

test.beforeEach(async ({ page }) => {
  await stubTurnstile(page);
});

test("부품 요청: 없는 부품을 적으면 안내가 보이고, 관리자 화면에서 수요를 보고 상태를 바꾼다", async ({ page, request }) => {
  // 같은 DB 를 다시 쓰는 경우를 위해: 지금 값을 읽고, 앞선 실행이 상태를 바꿔 두었으면 새 요청으로 돌려 둔다
  const login = await request.post(`${API}/auth/login`, { data: ADMIN });
  expect(login.status()).toBe(200);
  let before = await wheelRow(request);
  if (before && before.status !== "open") {
    const r = await request.patch(`${API}/admin/part-requests/${before.id}`, { data: { status: "open" } });
    expect(r.status()).toBe(200);
    before = await wheelRow(request);
  }

  // 1. 회원: 은신처랑 쳇바퀴 → 설계는 은신처로 만들고, 쳇바퀴는 아직 없다고 알린다
  const member = { username: `wheel_${RUN}`, nickname: `쳇바퀴${RUN}`, password: "password-123" };
  await signup(page, member, { next: "/design" });
  await expect(page.getByRole("heading", { name: "사육 환경을 알려 주세요" })).toBeVisible();
  await page.getByText("골든 (시리안)").click();
  await page.getByRole("button", { name: "다음" }).click();
  await page.getByLabel("요구사항").fill("은신처랑 쳇바퀴 만들어 주세요");
  await page.getByRole("button", { name: "맞춤 설계 받기" }).click();
  await page.waitForURL(/\/designs\/[0-9a-f]{32}/);
  await expect(page.getByRole("button", { name: /은신처 #1/ })).toBeVisible();
  const notice = page.getByTestId("missing-parts");
  await expect(notice).toHaveText(
    "요청하신 쳇바퀴는 아직 부품 라이브러리에 없어요. 요청을 기록해 두었고, 이번 설계는 있는 부품으로 만들었어요.",
  );
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/part-request-notice.png`, fullPage: true });

  // 2. 회원에게는 관리자 메뉴가 없고, 화면과 API 모두 막힌다
  await expect(page.getByRole("banner").getByRole("link", { name: "부품 요청" })).toHaveCount(0);
  await page.goto("/admin/part-requests");
  await expect(page.getByRole("alert").filter({ hasText: "관리자만 쓸 수 있어요." })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  const forbidden = await page.request.get(`${API}/admin/part-requests`);
  expect(forbidden.status()).toBe(403);
  await page.goto("/");
  await logout(page);

  // 로그인하지 않으면 로그인 안내 (API 는 401)
  await page.goto("/admin/part-requests");
  await expect(page.getByText("관리자로 로그인해 주세요")).toBeVisible();
  expect((await page.request.get(`${API}/admin/part-requests`)).status()).toBe(401);

  // 3. 관리자: 헤더의 링크로 부품 요청 화면 → 쳇바퀴가 회원 1명·설계 1개 늘어 있다
  await adminLogin(page, "/");
  await page.getByRole("banner").getByRole("link", { name: "부품 요청" }).click();
  await page.waitForURL((u) => u.pathname === "/admin/part-requests");
  await expect(page.getByRole("heading", { level: 1, name: "부품 요청" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "요청 상태" }).getByRole("link", { name: "새 요청" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  const row = page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(`^${WHEEL}`) }) });
  await expect(row).toHaveCount(1);
  const users = (before?.user_count ?? 0) + 1;
  const count = (before?.request_count ?? 0) + 1;
  await expect(row.getByRole("cell", { name: `${users} / ${count}`, exact: true })).toBeVisible();
  await expect(row).toContainText("달리기 운동"); // 쓰임새
  await expect(row).toContainText("은신처랑 쳇바퀴 만들어 주세요"); // 최근 예시 (요청 앞부분)
  await expect(row).toContainText("새 요청");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/part-requests-admin.png`, fullPage: true });

  // 검색: 이름으로 찾으면 주소에 남는다
  await page.getByLabel("이름으로 찾기").fill(WHEEL);
  await page.getByRole("button", { name: "찾기" }).click();
  await expect(page).toHaveURL(/\?q=%EC%B3%87%EB%B0%94%ED%80%B4$/);
  await expect(row).toHaveCount(1);

  // 4. 관리: 최근 설계(자세히)를 보고 상태를 '만들 예정'으로 바꾼다
  await page.getByRole("button", { name: `${WHEEL} 자세히·관리` }).click();
  const panel = page.getByRole("region", { name: "최근 설계" });
  await expect(panel).toContainText("은신처랑 쳇바퀴 만들어 주세요");
  await page.getByLabel("상태", { exact: true }).selectOption({ label: "만들 예정" });
  await page.getByLabel("관리 메모").fill("e2e: 다음 부품 후보");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "저장했어요." })).toBeVisible();
  await expect(row).toContainText("만들 예정");
  await expect(row).toContainText("e2e: 다음 부품 후보");

  // '만들 예정' 탭에 보이고 '새 요청' 탭에서는 빠진다
  await page.getByRole("navigation", { name: "요청 상태" }).getByRole("link", { name: "만들 예정" }).click();
  await expect(page).toHaveURL(/status=planned/);
  await expect(row).toHaveCount(1);
  await page.getByRole("navigation", { name: "요청 상태" }).getByRole("link", { name: "새 요청" }).click();
  await expect(page.getByText("찾는 이름의 부품 요청이 없어요.")).toBeVisible();

  // 상태는 서버에 저장됐다
  const after = await wheelRow(request);
  expect(after?.status).toBe("planned");
});
