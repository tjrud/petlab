import Link from "next/link";

import { api } from "@/lib/api";

export default function DownloadPanel({
  designId,
  version,
  allowed,
  partCount,
}: {
  designId: string;
  version: number;
  allowed: boolean;
  partCount: number;
}) {
  const btn = "flex-1 rounded-xl px-4 py-3 text-center font-semibold";
  return (
    <section aria-labelledby="download-title" className="space-y-3">
      <h2 id="download-title" className="font-bold">
        받기
      </h2>
      {allowed ? (
        <div className="flex gap-2">
          <a href={api.exportUrl(designId, "stl", version)} className={`${btn} bg-amber-500 text-white hover:bg-amber-600`} download>
            STL{partCount > 1 ? " (zip)" : ""} 내려받기
          </a>
          <a href={api.exportUrl(designId, "3mf", version)} className={`${btn} border border-amber-500 text-amber-700 hover:bg-amber-50`} download>
            3MF 내려받기
          </a>
        </div>
      ) : (
        <p className="rounded-xl bg-stone-100 p-3 text-sm text-stone-600">
          검증 문제를 해결해야 파일을 내려받을 수 있어요. 아래에 추가 요청을 적어 설계를 수정해 보세요.
        </p>
      )}
      <Link
        href={`/order?design=${designId}&version=${version}`}
        className="block rounded-xl border border-stone-300 px-4 py-3 text-center font-medium hover:bg-stone-50"
      >
        제작·배송 신청하기
      </Link>
      <p className="text-xs text-stone-500">파일은 mm 단위이며, 서포트 없이 출력할 수 있는 자세로 놓여 있어요.</p>
    </section>
  );
}
