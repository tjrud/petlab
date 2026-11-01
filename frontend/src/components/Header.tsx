import Link from "next/link";

export default function Header() {
  return (
    <header className="border-b border-amber-200/70 bg-white/70 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-full bg-amber-400 text-lg">🐹</span>
          <span className="text-lg font-bold tracking-tight">꼬물공방</span>
        </Link>
        <span className="hidden text-sm text-stone-500 sm:block">햄스터 맞춤 케이지 구조물 설계</span>
      </div>
    </header>
  );
}
