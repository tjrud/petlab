/**
 * 받침에 맞춰 조사를 붙여요: josa("은신처", "와과") → "은신처와", josa("밥그릇", "이가") → "밥그릇이".
 * 한글로 끝나지 않거나 빈 문자열이면 "을(를)"처럼 둘 다 적어요.
 */
export function josa(word: string, pair: "이가" | "와과" | "을를" | "은는"): string {
  const code = word.charCodeAt(word.length - 1);
  if (!(code >= 0xac00 && code <= 0xd7a3)) return `${word}${pair[0]}(${pair[1]})`;
  const batchim = (code - 0xac00) % 28 !== 0;
  const [withB, withoutB] = pair === "이가" ? ["이", "가"] : pair === "와과" ? ["과", "와"] : pair === "을를" ? ["을", "를"] : ["은", "는"];
  return word + (batchim ? withB : withoutB);
}
