"use client";

import Image from "next/image";

import { COMMUNITY_IMAGES } from "@/lib/communityImages";
import type { PostImage } from "@/lib/types";

export const MAX_IMAGES = 4; // 서버 MAX_POST_IMAGES 와 같다

const toPostImage = ({ src, alt, width, height, credit, license, source_url }: PostImage): PostImage => ({
  src,
  alt,
  width,
  height,
  credit,
  license,
  source_url,
});

/** 운영팀 글의 사진 고르기 (사이트에 함께 배포한 사진 중에서, 최대 4장). 고른 순서대로 보여요 */
export default function ImagePicker({
  value,
  onChange,
  disabled = false,
}: {
  value: PostImage[];
  onChange: (v: PostImage[]) => void;
  disabled?: boolean;
}) {
  const chosen = new Map(value.map((v, i) => [v.src, i]));
  const groups = [...new Set(COMMUNITY_IMAGES.map((i) => i.group))];
  // 목록에서 빠진 옛 사진도 고른 상태로 보이게 (빼기만 할 수 있다)
  const orphans = value.filter((v) => !COMMUNITY_IMAGES.some((c) => c.src === v.src));

  const toggle = (img: PostImage) => {
    if (chosen.has(img.src)) onChange(value.filter((v) => v.src !== img.src));
    else if (value.length < MAX_IMAGES) onChange([...value, toPostImage(img)]);
  };

  const tile = (img: PostImage) => {
    const order = chosen.get(img.src);
    const on = order !== undefined;
    return (
      <li key={img.src}>
        <button
          type="button"
          aria-pressed={on}
          aria-label={`${img.alt}${on ? ` (${order + 1}번째)` : ""}`}
          disabled={disabled || (!on && value.length >= MAX_IMAGES)}
          onClick={() => toggle(img)}
          className={`relative block w-full overflow-hidden rounded-lg border-2 disabled:opacity-40 ${
            on ? "border-amber-500" : "border-transparent hover:border-amber-200"
          }`}
        >
          <Image src={img.src} alt="" width={img.width} height={img.height} unoptimized className="aspect-[4/3] w-full object-cover" />
          {on && (
            <span className="absolute left-1 top-1 grid h-6 w-6 place-items-center rounded-full bg-amber-500 text-xs font-bold text-white">
              {order + 1}
            </span>
          )}
        </button>
      </li>
    );
  };

  return (
    <fieldset disabled={disabled}>
      <legend className="mb-1 block text-sm font-medium">
        사진 <span className="font-normal text-stone-500">(운영팀만 · 최대 {MAX_IMAGES}장, 고른 순서대로 보여요)</span>
      </legend>
      {COMMUNITY_IMAGES.length === 0 && orphans.length === 0 ? (
        <p className="text-sm text-stone-500">넣을 수 있는 사진이 아직 없어요.</p>
      ) : (
        <div className="max-h-80 space-y-3 overflow-y-auto rounded-lg border border-stone-200 p-3">
          {orphans.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold text-stone-600">목록에 없는 사진</p>
              <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">{orphans.map(tile)}</ul>
            </div>
          )}
          {groups.map((g) => (
            <div key={g}>
              <p className="mb-1 text-xs font-semibold text-stone-600">{g}</p>
              <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">{COMMUNITY_IMAGES.filter((i) => i.group === g).map(tile)}</ul>
            </div>
          ))}
        </div>
      )}
    </fieldset>
  );
}
