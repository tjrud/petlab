"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const NAV = [
  { href: "/design", label: "설계하기" },
  { href: "/cage", label: "가상 케이지" },
  { href: "/designs", label: "내 설계" },
  { href: "/explore", label: "탐색" },
  { href: "/community", label: "커뮤니티" },
] as const;

/** 넓은 화면에서는 헤더 맨 오른쪽(로그인 메뉴 옆)에 따로 둔다 */
export const ME_NAV = { href: "/me", label: "내 정보" } as const;

function isActive(pathname: string, href: string): boolean {
  // 뒤에 "/" 를 붙여 비교하므로 "/design" 이 "/designs" 를 잡지 않는다
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * 헤더 메뉴. 넓은 화면은 로고 옆(main)과 맨 오른쪽 "내 정보"(me)로 나누고,
 * 좁은 화면은 헤더 아래 줄에 모두(all) 가로로 보인다.
 */
export default function NavLinks({ className = "", part = "all" }: { className?: string; part?: "main" | "me" | "all" }) {
  const pathname = usePathname() ?? "/";
  const items = part === "main" ? NAV : part === "me" ? [ME_NAV] : [...NAV, ME_NAV];
  return (
    <nav aria-label={part === "me" ? "내 정보 메뉴" : "주 메뉴"} className={className}>
      <ul className="flex items-center gap-1 overflow-x-auto text-sm">
        {items.map((n) => {
          const active = isActive(pathname, n.href);
          return (
            <li key={n.href}>
              <Link
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`block whitespace-nowrap rounded-lg px-3 py-1.5 ${
                  active ? "bg-amber-100 font-semibold text-amber-900" : "text-stone-600 hover:bg-stone-100"
                }`}
              >
                {n.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
