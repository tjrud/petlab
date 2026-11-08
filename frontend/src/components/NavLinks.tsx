"use client";

import { Link } from "@/i18n/client";
import { usePathname } from "@/i18n/client";
import { useEffect, useRef, useState } from "react";

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
  const list = useRef<HTMLUListElement>(null);
  // 좁은 화면에서 메뉴가 한 줄에 다 들어가지 않으면 가로로 밀어서 본다. 스크롤바 대신 가려진 쪽 끝을 흐리게 해서 알린다
  const [more, setMore] = useState({ left: false, right: false });

  useEffect(() => {
    const ul = list.current;
    if (!ul) return;
    const update = () => {
      const left = ul.scrollLeft > 1;
      const right = ul.scrollLeft + ul.clientWidth < ul.scrollWidth - 1;
      setMore((m) => (m.left === left && m.right === right ? m : { left, right }));
    };
    update();
    ul.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(ul);
    return () => {
      ul.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, []);

  // 지금 보는 메뉴가 가려져 있으면 보이는 곳으로 옮긴다 (예: 내 정보·커뮤니티)
  useEffect(() => {
    const ul = list.current;
    const active = ul?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!ul || !active || ul.scrollWidth <= ul.clientWidth) return;
    const a = active.offsetLeft - ul.offsetLeft;
    if (a < ul.scrollLeft || a + active.offsetWidth > ul.scrollLeft + ul.clientWidth) {
      ul.scrollLeft = Math.max(0, a - (ul.clientWidth - active.offsetWidth) / 2);
    }
  }, [pathname]);

  const fade = more.left && more.right
    ? "[mask-image:linear-gradient(to_right,transparent,black_2rem,black_calc(100%-2rem),transparent)]"
    : more.right
      ? "[mask-image:linear-gradient(to_right,black_calc(100%-2.5rem),transparent)]"
      : more.left
        ? "[mask-image:linear-gradient(to_right,transparent,black_2.5rem)]"
        : "";

  return (
    <nav aria-label={part === "me" ? "내 정보 메뉴" : "주 메뉴"} className={className}>
      <ul
        ref={list}
        className={`flex items-center gap-1 overflow-x-auto text-sm [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${fade}`}
      >
        {items.map((n) => {
          const active = isActive(pathname, n.href);
          return (
            <li key={n.href} className="shrink-0">
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
