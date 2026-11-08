import Image from "next/image";

import { useT } from "@/i18n/client";
import type { PostImage } from "@/lib/types";

/** 사진 아래 출처 표시 (CC 라이선스: 촬영자·라이선스·원본 링크) */
export function ImageCredit({ img }: { img: PostImage }) {
  const t = useT();
  return (
    <>
      {t("사진: {credit}", { credit: img.credit })} ·{" "}
      <a href={img.source_url} target="_blank" rel="noopener noreferrer nofollow" className="underline-offset-2 hover:underline">
        {t(img.license)}
      </a>
    </>
  );
}

/** 글 본문 위의 사진. 첫 장은 크게, 나머지는 아래에 나란히 */
export default function PostImages({ images }: { images: PostImage[] }) {
  if (images.length === 0) return null;
  const [first, ...rest] = images;
  return (
    <div className="mt-5 space-y-3">
      <Figure img={first} priority />
      {rest.length > 0 && (
        <div className={`grid gap-3 ${rest.length === 1 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-2 sm:grid-cols-3"}`}>
          {rest.map((img) => (
            <Figure key={img.src} img={img} />
          ))}
        </div>
      )}
    </div>
  );
}

function Figure({ img, priority = false }: { img: PostImage; priority?: boolean }) {
  const t = useT();
  const alt = t(img.alt);
  return (
    <figure>
      <Image
        src={img.src}
        alt={alt}
        width={img.width}
        height={img.height}
        unoptimized
        priority={priority}
        className="h-auto max-h-[28rem] w-full rounded-xl bg-stone-100 object-cover"
      />
      <figcaption className="mt-1 text-xs text-stone-500">
        <span className="text-stone-600">{alt}</span>
        <span aria-hidden> · </span>
        <ImageCredit img={img} />
      </figcaption>
    </figure>
  );
}
