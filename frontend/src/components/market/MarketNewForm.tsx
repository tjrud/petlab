"use client";
/* eslint-disable @next/next/no-img-element -- 올린 미리보기 이미지는 Blob 공개 주소(외부)에서 바로 받는다 */

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { CharCount, errorText, oneLine, Placeholder } from "@/components/community/common";
import { EmailUnverifiedNotice, useEmailBlocked } from "@/components/EmailVerification";
import LoginRequired from "@/components/LoginRequired";
import { FORMAT_HINT, formatBytes, imageSrc, MARKET_CATEGORIES, marketHref } from "@/components/market/common";
import LayoutPreview from "@/components/market/LayoutPreview";
import { api, isEmailUnverified } from "@/lib/api";
import { uploadMarketFile } from "@/lib/marketUpload";
import { isMeshFormat } from "@/lib/meshUrl";
import type { CageLayout, MarketCategory, MarketConfig, MarketFile } from "@/lib/types";
import { ui } from "@/lib/ui";

const MAX_FILES = 5; // 서버 MAX_ITEM_FILES 와 같다
const LIMITS = { title: 100, description: 3000 } as const;

type Slot = {
  key: string;
  name: string;
  size: number;
  status: "uploading" | "done" | "error";
  sent: number;
  file?: MarketFile;
  error?: string;
  /** STL·3MF 로 자동으로 만든 미리보기 이미지 */
  auto?: boolean;
};

export function MarketNewPlaceholder() {
  return <Placeholder rows={3} label="올리기 화면을 준비하는 중이에요" rowClassName="h-24" />;
}

let slotSeq = 0;

/** 공유 작품 올리기: 완성 파일(SKP·3MF·STL) 또는 가상 케이지 배치 + 소개 */
export default function MarketNewForm() {
  const router = useRouter();
  const { status, user, emailUnverified } = useAuth();
  const ids = { title: useId(), desc: useId(), cat: useId(), files: useId(), image: useId(), count: useId() };

  const [config, setConfig] = useState<MarketConfig | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  // 가상 케이지의 "탐색에 공유"로 들어오면(?layout=) 그 배치안을 함께 공유한다
  const layoutParam = useSearchParams().get("layout");
  const [layout, setLayout] = useState<CageLayout | null>(null);
  const [layoutError, setLayoutError] = useState<string | null>(null);
  const [category, setCategory] = useState<MarketCategory>(layoutParam ? "layout" : "hideout");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [image, setImage] = useState<Slot | null>(null);
  const [toCommunity, setToCommunity] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailBlocked, setEmailBlocked] = useEmailBlocked();
  const fileInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  /** 미리보기 이미지 칸이 차 있는지 (비동기 작업에서 최신 값을 보려고) */
  const imageTaken = useRef(false);
  /** 3D 모습으로 미리보기 이미지를 그리는 중 (그동안 등록을 막는다) */
  const [autoRendering, setAutoRendering] = useState(false);
  /** 이 값이 바뀌면 그리던 미리보기를 버린다 (사람이 이미지를 골랐거나 등록을 시작했을 때) */
  const autoToken = useRef(0);
  useEffect(() => {
    imageTaken.current = image !== null;
  }, [image]);

  useEffect(() => {
    if (!layoutParam || !user) return;
    let alive = true;
    api.layout(layoutParam).then(
      (l) => {
        if (!alive) return;
        setLayout(l);
        setTitle((t) => t || l.name);
      },
      (e: unknown) => alive && setLayoutError(errorText(e, "배치안을 불러오지 못했어요.")),
    );
    return () => {
      alive = false;
    };
  }, [layoutParam, user]);

  useEffect(() => {
    let alive = true;
    api.marketConfig().then(
      (c) => alive && setConfig(c),
      () => alive && setConfig(null),
    );
    return () => {
      alive = false;
    };
  }, []);

  if (status === null) return <MarketNewPlaceholder />;
  if (!user) return <LoginRequired message="로그인하면 작품을 올릴 수 있어요" />;

  const uploading = slots.some((s) => s.status === "uploading") || image?.status === "uploading" || autoRendering;
  const doneFiles = slots.filter((s) => s.status === "done" && s.file).map((s) => s.file!);
  const uploadsOff = config !== null && !config.uploads_enabled;

  const setSlot = (key: string, patch: Partial<Slot>, isImage = false) => {
    if (isImage) setImage((s) => (s && s.key === key ? { ...s, ...patch } : s));
    else setSlots((list) => list.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  };

  async function start(file: File, isImage: boolean, auto = false) {
    const slot: Slot = { key: `s${++slotSeq}`, name: file.name, size: file.size, status: "uploading", sent: 0, auto };
    if (isImage) {
      if (!auto) autoToken.current += 1; // 직접 고른 이미지가 우선
      imageTaken.current = true;
      setImage(slot);
    } else setSlots((list) => [...list, slot]);
    try {
      const f = await uploadMarketFile(file, isImage ? "image" : "model", (sent) => setSlot(slot.key, { sent }, isImage));
      setSlot(slot.key, { status: "done", file: f, sent: file.size }, isImage);
      if (!isImage) void autoImage(file, f);
    } catch (e) {
      if (isEmailUnverified(e)) setEmailBlocked(true);
      setSlot(slot.key, { status: "error", error: errorText(e, "올리지 못했어요.") }, isImage);
    }
  }

  /** 미리보기 이미지를 고르지 않았으면 처음 올린 STL·3MF 의 3D 모습을 그려 대신 올린다 */
  async function autoImage(file: File, uploaded: MarketFile) {
    if (imageTaken.current || !isMeshFormat(uploaded.format) || !uploaded.dims_mm) return;
    imageTaken.current = true; // 그리는 동안 다른 파일이 또 그리지 않게
    const token = ++autoToken.current;
    setAutoRendering(true);
    let blob: Blob | null = null;
    let thumbnailFile: ((b: Blob, name: string) => File) | null = null;
    try {
      // 3D 그리기 코드(three.js)는 필요할 때 받는다 (올리기 화면 첫 로딩을 가볍게)
      const mod = await import("@/lib/meshThumbnail");
      thumbnailFile = mod.thumbnailFile;
      blob = await mod.renderMeshThumbnail(await file.arrayBuffer(), uploaded.format);
    } catch {
      blob = null;
    } finally {
      setAutoRendering(false);
    }
    if (token !== autoToken.current) return; // 그사이 이미지를 직접 골랐거나 등록을 시작했다
    if (!blob || !thumbnailFile) {
      imageTaken.current = false;
      return;
    }
    await start(thumbnailFile(blob, file.name), true, true);
  }

  function pickFiles(list: FileList | null) {
    if (!list) return;
    const room = MAX_FILES - slots.filter((s) => s.status !== "error").length;
    const files = Array.from(list).slice(0, Math.max(0, room));
    if (list.length > files.length) setError(`파일은 ${MAX_FILES}개까지 올릴 수 있어요.`);
    for (const f of files) void start(f, false);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setEmailBlocked(false);
    if (!title.trim()) return setError("제목을 입력해 주세요.");
    if (!description.trim()) return setError("소개를 입력해 주세요.");
    if (doneFiles.length === 0 && !layout) return setError("파일을 하나 이상 올려 주세요.");
    if (uploading) return setError("파일을 다 올린 뒤에 등록해 주세요.");
    autoToken.current += 1;
    setSubmitting(true);
    try {
      const item = await api.createMarketItem({
        title: title.trim(),
        description: description.trim(),
        category,
        file_ids: doneFiles.map((f) => f.id),
        image_file_id: image?.status === "done" && image.file ? image.file.id : null,
        layout_id: layout?.id ?? null,
        post_to_community: toCommunity,
      });
      router.replace(marketHref(item.id));
    } catch (err) {
      if (isEmailUnverified(err)) setEmailBlocked(true);
      else setError(errorText(err, "작품을 올리지 못했어요. 다시 시도해 주세요."));
      setSubmitting(false);
    }
  }

  const accept = (config?.model_formats ?? ["skp", "3mf", "stl"]).map((f) => `.${f}`).join(",");
  const acceptImage = ".png,.jpg,.jpeg,.webp";

  return (
    <form onSubmit={submit} noValidate className={`${ui.card} space-y-6`}>
      {(emailUnverified || emailBlocked) && <EmailUnverifiedNotice action="작품을 올릴" />}
      {uploadsOff && (
        <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          {layoutParam
            ? "지금은 파일을 올릴 수 없어요. 가상 케이지 배치는 그대로 공유할 수 있어요."
            : "지금은 파일을 올릴 수 없어요. 가상 케이지에서 저장한 배치는 '탐색에 공유'로 올릴 수 있어요."}
        </p>
      )}

      {layoutParam && (
        <section aria-label="공유할 가상 케이지 배치" className="rounded-xl border border-sky-200 bg-sky-50/40 p-4">
          <p className={ui.label}>공유할 가상 케이지 배치</p>
          {layout ? (
            <>
              <LayoutPreview layout={layout} className="mx-auto max-h-64 w-full" />
              <p className="mt-2 text-sm text-stone-600">
                {layout.name} · 케이지 {layout.cage.width_mm}×{layout.cage.depth_mm}×{layout.cage.height_mm}mm · 구조물 {layout.items.length}개
              </p>
              <p className="text-xs text-stone-500">배치에 넣은 내 파일(STL·3MF)도 이 배치를 보는 사람이 3D로 볼 수 있게 공개돼요.</p>
            </>
          ) : (
            <p className="text-sm text-stone-500">{layoutError ?? "불러오는 중…"}</p>
          )}
        </section>
      )}

      <div>
        <label htmlFor={ids.title} className={ui.label}>
          제목
        </label>
        <input
          id={ids.title}
          className={ui.input}
          value={title}
          maxLength={LIMITS.title}
          onChange={(e) => setTitle(oneLine(e.target.value))}
          disabled={submitting}
        />
      </div>

      <div>
        <label htmlFor={ids.cat} className={ui.label}>
          분류
        </label>
        <select id={ids.cat} className={ui.input} value={category} onChange={(e) => setCategory(e.target.value as MarketCategory)} disabled={submitting}>
          {MARKET_CATEGORIES.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor={ids.desc} className={ui.label}>
          소개
        </label>
        <textarea
          id={ids.desc}
          rows={6}
          className={`${ui.input} leading-relaxed`}
          placeholder="크기, 만든 프로그램, 출력 설정, 어떤 케이지에 맞는지 등을 적어 주세요."
          value={description}
          maxLength={LIMITS.description}
          aria-describedby={ids.count}
          onChange={(e) => setDescription(e.target.value)}
          disabled={submitting}
        />
        <CharCount id={ids.count} length={description.length} max={LIMITS.description} />
      </div>

      <fieldset disabled={submitting || uploadsOff} className="space-y-2">
        <legend className={ui.label}>
          완성 파일 <span className="font-normal text-stone-500">(SKP·3MF·STL, 최대 {MAX_FILES}개, 파일당 {formatBytes(config?.max_model_bytes ?? 50 * 1024 * 1024)})</span>
        </legend>
        <p className="text-xs text-stone-500">3D 미리보기와 가상 케이지에는 STL·3MF가 필요해요. SKP만 있다면 STL로도 내보내 함께 올려 주세요.</p>
        <input
          ref={fileInput}
          id={ids.files}
          type="file"
          multiple
          accept={accept}
          className="sr-only"
          aria-label="완성 파일 고르기"
          onChange={(e) => {
            pickFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <button type="button" className={ui.btnSecondary} onClick={() => fileInput.current?.click()}>
          파일 고르기
        </button>
        {slots.length > 0 && (
          <ul className="space-y-1.5">
            {slots.map((s) => (
              <SlotRow key={s.key} slot={s} onRemove={() => setSlots((l) => l.filter((x) => x.key !== s.key))} />
            ))}
          </ul>
        )}
      </fieldset>

      <fieldset disabled={submitting || uploadsOff} className="space-y-2">
        <legend className={ui.label}>
          미리보기 이미지 <span className="font-normal text-stone-500">(선택 · PNG·JPG·WEBP)</span>
        </legend>
        <p className="text-xs text-stone-500">
          {autoRendering ? "올린 3D 파일로 미리보기 이미지를 만드는 중이에요." : "고르지 않으면 올린 STL·3MF의 3D 모습으로 만들어 넣어요."}
        </p>
        <input
          ref={imageInput}
          id={ids.image}
          type="file"
          accept={acceptImage}
          className="sr-only"
          aria-label="미리보기 이미지 고르기"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void start(f, true);
            e.target.value = "";
          }}
        />
        {image ? (
          <ul>
            <SlotRow slot={image} onRemove={() => setImage(null)} />
          </ul>
        ) : null}
        {image?.status === "done" && image.file && (
          <img src={imageSrc(image.file)} alt="미리보기 이미지" className="max-h-48 rounded-lg border border-stone-200 bg-stone-50 object-contain" />
        )}
        {image ? (
          image.auto && (
            <button type="button" className={ui.btnSecondary} onClick={() => imageInput.current?.click()}>
              다른 이미지로 바꾸기
            </button>
          )
        ) : (
          <button type="button" className={ui.btnSecondary} onClick={() => imageInput.current?.click()}>
            이미지 고르기
          </button>
        )}
      </fieldset>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={toCommunity}
          disabled={submitting}
          onChange={(e) => setToCommunity(e.target.checked)}
        />
        <span>
          커뮤니티에 소개 글도 올리기
          <span className="block text-xs text-stone-500">
            댓글은 소개 글에서 받아요.
          </span>
        </span>
      </label>

      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <button type="submit" className={ui.btnPrimary} disabled={submitting || uploading || emailUnverified || (uploadsOff && !layoutParam)}>
          {submitting ? "올리는 중…" : autoRendering ? "미리보기 만드는 중…" : uploading ? "파일 올리는 중…" : "탐색에 올리기"}
        </button>
      </div>
    </form>
  );
}

function SlotRow({ slot, onRemove }: { slot: Slot; onRemove: () => void }) {
  const pct = slot.size ? Math.round((slot.sent / slot.size) * 100) : 0;
  const fmt = slot.name.split(".").pop()?.toLowerCase() ?? "";
  return (
    <li className="flex items-center gap-3 rounded-lg border border-stone-200 px-3 py-2 text-sm">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{slot.name}</p>
        <p className="text-xs text-stone-500">
          {formatBytes(slot.size)}
          {FORMAT_HINT[fmt] ? ` · ${FORMAT_HINT[fmt]}` : ""}
          {slot.status === "uploading" && ` · ${pct}%`}
          {slot.status === "done" && " · 올림"}
          {slot.auto && " · 3D 파일로 만든 이미지"}
        </p>
        {slot.status === "uploading" && (
          <div className="mt-1 h-1.5 overflow-hidden rounded bg-stone-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${slot.name} 올리는 중`}>
            <div className="h-full bg-amber-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
        )}
        {slot.status === "error" && <p className="text-xs text-red-700">{slot.error}</p>}
      </div>
      {slot.status !== "uploading" && (
        <button type="button" onClick={onRemove} className="shrink-0 text-xs text-stone-500 hover:text-red-700" aria-label={`${slot.name} 빼기`}>
          빼기
        </button>
      )}
    </li>
  );
}
