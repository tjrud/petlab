// 영어 사전 확인: 코드에서 t("한국어") 로 부르는 문구가 src/i18n/en/*.ts 에 모두 있는지.
// (변수로 넘기는 t(value) 는 확인하지 못한다)  npm run check:i18n
import fs from "node:fs";
import path from "node:path";

const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
const unquote = (s) => JSON.parse(s[0] === "'" ? `"${s.slice(1, -1).replace(/"/g, '\\"')}"` : s);
const HANGUL = /[가-힣]/;

const en = new Set();
for (const f of walk("src/i18n/en")) {
  const re = /^\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\s*:/gm;
  for (const m of fs.readFileSync(f, "utf8").matchAll(re)) en.add(unquote(m[1]));
}
let missing = 0;
for (const f of walk("src")) {
  if (!/\.tsx?$/.test(f) || f.includes(`i18n${path.sep}en`)) continue;
  const re = /\bt\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g;
  for (const m of fs.readFileSync(f, "utf8").matchAll(re)) {
    const k = unquote(m[1]);
    if (HANGUL.test(k) && !en.has(k)) {
      console.log(`${f}: ${k}`);
      missing++;
    }
  }
}
console.log(`영어 번역이 없는 문구: ${missing}개 (사전 ${en.size}개)`);
process.exit(missing ? 1 : 0);
