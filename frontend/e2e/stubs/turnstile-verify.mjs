// E2E 용 가짜 Turnstile 확인 서버 (Cloudflare siteverify 대신).
// POST /siteverify (form-encoded: secret, response, remoteip?) → response 가 "e2e-pass" 일 때만 성공.
// GET /health → 200 (Playwright webServer 준비 확인용)
import http from "node:http";

const PORT = Number(process.env.PORT ?? 8099);
const SECRET = process.env.TURNSTILE_SECRET_KEY ?? "e2e-secret-key";

function send(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  if (req.method === "GET" && url.pathname === "/health") return send(res, 200, { ok: true });
  if (req.method !== "POST" || url.pathname !== "/siteverify") return send(res, 404, { error: "not found" });

  let raw = "";
  req.setEncoding("utf8");
  req.on("data", (chunk) => {
    raw += chunk;
    if (raw.length > 64 * 1024) req.destroy(); // 테스트용이지만 너무 큰 본문은 받지 않는다
  });
  req.on("end", () => {
    // Cloudflare 는 form-encoded 와 JSON 을 모두 받는다. 둘 다 읽는다
    let params;
    if ((req.headers["content-type"] ?? "").includes("application/json")) {
      try {
        params = new URLSearchParams(Object.entries(JSON.parse(raw || "{}")).map(([k, v]) => [k, String(v)]));
      } catch {
        params = new URLSearchParams();
      }
    } else {
      params = new URLSearchParams(raw);
    }
    if (params.get("secret") !== SECRET) {
      return send(res, 200, { success: false, "error-codes": ["invalid-input-secret"] });
    }
    if (params.get("response") === "e2e-pass") {
      return send(res, 200, { success: true, challenge_ts: new Date().toISOString(), hostname: "localhost" });
    }
    return send(res, 200, { success: false, "error-codes": ["invalid-input-response"] });
  });
});

server.listen(PORT, () => {
  console.log(`turnstile verify stub listening on http://localhost:${PORT}`);
});
