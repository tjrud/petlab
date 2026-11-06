"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { CharCount, errorText, oneLine, Placeholder } from "@/components/community/common";
import DesignAttachField, { useAttachOptions } from "@/components/community/DesignAttachField";
import { EmailUnverifiedNotice, useEmailBlocked } from "@/components/EmailVerification";
import LoginRequired from "@/components/LoginRequired";
import { FORMAT_HINT, formatBytes, MARKET_CATEGORIES, marketHref } from "@/components/market/common";
import { api, isEmailUnverified } from "@/lib/api";
import { uploadMarketFile } from "@/lib/marketUpload";
import type { MarketCategory, MarketConfig, MarketFile } from "@/lib/types";
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
};

export function MarketNewPlaceholder() {
  return <Placeholder rows={3} label="올리기 화면을 준비하는 중이에요" rowClassName="h-24" />;
}

let slotSeq = 0;

/** 둥지마당 작품 올리기: 완성 파일(SKP·3MF·STL) 또는 NestForge 설계 + 소개 */
export default function MarketNewForm() {
  const router = useRouter();
  const { status, user, emailUnverified } = useAuth();
  const attach = useAttachOptions(user?.id ?? null, null, undefined);
  const ids = { title: useId(), desc: useId(), cat: useId(), files: useId(), image: useId(), count: useId() };

  const [config, setConfig] = useState<MarketConfig | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<MarketCategory>("hideout");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [image, setImage] = useState<Slot | null>(null);
  const [designId, setDesignId] = useState("");
  const [toCommunity, setToCommunity] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailBlocked, setEmailBlocked] = useEmailBlocked();
  const fileInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);

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

  const design = attach.kind === "ok" ? (attach.options.find((o) => o.id === designId) ?? null) : null;
  const uploading = slots.some((s) => s.status === "uploading") || image?.status === "uploading";
  const doneFiles = slots.filter((s) => s.status === "done" && s.file).map((s) => s.file!);
  const uploadsOff = config !== null && !config.uploads_enabled;

  const setSlot = (key: string, patch: Partial<Slot>, isImage = false) => {
    if (isImage) setImage((s) => (s && s.key === key ? { ...s, ...patch } : s));
    else setSlots((list) => list.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  };

  async function start(file: File, isImage: boolean) {
    const slot: Slot = { key: `s${++slotSeq}`, name: file.name, size: file.size, status: "uploading", sent: 0 };
    if (isImage) setImage(slot);
    else setSlots((list) => [...list, slot]);
    try {
      const f = await uploadMarketFile(file, isImage ? "image" : "model", (sent) => setSlot(slot.key, { sent }, isImage));
      setSlot(slot.key, { status: "done", file: f, sent: file.size }, isImage);
    } catch (e) {
      if (isEmailUnverified(e)) setEmailBlocked(true);
      setSlot(slot.key, { status: "error", error: errorText(e, "올리지 못했어요.") }, isImage);
    }
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
    if (doneFiles.length === 0 && !design) return setError("파일을 올리거나 NestForge 설계를 하나 골라 주세요.");
    if (uploading) return setError("파일을 다 올린 뒤에 등록해 주세요.");
    setSubmitting(true);
    try {
      const item = await api.createMarketItem({
        title: title.trim(),
        description: description.trim(),
        category,
        file_ids: doneFiles.map((f) => f.id),
        image_file_id: image?.status === "done" && image.file ? image.file.id : null,
        design_id: design?.id ?? null,
        design_version: design?.version ?? null,
        post_to_community: toCommunity || !!design,
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
          지금은 파일 저장소가 준비되지 않아 파일을 올릴 수 없어요. NestForge 설계는 공유할 수 있어요.
        </p>
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
        ) : (
          <button type="button" className={ui.btnSecondary} onClick={() => imageInput.current?.click()}>
            이미지 고르기
          </button>
        )}
      </fieldset>

      <div>
        <p className={ui.label}>NestForge 설계 함께 공유 (선택)</p>
        <DesignAttachField state={attach} value={designId} onChange={setDesignId} disabled={submitting} />
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={toCommunity || !!design}
          disabled={!!design || submitting}
          onChange={(e) => setToCommunity(e.target.checked)}
        />
        <span>
          커뮤니티에 소개 글도 올리기
          <span className="block text-xs text-stone-500">
            {design ? "설계를 공유하려면 소개 글이 필요해요. 댓글은 소개 글에서 받아요." : "댓글은 소개 글에서 받아요."}
          </span>
        </span>
      </label>

      {error && (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <button type="submit" className={ui.btnPrimary} disabled={submitting || uploading || emailUnverified}>
          {submitting ? "올리는 중…" : uploading ? "파일 올리는 중…" : "둥지마당에 올리기"}
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
