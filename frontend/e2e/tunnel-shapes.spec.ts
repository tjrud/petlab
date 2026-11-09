import { expect, test } from "@playwright/test";

import { signup, stubTurnstile } from "./support";

const RUN = Date.now().toString(36).slice(-5);
const API = "http://localhost:8000";

test.beforeEach(async ({ page }) => {
  await stubTurnstile(page);
});

test("터널 모양: 둥근 원통형은 세워서 출력해 통과, S자로 휜 네모 터널은 서포트 경고, 설계 화면에 모양이 보인다", async ({ page }) => {
  await signup(page, { username: `tun_${RUN}`, nickname: `터널${RUN}`, password: "tunnel-pass-321" }, { next: "/" });
  const make = async (prompt: string) => {
    const h = await page.request.post(`${API}/habitats`, {
      data: { species: "hamster", size: "syrian", count: 1, cage: { width_mm: 1000, depth_mm: 500, height_mm: 500 } },
    });
    const d = await page.request.post(`${API}/designs`, { data: { habitat_id: (await h.json()).id, prompt } });
    expect(d.status()).toBe(201);
    return (await d.json()) as { id: string };
  };

  const tube = await make("둥근 원통형 터널을 만들어 주세요");
  await page.goto(`/designs/${tube.id}`);
  await page.getByRole("button", { name: /터널 #1/ }).first().click();
  await expect(page.getByText("단면 모양").first()).toBeVisible();
  await expect(page.getByText("둥근 관").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "STL 받기" })).toBeVisible();
  await expect(page.getByText(/서포트가 필요해요/)).toHaveCount(0);

  const sbox = await make("S자로 휜 네모난 터널");
  await page.goto(`/designs/${sbox.id}`);
  await page.getByRole("button", { name: /터널 #1/ }).first().click();
  await expect(page.getByText("S자").first()).toBeVisible();
  await expect(page.getByText("네모").first()).toBeVisible();
  await expect(page.getByText(/휜 터널을 이 단면으로 만들면 지붕 안쪽에 서포트가 필요해요/)).toBeVisible();
  // 경고라 내려받기는 막지 않는다
  await expect(page.getByRole("link", { name: "STL 받기" })).toBeVisible();

  // 영어 화면에서도 모양 이름과 경고가 영어로
  await page.goto(`/en/designs/${sbox.id}`);
  await page.getByRole("button", { name: /Tunnel #1/ }).first().click();
  await expect(page.getByText("S-curve").first()).toBeVisible();
  await expect(page.getByText(/needs supports under the roof/)).toBeVisible();
});
