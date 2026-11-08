"use client";

import { Link } from "@/i18n/client";
import { useEffect, useState } from "react";

import { ApiError, errorText } from "@/lib/api";
import { ui } from "@/lib/ui";

export type Loaded<T> =
  | { kind: "loading" }
  | { kind: "ok"; data: T }
  | { kind: "error"; message: string; needsLogin: boolean };

/**
 * 메인 화면 각 영역의 데이터를 따로 불러온다 (한 영역이 실패해도 나머지는 그대로 보인다).
 * `load` 는 렌더마다 새로 만들지 않도록 모듈 최상단에 정의한 함수를 넘긴다.
 */
export function useLoad<T>(load: () => Promise<T>, fallbackMessage: string) {
  const [state, setState] = useState<Loaded<T>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    load().then(
      (data) => {
        if (alive) setState({ kind: "ok", data });
      },
      (e: unknown) => {
        if (!alive) return;
        setState({
          kind: "error",
          message: errorText(e, fallbackMessage),
          needsLogin: e instanceof ApiError && e.code === "auth_required",
        });
      },
    );
    return () => {
      alive = false;
    };
  }, [load, fallbackMessage, attempt]);

  const retry = () => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  };
  return { state, retry };
}

/** 불러오는 동안 보여 주는 자리 표시 (화면 낭독기에는 안내 문구만 읽힌다) */
export function Skeleton({ rows, label, rowClassName = "h-16" }: { rows: number; label: string; rowClassName?: string }) {
  return (
    <div role="status">
      <span className="sr-only">{label}</span>
      <ul aria-hidden className="space-y-2">
        {Array.from({ length: rows }, (_, i) => (
          <li key={i} className={`animate-pulse rounded-xl bg-stone-100 ${rowClassName}`} />
        ))}
      </ul>
    </div>
  );
}

/** 영역 하나를 불러오지 못했을 때 (다시 시도하거나, 로그인이 풀렸으면 다시 로그인) */
export function LoadError({
  message,
  needsLogin,
  onRetry,
}: {
  message: string;
  needsLogin: boolean;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className={`${ui.error} flex flex-wrap items-center justify-between gap-2`}>
      <span>{message}</span>
      {needsLogin ? (
        <Link href="/login" className="font-semibold underline underline-offset-2">
          다시 로그인하기
        </Link>
      ) : (
        <button type="button" onClick={onRetry} className="font-semibold underline underline-offset-2">
          다시 불러오기
        </button>
      )}
    </div>
  );
}
