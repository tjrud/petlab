"use client";

import { useState, type MouseEvent } from "react";

import AquariumPrintNotice from "@/components/AquariumPrintNotice";
import { Link, useLang, useT } from "@/i18n/client";
import { api, errorFrom } from "@/lib/api";
import type { HabitatKind, Item } from "@/lib/types";

const NETWORK_ERROR = "파일을 받지 못했어요. 잠시 후 다시 시도해 주세요.";

/** Content-Disposition 의 filename*=UTF-8''... (또는 filename="...") 에서 파일 이름을 꺼낸다 */
function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* 잘못된 인코딩이면 아래 형식으로 */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

/** 내려받을 STL 파일 이름 (서버 export 와 같은 규칙: 구조물 하나·파트 하나면 part1_<템플릿>.stl, 파트가 여럿이면 파트 이름을 붙인다) */
export function partFiles(items: Item[]): { name: string; label: string }[] {
  const out: { name: string; label: string }[] = [];
  for (const it of items) {
    const parts = it.parts?.length ? it.parts : [{ key: "body", name_ko: "본체", size_mm: it.print_size_mm }];
    const base = `part${it.index + 1}_${it.template}`;
    for (const part of parts) {
      out.push({ name: parts.length > 1 ? `${base}_${part.key}.stl` : `${base}.stl`, label: part.name_ko });
    }
  }
  return out;
}

export default function DownloadPanel({
  designId,
  version,
  allowed,
  items,
  kind = "cage",
  printNotes = null,
}: {
  designId: string;
  version: number;
  allowed: boolean;
  items: Item[];
  /** 사육 환경 종류. 어항이면 출력·설치 안전 안내를 함께 보여 준다 */
  kind?: HabitatKind;
  /** 어항 출력 안내 (종 규칙의 print_notes_ko). null 이면 아직 불러오는 중이라 안내를 띄우지 않는다 */
  printNotes?: readonly string[] | null;
}) {
  const t = useT();
  const lang = useLang();
  const files = partFiles(items);
  const partCount = files.length;
  const multiPartItems = items.filter((it) => (it.parts?.length ?? 1) > 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 링크(href)는 그대로 두고, 누르면 먼저 받아 본 뒤 저장한다.
  // 서버가 내려받기를 막으면(예: 서비스 업데이트 뒤 다시 검증한 형상이 기준을 통과하지 못함) 오류 JSON 이 파일로
  // 저장되는 대신 그 이유를 화면에 보여 준다.
  const download = async (e: MouseEvent<HTMLAnchorElement>, url: string, fallbackName: string) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      // 오류 문구를 지금 화면 언어로 받는다 (api.ts 의 요청과 같은 X-Lang 헤더)
      const res = await fetch(url, { credentials: "include", headers: { "X-Lang": lang } });
      if (!res.ok) {
        setError((await errorFrom(res)).messageKo);
        return;
      }
      const blob = await res.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = filenameFrom(res.headers.get("content-disposition")) ?? fallbackName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(href), 30_000);
    } catch {
      // 요청 자체가 실패했거나(네트워크) 응답을 읽지 못한 경우
      setError(t(NETWORK_ERROR));
    } finally {
      setBusy(false);
    }
  };

  const btn = "flex-1 whitespace-nowrap rounded-xl px-3 py-3 text-center text-sm font-semibold sm:text-base";
  const stlUrl = api.exportUrl(designId, "stl", version);
  const threeMfUrl = api.exportUrl(designId, "3mf", version);
  const base = `nestforge_${designId.slice(0, 8)}_v${version}`;
  return (
    <section aria-labelledby="download-title" className="space-y-3">
      <h2 id="download-title" className="font-bold">
        {t("받기")}
      </h2>
      {allowed ? (
        <>
          <div className="flex gap-2" aria-busy={busy}>
            <a
              href={stlUrl}
              onClick={(e) => download(e, stlUrl, `${base}.${partCount > 1 ? "zip" : "stl"}`)}
              className={`${btn} bg-amber-500 text-white hover:bg-amber-600 ${busy ? "opacity-60" : ""}`}
              download
            >
              {partCount > 1 ? t("STL (zip) 받기") : t("STL 받기")}
            </a>
            <a
              href={threeMfUrl}
              onClick={(e) => download(e, threeMfUrl, `${base}.3mf`)}
              className={`${btn} border border-amber-500 text-amber-700 hover:bg-amber-50 ${busy ? "opacity-60" : ""}`}
              download
            >
              {t("3MF 받기")}
            </a>
          </div>
          {multiPartItems.length > 0 && (
            <div className="rounded-xl bg-stone-50 p-3 text-xs text-stone-600" data-testid="part-files">
              <p>
                {t("조립형 구조물은 파트를 따로 출력해 끼워 맞춰요. STL은 파트 {n}개가 zip 하나로, 3MF는 파일 하나에 파트를 모두 담아요.", {
                  n: partCount,
                })}
              </p>
              <ul className="mt-1 list-disc pl-4">
                {files.map((f) => (
                  <li key={f.name}>
                    <span className="font-mono">{f.name}</span> · {t(f.label)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {error && (
            <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">
              {error}
            </p>
          )}
        </>
      ) : (
        <p className="rounded-xl bg-stone-100 p-3 text-sm text-stone-600">
          {t("검증 문제를 해결해야 파일을 내려받을 수 있어요. 위의 수정 요청란에 바꿀 내용을 적어 다시 설계하면 돼요.")}
        </p>
      )}
      {kind === "aquarium" && printNotes !== null && <AquariumPrintNotice notes={printNotes} />}
      <Link
        href={`/order?design=${designId}&version=${version}`}
        className="block rounded-xl border border-stone-300 px-4 py-3 text-center font-medium hover:bg-stone-50"
      >
        {t("제작·배송 신청하기")}
      </Link>
      <p className="text-xs text-stone-500">
        {t("파일은 mm 단위이며, 서포트 없이 출력할 수 있는 자세로 놓여 있어요.")}
      </p>
    </section>
  );
}
