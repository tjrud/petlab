"use client";

import { Link, useT } from "@/i18n/client";

import { useAuth } from "@/components/AuthProvider";
import { loginHref, NEW_POST_PATH } from "@/components/community/common";
import { ui } from "@/lib/ui";

/** "글쓰기" 버튼. 로그인하지 않았으면 로그인 화면을 거쳐 글쓰기 화면으로 돌아온다 */
export default function WriteButton() {
  const t = useT();
  const { status, user } = useAuth();
  const href = status !== null && !user ? loginHref(NEW_POST_PATH) : NEW_POST_PATH;
  return (
    <Link href={href} className={`${ui.btnPrimary} shrink-0`}>
      {t("글쓰기")}
    </Link>
  );
}
