// 이메일 주소 형식 확인 (화면에서 미리 걸러 내는 용도. 최종 판단은 서버(EmailStr)가 한다)

const SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * 대략적인 형식에 더해, 서버가 거절하는 흔한 실수도 미리 거른다:
 * 점이 이어지거나(..), 맨 앞·맨 끝이나 @ 바로 앞뒤에 점이 있거나, 인코딩된 주소(=?)인 경우.
 */
export function isPlausibleEmail(raw: string): boolean {
  const v = raw.trim();
  return (
    v.length <= 254 &&
    SHAPE.test(v) &&
    !v.includes("..") &&
    !v.includes("=?") &&
    !/^\.|\.$|\.@|@\./.test(v)
  );
}
