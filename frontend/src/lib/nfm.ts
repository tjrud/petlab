// 3D 미리보기용 가벼운 메시(NFM1) 읽기. 서버가 STL·3MF 를 올릴 때 만들어 둔다 (backend/app/mesh_preview.py).
// 형식 (리틀 엔디언, 파일 전체가 gzip):
//   0 "NFM1" · 4 u32 flags(bit0: 인덱스 u16) · 8 u32 꼭짓점 수 · 12 u32 삼각형 수
//   16 f32[3] 원점(mm) · 28 f32[3] 한 칸 크기(mm) · 40 u16 좌표[꼭짓점*3] · 4바이트 경계 · u16|u32 인덱스[삼각형*3]

import * as THREE from "three";

export { canDecodeNfm } from "@/lib/meshUrl";

const MAGIC = 0x314d464e; // "NFM1"

export async function decodeNfm(gz: ArrayBuffer): Promise<THREE.BufferGeometry> {
  const stream = new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"));
  const buf = await new Response(stream).arrayBuffer();
  const dv = new DataView(buf);
  if (buf.byteLength < 40 || dv.getUint32(0, true) !== MAGIC) throw new Error("NFM1 형식이 아니에요");
  const flags = dv.getUint32(4, true);
  const nv = dv.getUint32(8, true);
  const nt = dv.getUint32(12, true);
  const o = [16, 20, 24].map((k) => dv.getFloat32(k, true));
  const s = [28, 32, 36].map((k) => dv.getFloat32(k, true));
  const indexAt = 40 + nv * 6 + ((4 - ((40 + nv * 6) % 4)) % 4);
  const wide = (flags & 1) === 0;
  if (buf.byteLength < indexAt + nt * 3 * (wide ? 4 : 2)) throw new Error("NFM1 파일이 잘렸어요");
  const q = new Uint16Array(buf, 40, nv * 3);
  const pos = new Float32Array(nv * 3);
  for (let i = 0; i < nv * 3; i += 3) {
    pos[i] = o[0] + q[i] * s[0];
    pos[i + 1] = o[1] + q[i + 1] * s[1];
    pos[i + 2] = o[2] + q[i + 2] * s[2];
  }
  const idx = wide ? new Uint32Array(buf, indexAt, nt * 3) : new Uint16Array(buf, indexAt, nt * 3);
  for (let i = 0; i < idx.length; i++) if (idx[i] >= nv) throw new Error("NFM1 인덱스가 잘못됐어요");
  const indexed = new THREE.BufferGeometry();
  indexed.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  indexed.setIndex(new THREE.BufferAttribute(idx, 1));
  // STL 과 같은 각진 면으로 보이게 (면마다 법선)
  const flat = indexed.toNonIndexed();
  flat.computeVertexNormals();
  indexed.dispose();
  return flat;
}

/** useLoader 로 쓰는 NFM1 로더 (받기는 three 의 FileLoader, 풀기는 decodeNfm) */
export class NfmLoader extends THREE.Loader<THREE.BufferGeometry> {
  load(
    url: string,
    onLoad: (g: THREE.BufferGeometry) => void,
    onProgress?: (e: ProgressEvent) => void,
    onError?: (e: unknown) => void,
  ) {
    const loader = new THREE.FileLoader(this.manager);
    loader.setResponseType("arraybuffer");
    loader.setWithCredentials(this.withCredentials);
    loader.load(
      url,
      (data) => decodeNfm(data as ArrayBuffer).then(onLoad, (e) => onError?.(e)),
      onProgress,
      onError,
    );
  }
}
