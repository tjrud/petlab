// E2E 공용 도우미: 가짜 Turnstile 위젯, 메일함(outbox) 읽기, 회원가입·이메일 인증.
import fs from "node:fs/promises";
import path from "node:path";

import { expect, type Page } from "@playwright/test";

/** 백엔드가 메일을 한 통에 JSON 파일 하나로 저장하는 곳 (playwright.config.ts 의 EMAIL_OUTBOX_DIR 와 같다) */
const OUTBOX = path.join(process.env.E2E_TMP ?? "", "outbox");

/**
 * challenges.cloudflare.com 의 Turnstile 스크립트 대신 쓰는 가짜 위젯.
 * render() 는 "로봇이 아니에요" 체크박스를 넣고, 체크하면 callback("e2e-pass") 를 부른다.
 * 아이디에 "capfail" 이 들어 있으면 "e2e-fail" 을 보내 서버가 거절하게 한다 (가짜 확인 서버는 e2e-pass 만 통과).
 */
const TURNSTILE_STUB = `
(() => {
  let n = 0;
  const widgets = new Map();
  window.turnstile = {
    render(el, opts) {
      const id = "e2e-widget-" + ++n;
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      label.append(box, document.createTextNode(" 로봇이 아니에요"));
      box.addEventListener("change", () => {
        if (!box.checked) return;
        const username = document.querySelector('input[name="username"]');
        opts.callback(username && username.value.includes("capfail") ? "e2e-fail" : "e2e-pass");
      });
      el.appendChild(label);
      widgets.set(id, { label, box, opts });
      return id;
    },
    reset(id) {
      const w = widgets.get(id);
      if (w) w.box.checked = false;
    },
    remove(id) {
      const w = widgets.get(id);
      if (w) {
        w.label.remove();
        widgets.delete(id);
      }
    },
  };
})();
`;

/** 이 페이지에서 Turnstile 스크립트 요청을 가짜 위젯으로 바꾼다 (페이지를 열기 전에 부른다) */
export async function stubTurnstile(page: Page) {
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js*", (route) =>
    route.fulfill({ status: 200, contentType: "text/javascript; charset=utf-8", body: TURNSTILE_STUB }),
  );
}

type Mail = { to: string; subject: string; text: string; html: string };

/** 그 주소로 온 가장 최근 메일. 파일 이름이 "<시각(ns)>-<id>.json" 이라 이름순이 보낸 순서다. 몇 초 동안 기다린다 */
export async function latestMailTo(to: string, timeoutMs = 10_000): Promise<Mail> {
  const deadline = Date.now() + timeoutMs;
  const want = to.toLowerCase();
  for (;;) {
    let names: string[] = [];
    try {
      // 쓰는 중인 임시 파일(".<이름>.tmp")은 건너뛴다
      names = (await fs.readdir(OUTBOX)).filter((n) => n.endsWith(".json") && !n.startsWith("."));
    } catch {
      /* 아직 메일이 한 통도 없다 */
    }
    for (const name of names.sort().reverse()) {
      const mail = JSON.parse(await fs.readFile(path.join(OUTBOX, name), "utf-8")) as Mail;
      if (mail.to.toLowerCase().includes(want)) return mail;
    }
    if (Date.now() > deadline) throw new Error(`메일이 오지 않았어요: ${to} (${OUTBOX})`);
    await new Promise((r) => setTimeout(r, 250));
  }
}

/** 그 주소로 온 가장 최근 인증 메일의 링크 (/verify-email?token=...) 를 경로로 돌려준다 */
export async function verifyLinkFor(email: string): Promise<string> {
  const mail = await latestMailTo(email);
  const match = mail.text.match(/https?:\/\/[^\s"'<>]+\/verify-email\?token=[^\s"'<>]+/);
  if (!match) throw new Error(`인증 링크가 없는 메일이에요: ${mail.subject}`);
  const url = new URL(match[0]);
  return url.pathname + url.search;
}

/** 메일의 인증 링크를 열어 이메일 인증을 마친다 (성공하면 주소에서 토큰이 빠진다) */
export async function verifyEmail(page: Page, email: string) {
  await page.goto(await verifyLinkFor(email));
  await expect(page.getByRole("heading", { name: "이메일 인증을 마쳤어요" })).toBeVisible();
  await expect(page).toHaveURL(/\/verify-email\?done=1$/);
}

export type NewMember = { username: string; nickname: string; password: string };

export const emailOf = (username: string) => `${username}@example.com`;

/**
 * 회원가입 (이메일 입력 → 가짜 CAPTCHA → 가입 → "인증 메일을 보냈어요" → 계속하기).
 * verify 가 true(기본)이면 메일의 링크로 인증까지 마치고 next 화면으로 돌아온다. 가입한 이메일을 돌려준다.
 */
export async function signup(page: Page, m: NewMember, { next = "/", verify = true } = {}): Promise<string> {
  const email = emailOf(m.username);
  await stubTurnstile(page);
  await page.goto(`/signup?next=${encodeURIComponent(next)}`);
  await page.getByLabel("아이디").fill(m.username);
  await page.getByLabel("닉네임").fill(m.nickname);
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호", { exact: true }).fill(m.password);
  await page.getByLabel("비밀번호 확인").fill(m.password);
  await page.getByLabel("로봇이 아니에요").check();
  await page.getByRole("button", { name: "가입하기" }).click();
  await expect(page.getByRole("heading", { name: "인증 메일을 보냈어요" })).toBeVisible();
  await expect(page.getByRole("main").getByText(email)).toBeVisible();
  await page.getByRole("button", { name: "계속하기" }).click();
  await page.waitForURL((url) => url.pathname === next);
  await expect(page.getByRole("banner").getByText(m.nickname)).toBeVisible();
  if (verify) {
    await verifyEmail(page, email);
    await page.goto(next);
  }
  return email;
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.waitForURL((url) => url.pathname === "/");
  await expect(page.getByRole("banner").getByRole("link", { name: "로그인" })).toBeVisible();
}
