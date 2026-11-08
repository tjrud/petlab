// 3D 파일 주소 도우미 (three.js 를 불러오지 않는 가벼운 모듈: 첫 화면 번들에 three 가 섞이지 않게)

/** Blob 공개 주소는 쿠키 없이, API 경로(로컬 저장소)는 로그인 쿠키와 함께 받는다 */
export const needsCredentials = (url: string) => !url.includes(".blob.vercel-storage.com");

/** 이보다 큰 3D 파일은 누르기 전에는 받지 않는다 (상세 화면을 열 때마다 수십 MB 를 받지 않게) */
export const AUTO_3D_BYTES = 10 * 1024 * 1024;

/** 3D 로 볼 수 있는 형식 */
export type MeshFormat = "stl" | "3mf";
export const isMeshFormat = (f: string): f is MeshFormat => f === "stl" || f === "3mf";

/** 이 브라우저가 gzip 을 풀 수 있는지 (가벼운 미리보기 메시 NFM1 을 쓸 수 있는지. Safari 16.4+, Firefox 113+, Chrome 80+) */
export const canDecodeNfm = () => typeof DecompressionStream !== "undefined";
