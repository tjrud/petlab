"use client";
/* eslint-disable @next/next/no-img-element -- 미리보기는 Blob 공개 주소(외부)에서 바로 받는다 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthorName, errorText, Placeholder, postHref } from "@/components/community/common";
import SharedDesignCard from "@/components/community/SharedDesignCard";
import { FORMAT_HINT, FORMAT_LABEL, formatBytes, FormatChips, imageSrc, MARKET_PATH } from "@/components/market/common";
import RetryAlert from "@/components/RetryAlert";
import { api, ApiError } from "@/lib/api";
import type { MarketItem } from "@/lib/types";
import { formatDateTime, ui } from "@/lib/ui";

type Result = { key: string; kind: "ok"; item: MarketItem } | { key: string; kind: "error"; status: number; message: string };

export function MarketItemPlaceholder() {
  return <Placeholder rows={2} label="작품을 불러오는 중이에요" rowClassName="h-48" />;
}

/** 둥지마당 작품 보기: 미리보기·소개·파일 내려받기·NestForge 설계·커뮤니티 소개 글 */
export default function MarketItemDetail({ id }: { id: string }) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const key = `${id}|${attempt}`;

  useEffect(() => {
    let alive = true;
    api.marketItem(id).then(
      (item) => alive && setResult({ key, kind: "ok", item }),
      (e: unknown) =>
        alive &&
        setResult({ key, kind: "error", status: e instanceof ApiError ? e.status : 0, message: errorText(e, "작품을 불러오지 못했어요.") }),
    );
    return () => {
      alive = false;
    };
  }, [id, key]);

  const r = result?.key === key ? result : null;
  if (!r) return <MarketItemPlaceholder />;
  if (r.kind === "error") {
    if (r.status === 404) {
      return (
        <div className={`${ui.card} text-center`}>
          <h1 className="text-xl font-bold">작품을 찾을 수 없어요</h1>
          <p className="mt-2 text-sm text-stone-600">주소가 잘못되었거나 지워진 작품이에요.</p>
          <Link href={MARKET_PATH} className={`${ui.btnSecondary} mt-4`}>
            둥지마당으로
          </Link>
        </div>
      );
    }
    return <RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} />;
  }
  const it = r.item;

  async function remove() {
    if (!window.confirm("이 작품을 지울까요? 올린 파일도 함께 지워지고 되돌릴 수 없어요. 커뮤니티 소개 글은 남아요.")) return;
    setDeleting(true);
    setActionError(null);
    try {
      await api.deleteMarketItem(it.id);
      router.replace(MARKET_PATH);
    } catch (e) {
      setActionError(errorText(e, "지우지 못했어요."));
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-5">
      <article className={`${ui.card} space-y-4`}>
        {it.image && (
          <img src={imageSrc(it.image)} alt={`${it.title} 미리보기`} className="max-h-[28rem] w-full rounded-xl bg-stone-100 object-contain" />
        )}
        <header className="space-y-2">
          <p className="text-sm font-medium text-amber-800">{it.category_name_ko}</p>
          <h1 className="break-words text-2xl font-bold leading-snug sm:text-3xl">{it.title}</h1>
          <FormatChips formats={it.formats} />
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-stone-500">
            <AuthorName author={it.author} />
            <span aria-hidden>·</span>
            <time dateTime={it.created_at}>{formatDateTime(it.created_at)}</time>
            <span aria-hidden>·</span>
            <span>내려받기 {it.download_count}회</span>
          </p>
        </header>
        <div className="whitespace-pre-wrap break-words leading-relaxed text-stone-800">{it.description}</div>

        {it.files.length > 0 && (
          <section aria-labelledby="files-title" className="space-y-2">
            <h2 id="files-title" className={ui.h2}>
              파일
            </h2>
            <ul className="space-y-2">
              {it.files.map((f) => (
                <li key={f.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-stone-200 p-3">
                  <span className="grid h-10 w-12 shrink-0 place-items-center rounded-lg bg-stone-100 text-xs font-bold text-stone-600">
                    {FORMAT_LABEL[f.format] ?? f.format.toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{f.filename}</span>
                    <span className="block text-xs text-stone-500">
                      {formatBytes(f.size)}
                      {FORMAT_HINT[f.format] ? ` · ${FORMAT_HINT[f.format]}` : ""}
                    </span>
                  </span>
                  <a href={api.marketUrl(f.download_url)} className={ui.btnPrimary} aria-label={`${f.filename} 내려받기`}>
                    내려받기
                  </a>
                </li>
              ))}
            </ul>
            <p className="text-xs text-stone-500">올린 사람이 만든 파일이에요. NestForge 안전 검증을 거치지 않았으니 크기와 틈을 확인하고 쓰세요.</p>
          </section>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-amber-100 pt-4">
          {it.post_id ? (
            <Link href={postHref(it.post_id)} className={`${ui.link} text-sm font-medium`}>
              커뮤니티 소개 글에서 댓글 보기 →
            </Link>
          ) : (
            <span />
          )}
          {it.can_delete && (
            <button type="button" className={ui.btnDanger} onClick={remove} disabled={deleting}>
              {deleting ? "지우는 중…" : "작품 지우기"}
            </button>
          )}
        </div>
        {actionError && (
          <p role="alert" className={ui.error}>
            {actionError}
          </p>
        )}
      </article>
      {it.design && <SharedDesignCard design={it.design} />}
    </div>
  );
}
