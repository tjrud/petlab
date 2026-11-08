"use client";
/* eslint-disable @next/next/no-img-element -- 미리보기는 Blob 공개 주소(외부)에서 바로 받는다 */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthorName, errorText, Placeholder, postHref } from "@/components/community/common";
import SharedDesignCard from "@/components/community/SharedDesignCard";
import { useAuth } from "@/components/AuthProvider";
import LayoutPreview from "@/components/market/LayoutPreview";
import { fileIdOf, getAsset, registerFileAsset } from "@/lib/cageAssets";
import { readDraft, writeDraft } from "@/lib/cagePlannerDoc";
import { FORMAT_HINT, FORMAT_LABEL, formatBytes, FormatChips, imageSrc, MARKET_PATH } from "@/components/market/common";
import RetryAlert from "@/components/RetryAlert";
import { AUTO_3D_BYTES, canDecodeNfm, isMeshFormat, needsCredentials } from "@/lib/meshUrl";
import { api, ApiError } from "@/lib/api";
import { uploadMarketFile } from "@/lib/marketUpload";
import type { MarketFile, MarketItem } from "@/lib/types";
import { formatDateTime, ui } from "@/lib/ui";

const ModelPreview = dynamic(() => import("@/components/market/ModelPreview"), {
  ssr: false,
  loading: () => <div className="h-80 animate-pulse rounded-xl bg-stone-100 sm:h-96" />,
});

/** 3D 로 볼 수 있는 파일 (STL·3MF 이고 크기를 읽은 것) */
const previewable = (f: MarketFile) => isMeshFormat(f.format) && !!f.mesh_url && !!f.dims_mm;

const saveData = () =>
  typeof navigator !== "undefined" && !!(navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;

/** 사용자에게 그대로 보여 줄 오류 (그 밖의 브라우저 오류는 정해 둔 문구로 바꾼다) */
class ShownError extends Error {}

/** 가상 케이지에서 이 파일을 빈 자리에 놓는 주소 */
export const cageAddHref = (fileId: string) => `/cage?add=${encodeURIComponent(fileId)}`;

type Result = { key: string; kind: "ok"; item: MarketItem } | { key: string; kind: "error"; status: number; message: string };

export function MarketItemPlaceholder() {
  return <Placeholder rows={2} label="작품을 불러오는 중이에요" rowClassName="h-48" />;
}

/** 공유 작품 보기: 미리보기(이미지·3D)·소개·파일 내려받기·가상 케이지에 놓아 보기·커뮤니티 소개 글 */
export default function MarketItemDetail({ id }: { id: string }) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copying, setCopying] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [thumbBusy, setThumbBusy] = useState(false);
  /** "3D로 보기"를 한 번 눌렀으면 다른 파일도 바로 보여 준다 */
  const [opened3d, setOpened3d] = useState(false);
  const [glUnavailable, setGlUnavailable] = useState(false);
  const { user } = useAuth();
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

  // 배치에 들어 있는 파일(STL·3MF)의 크기를 받아 위에서 본 그림에 실제 크기로 그린다
  const [, setFilesVer] = useState(0);
  const layoutItems = result?.kind === "ok" ? (result.item.layout?.items ?? null) : null;
  useEffect(() => {
    if (!layoutItems) return;
    const ids = [...new Set(layoutItems.map((it) => fileIdOf(it.asset)).filter((x): x is string => !!x && !getAsset(`file_${x}`)))];
    if (!ids.length) return;
    let alive = true;
    void Promise.allSettled(ids.map((fid) => api.marketFile(fid).then((f) => registerFileAsset(f, api.marketUrl)))).then(
      () => alive && setFilesVer((v) => v + 1),
    );
    return () => {
      alive = false;
    };
  }, [layoutItems]);

  const r = result?.key === key ? result : null;
  if (!r) return <MarketItemPlaceholder />;
  if (r.kind === "error") {
    if (r.status === 404) {
      return (
        <div className={`${ui.card} text-center`}>
          <h1 className="text-xl font-bold">작품을 찾을 수 없어요</h1>
          <p className="mt-2 text-sm text-stone-600">주소가 잘못되었거나 지워진 작품이에요.</p>
          <Link href={MARKET_PATH} className={`${ui.btnSecondary} mt-4`}>
            탐색으로
          </Link>
        </div>
      );
    }
    return <RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} />;
  }
  const it = r.item;
  const meshFiles = it.files.filter(previewable);
  const preview = meshFiles.find((f) => f.id === previewId) ?? meshFiles[0] ?? null;
  const hasSkp = it.files.some((f) => f.format === "skp");
  /** 3D 파일로 자동으로 만든 대표 이미지인지 (thumbnailFile 이 붙이는 이름) */
  const autoImage = !!it.image && /-미리보기\.(webp|png|jpg)$/.test(it.image.filename);
  // 받을 크기: 가벼운 미리보기 메시가 있으면 그 크기 (보통 1MB 안팎이라 바로 보여 준다)
  const loadBytes = preview ? (preview.preview_size && canDecodeNfm() ? preview.preview_size : preview.size) : 0;
  const show3d = !!preview && (opened3d || (loadBytes <= AUTO_3D_BYTES && !saveData()));

  /** 3D 모습을 그려 대표 이미지로 (이미지 없이 올린 작품. 올린 사람만) */
  async function makeImage(f: MarketFile) {
    if (!f.mesh_url || !isMeshFormat(f.format)) return;
    setThumbBusy(true);
    setActionError(null);
    try {
      // 3D 그리기 코드(three.js)는 이 버튼을 누를 때 받는다 (상세 화면 첫 로딩을 가볍게)
      const { renderMeshThumbnail, thumbnailFile } = await import("@/lib/meshThumbnail");
      /** 받아서 그린다. 받지 못했으면 "fetch", 그리지 못했으면 "render" */
      const tryRender = async (path: string, fmt: Parameters<typeof renderMeshThumbnail>[1]): Promise<Blob | "fetch" | "render"> => {
        const url = api.marketUrl(path);
        let buffer: ArrayBuffer;
        try {
          const res = await fetch(url, { credentials: needsCredentials(url) ? "include" : "omit" });
          if (!res.ok) return "fetch";
          buffer = await res.arrayBuffer();
        } catch {
          return "fetch";
        }
        try {
          return (await renderMeshThumbnail(buffer, fmt)) ?? "render";
        } catch {
          return "render";
        }
      };
      // 가벼운 미리보기 메시로 먼저, 안 되면 원본으로
      let got: Blob | "fetch" | "render" = "fetch";
      if (f.preview_url && canDecodeNfm()) got = await tryRender(f.preview_url, "nfm");
      if (!(got instanceof Blob)) got = await tryRender(f.mesh_url, f.format);
      if (got === "fetch") throw new ShownError("파일을 받지 못했어요. 잠시 뒤 다시 해 주세요.");
      const blob = got === "render" ? null : got;
      if (!blob) throw new ShownError("이 파일로는 이미지를 만들 수 없어요.");
      const img = await uploadMarketFile(thumbnailFile(blob, f.filename), "image", () => {});
      const item = await api.updateMarketItem(it.id, { image_file_id: img.id });
      setResult({ key, kind: "ok", item });
    } catch (e) {
      setActionError(e instanceof ShownError ? e.message : errorText(e, "대표 이미지를 만들지 못했어요."));
    } finally {
      setThumbBusy(false);
    }
  }

  /** 배치 예시를 내 가상 케이지로: 로그인했으면 내 배치안으로 저장해 열고, 아니면 이 브라우저의 작업으로 담아 연다 */
  async function copyToCage() {
    const lay = it.layout;
    if (!lay) return;
    setActionError(null);
    if (user) {
      setCopying(true);
      try {
        const { layout_id } = await api.copyLayout(it.id);
        router.push(`/cage?layout=${encodeURIComponent(layout_id)}`);
      } catch (e) {
        setActionError(errorText(e, "담지 못했어요."));
        setCopying(false);
      }
      return;
    }
    const draft = readDraft();
    if (draft && draft.items.length > 0 && !window.confirm("가상 케이지에서 저장하지 않은 작업이 이 배치로 바뀌어요. 계속할까요?")) return;
    writeDraft({
      name: `${lay.name} (탐색)`.slice(0, 40),
      species: lay.species,
      size: lay.size,
      petId: null,
      layoutId: null,
      cage: lay.cage,
      items: lay.items,
    });
    router.push("/cage");
  }

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
          <img src={imageSrc(it.image)} alt={`${it.title} 미리보기`} fetchPriority="high" className="max-h-[28rem] w-full rounded-xl bg-stone-100 object-contain" />
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

        {preview && (
          <section aria-labelledby="preview-title" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="preview-title" className={ui.h2}>
                3D 미리보기
              </h2>
              <Link href={cageAddHref(preview.id)} className={ui.btnPrimary}>
                가상 케이지에 놓아 보기
              </Link>
            </div>
            {meshFiles.length > 1 && (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="미리 볼 파일">
                {meshFiles.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    aria-pressed={f.id === preview.id}
                    onClick={() => setPreviewId(f.id)}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      f.id === preview.id ? "border-amber-500 bg-amber-100 font-semibold text-amber-900" : "border-stone-300 text-stone-600 hover:bg-stone-50"
                    }`}
                  >
                    {f.filename}
                  </button>
                ))}
              </div>
            )}
            {show3d ? (
              <ModelPreview key={preview.id} file={preview} className="h-80 sm:h-96" onUnavailable={() => setGlUnavailable(true)} />
            ) : (
              <div className="relative grid h-80 place-items-center overflow-hidden rounded-xl bg-[#eef1f4] sm:h-96">
                {it.image && (
                  <img src={imageSrc(it.image)} alt="" className="absolute inset-0 h-full w-full object-contain opacity-60" />
                )}
                <button type="button" className={`${ui.btnSecondary} relative`} onClick={() => setOpened3d(true)}>
                  3D로 보기 ({formatBytes(loadBytes)})
                </button>
              </div>
            )}
            <p className="text-xs text-stone-500">
              가상 케이지에 놓으면 지금 작업 중인 케이지의 빈 자리에 실제 크기로 들어가요. 저장은 가상 케이지에서 해요.
            </p>
            {/* 대표 이미지가 없거나 3D 파일로 자동으로 만든 것이면, 올린 사람이 지금 3D 모습으로 (다시) 만들 수 있다 */}
            {it.can_edit && (!it.image || autoImage) && !glUnavailable && (
              <button type="button" className={ui.btnSecondary} onClick={() => void makeImage(preview)} disabled={thumbBusy}>
                {thumbBusy
                  ? "대표 이미지 만드는 중…"
                  : it.image
                    ? "이 3D 모습으로 대표 이미지 다시 만들기"
                    : "이 3D 모습으로 대표 이미지 만들기"}
              </button>
            )}
          </section>
        )}

        {it.layout && (
          <section aria-labelledby="layout-title" className="space-y-3 rounded-xl border border-sky-200 bg-sky-50/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="layout-title" className={ui.h2}>
                가상 케이지 배치
              </h2>
              <button type="button" className={ui.btnPrimary} onClick={() => void copyToCage()} disabled={copying}>
                {copying ? "담는 중…" : "내 가상 케이지로 담기"}
              </button>
            </div>
            <LayoutPreview layout={it.layout} className="mx-auto max-h-80 w-full" />
            <p className="text-sm text-stone-600">
              {it.layout.name} · 케이지 {it.layout.cage.width_mm}×{it.layout.cage.depth_mm}×{it.layout.cage.height_mm}mm ·{" "}
              {it.layout.size_name_ko}
            </p>
            <p className="text-xs text-stone-500">
              {user ? "담으면 내 배치안으로 저장되고 가상 케이지에서 바로 열려요." : "담으면 가상 케이지에서 바로 열려요. 저장하려면 로그인하세요."}
            </p>
          </section>
        )}

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
                  {previewable(f) && (
                    <Link href={cageAddHref(f.id)} className={ui.btnSecondary} aria-label={`${f.filename} 케이지에 놓기`}>
                      케이지에 놓기
                    </Link>
                  )}
                  <a href={api.marketUrl(f.download_url)} className={ui.btnPrimary} aria-label={`${f.filename} 내려받기`}>
                    내려받기
                  </a>
                </li>
              ))}
            </ul>
            {hasSkp && (
              <p className="text-xs text-stone-500">
                SketchUp(SKP) 파일은 브라우저에서 3D로 볼 수 없어 3D 미리보기와 가상 케이지에서 쓸 수 없어요.
              </p>
            )}
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
