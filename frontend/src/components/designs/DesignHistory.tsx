"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import DesignCard from "@/components/designs/DesignCard";
import DesignGridSkeleton from "@/components/designs/DesignGridSkeleton";
import Pagination from "@/components/Pagination";
import LoginRequired from "@/components/LoginRequired";
import RetryAlert from "@/components/RetryAlert";
import { api, errorText, isAuthError } from "@/lib/api";
import type { DesignListItem, Paged } from "@/lib/types";
import { ui } from "@/lib/ui";

const PAGE_SIZE = 12;
const MAX_PAGE = 10_000; // 백엔드 허용 범위

/** 주소의 ?page= 값 (잘못된 값이면 1쪽) */
function parsePage(raw: string | null): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 && n <= MAX_PAGE ? n : 1;
}

const pageHref = (p: number) => (p <= 1 ? "/designs" : `/designs?page=${p}`);

type Result =
  | { key: string; kind: "ok"; data: Paged<DesignListItem> }
  | { key: string; kind: "error"; message: string; authCode: string | null };

/** "내 설계" 목록 (회원 전용). 페이지·로그인 상태가 바뀌면 다시 불러온다. */
export default function DesignHistory() {
  const params = useSearchParams();
  const page = parsePage(params.get("page"));
  const { status, user } = useAuth();
  const authKnown = status !== null;
  const userId = user?.id ?? null;

  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  // 지금 보여 줘야 할 요청. 결과의 key 가 다르면(이전 페이지·이전 사용자 결과) 불러오는 중으로 본다
  const key = `${userId}|${page}|${attempt}`;

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    api.listDesigns(page, PAGE_SIZE).then(
      (data) => {
        if (alive) setResult({ key, kind: "ok", data });
      },
      (e: unknown) => {
        if (!alive) return;
        setResult({
          key,
          kind: "error",
          message: errorText(e, "설계 내역을 불러오지 못했어요."),
          authCode: isAuthError(e) ? (e.code ?? null) : null,
        });
      },
    );
    return () => {
      alive = false;
    };
  }, [userId, page, key]);

  if (!authKnown) return <DesignGridSkeleton />;
  if (!userId) return <LoginRequired message="로그인하면 내 설계 내역을 볼 수 있어요" />;

  const r = result?.key === key ? result : null;
  if (!r) return <DesignGridSkeleton />;

  if (r.kind === "error") {
    if (r.authCode) {
      return (
        <LoginRequired message="로그인하면 내 설계 내역을 볼 수 있어요" unavailable={r.authCode === "auth_unavailable"} />
      );
    }
    return <RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} />;
  }

  const { items, total, page_size } = r.data;
  const totalPages = Math.max(1, Math.ceil(total / page_size));

  if (total === 0) {
    return (
      <div className={`${ui.card} flex flex-col items-center py-12 text-center`}>
        <p className="mt-3 text-lg font-semibold">아직 만든 설계가 없어요</p>
        <p className="mt-1 text-sm text-stone-600">케이지 크기와 원하는 구조물을 적으면 설계를 시작할 수 있어요.</p>
        <Link href="/design" className={`${ui.btnPrimary} mt-5`}>
          첫 설계 만들기
        </Link>
      </div>
    );
  }

  if (items.length === 0) {
    // 주소의 페이지 번호가 전체 페이지 수보다 큰 경우
    return (
      <div className={`${ui.card} text-center`}>
        <p className="font-medium">이 페이지에는 설계가 없어요.</p>
        <Link href={pageHref(1)} className={`${ui.btnSecondary} mt-4`}>
          첫 페이지로
        </Link>
      </div>
    );
  }

  return (
    <div>
      <p className={`${ui.muted} mb-3`}>총 {total}개</p>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((d) => (
          <DesignCard key={d.id} design={d} onDeleted={() => setAttempt((n) => n + 1)} />
        ))}
      </ul>
      {total > page_size && <Pagination page={page} totalPages={totalPages} hrefFor={pageHref} />}
    </div>
  );
}
