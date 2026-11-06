// 둥지마당 파일 올리기: 배포 플랫폼의 요청 크기 한도(약 4.5MB) 때문에 서버가 정한 크기(3MB)로 나눠 보낸다.
// 조각 하나가 네트워크 문제로 실패하면 몇 번 다시 보낸다. 다 보내면 서버가 내용을 확인하고 저장한다.

import { api, ApiError } from "@/lib/api";
import type { MarketFile } from "@/lib/types";

const RETRIES = 3;

export async function uploadMarketFile(
  file: File,
  kind: "model" | "image",
  onProgress: (sent: number, total: number) => void,
  signal?: AbortSignal,
): Promise<MarketFile> {
  const start = await api.startUpload(file.name, file.size, kind);
  const size = start.chunk_bytes;
  onProgress(0, file.size);
  for (let n = 0; n < start.chunks; n++) {
    const chunk = file.slice(n * size, Math.min(file.size, (n + 1) * size));
    for (let attempt = 0; ; attempt++) {
      try {
        await api.putChunk(start.id, n, chunk, signal);
        break;
      } catch (e) {
        const retryable = e instanceof ApiError && (e.status === 0 || e.status >= 500);
        if (!retryable || attempt >= RETRIES || signal?.aborted) throw e;
        await new Promise((r) => setTimeout(r, 800 * (attempt + 1)));
      }
    }
    onProgress(Math.min(file.size, (n + 1) * size), file.size);
  }
  return api.completeUpload(start.id);
}
