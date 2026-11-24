import { expect, test } from "@playwright/test";

import { signup, stubTurnstile } from "./support";

const RUN = Date.now().toString(36).slice(-5);
const API = "http://localhost:8000";
const PROMPT = "은신처 오른쪽에 밥그릇 받침, 왼쪽에 물병 거치대, 앞에는 터널로 은신처 하나 더 이어줘";

/** zip 의 중앙 디렉터리에서 파일 이름 목록을 읽는다 (압축을 풀지 않는다). */
function zipEntryNames(buf: Buffer): string[] {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65_557); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error("not a zip file");
  const count = buf.readUInt16LE(eocd + 10);
  let pos = buf.readUInt32LE(eocd + 16);
  const names: string[] = [];
  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(pos) !== 0x02014b50) throw new Error("bad central directory");
    const nameLen = buf.readUInt16LE(pos + 28);
    const extraLen = buf.readUInt16LE(pos + 30);
    const commentLen = buf.readUInt16LE(pos + 32);
    names.push(buf.subarray(pos + 46, pos + 46 + nameLen).toString("utf8"));
    pos += 46 + nameLen + extraLen + commentLen;
  }
  return names;
}

test.beforeEach(async ({ page }) => {
  await stubTurnstile(page);
});

test("조립 구조물: 부품·연결·파트 파일이 보이고 STL zip 의 파일 이름이 겹치지 않는다", async ({ page }) => {
  await signup(page, { username: `asm_${RUN}`, nickname: `조립${RUN}`, password: "assembly-pass-321" }, { next: "/" });
  const h = await page.request.post(`${API}/habitats`, {
    data: { species: "hamster", size: "dwarf", count: 1, cage: { width_mm: 1000, depth_mm: 600, height_mm: 400 } },
  });
  const d = await page.request.post(`${API}/designs`, { data: { habitat_id: (await h.json()).id, prompt: PROMPT } });
  expect(d.status()).toBe(201);
  const design = (await d.json()) as { id: string };

  await page.goto(`/designs/${design.id}`);
  await page.getByRole("button", { name: /#1/ }).first().click();
  const parts = page.getByTestId("assembly-parts");
  await expect(parts).toBeVisible();
  for (const id of ["hide", "bowl", "bottle", "tube", "hide2"]) {
    await expect(page.getByTestId(`assembly-part-${id}`)).toBeVisible();
  }
  await expect(page.getByTestId("assembly-joins").locator("li")).toHaveCount(4);
  await expect(page.getByTestId("assembly-joins")).toContainText("슬라이드");

  const files = page.getByTestId("part-files").locator("li");
  await expect(files.first()).toBeVisible();
  const listed = await files.allTextContents();
  expect(listed.length).toBeGreaterThan(1);
  const link = page.getByRole("link", { name: "STL (zip) 받기" });
  await expect(link).toBeVisible();

  const href = await link.getAttribute("href");
  expect(href).toBeTruthy();
  const res = await page.request.get(href!); // API 서버 주소 (API_BASE) 그대로
  expect(res.status()).toBe(200);
  const names = zipEntryNames(await res.body());
  expect(names.length).toBe(listed.length);
  expect(new Set(names).size).toBe(names.length);
});

test("라이브러리 부품이 든 설계: 화면의 파트 파일 이름이 STL zip 의 이름과 같다 (@ 는 -)", async ({ page }) => {
  await signup(page, { username: `lib_${RUN}`, nickname: `라이브${RUN}`, password: "assembly-pass-321" }, { next: "/" });
  const h = await page.request.post(`${API}/habitats`, {
    data: { species: "hamster", size: "dwarf", count: 1, cage: { width_mm: 1000, depth_mm: 600, height_mm: 400 } },
  });
  const d = await page.request.post(`${API}/designs`, {
    data: { habitat_id: (await h.json()).id, prompt: "2층 집이랑 터널 갈림길 따로" },
  });
  expect(d.status()).toBe(201);
  const design = (await d.json()) as { id: string };
  await page.goto(`/designs/${design.id}`);
  const files = page.getByTestId("part-files").locator("li span.font-mono");
  await expect(files.first()).toBeVisible();
  const listed = await files.allTextContents();
  expect(listed).toContain("part2_tunnel_junction-v1.stl");
  const href = await page.getByRole("link", { name: "STL (zip) 받기" }).getAttribute("href");
  const res = await page.request.get(href!);
  expect(res.status()).toBe(200);
  expect(zipEntryNames(await res.body()).sort()).toEqual([...listed].sort());
});
