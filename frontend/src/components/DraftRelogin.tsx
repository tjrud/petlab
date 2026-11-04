"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef } from "react";

import { useAuth } from "@/components/AuthProvider";
import { withNext } from "@/lib/safeNext";
import { ui } from "@/lib/ui";

// 로그인이 풀려 보내지 못한 입력 지키기.
// 폼은 쓰던 내용을 그대로 보여 주고, 내용은 이 탭(sessionStorage)에 맡겨 두었다가
// 같은 회원으로 다시 로그인해 그 화면에 돌아오면 되살린다 (로그인은 전체 새로고침으로 끝나므로).

const PREFIX = "nestforge:draft:";

type Stored = { owner: string; draft: unknown };

function take(key: string): Stored | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (raw === null) return null;
    sessionStorage.removeItem(PREFIX + key);
    return JSON.parse(raw) as Stored;
  } catch {
    return null; // 저장소를 쓸 수 없거나 내용이 깨졌으면 되살리지 않는다
  }
}

/** 맡겨 둔 입력을 버린다 (글을 올렸거나 취소한 경우) */
export function clearDraft(key: string) {
  try {
    sessionStorage.removeItem(PREFIX + key);
  } catch {
    /* 저장소를 쓸 수 없음 */
  }
}

/**
 * - keep 이 true 인 동안(로그인이 필요한 상태) draft 가 바뀔 때마다 맡겨 둔다. draft 가 null 이면(쓴 내용 없음) 맡기지 않는다
 * - 로그인한 상태로 화면이 열리면 맡겨 둔 내용을 한 번 꺼내 restore 로 넘긴다 (다른 회원이 맡긴 것이면 버린다)
 * 비밀번호처럼 남기면 안 되는 값은 넣지 않는다.
 */
export function useDraftBackup<T>(key: string, draft: T | null, keep: boolean, restore: (draft: T) => void) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  // 로그인이 풀린 뒤에도 누구의 입력인지 알 수 있게 마지막으로 로그인했던 회원을 기억한다
  const owner = useRef<string | null>(null);
  useEffect(() => {
    if (userId) owner.current = userId;
  }, [userId]);

  const serialized = draft === null ? null : JSON.stringify(draft);
  useEffect(() => {
    if (!keep || serialized === null || !owner.current) return;
    try {
      sessionStorage.setItem(PREFIX + key, `{"owner":${JSON.stringify(owner.current)},"draft":${serialized}}`);
    } catch {
      /* 저장소를 쓸 수 없으면 화면에 남은 내용만 지킨다 */
    }
  }, [key, serialized, keep]);

  const onRestore = useEffectEvent(restore);
  useEffect(() => {
    if (!userId) return;
    const saved = take(key);
    if (saved && saved.owner === userId) onRestore(saved.draft as T);
  }, [key, userId]);
}

/** 로그인이 풀렸지만 쓰던 내용이 있어 폼을 그대로 둘 때의 안내 (다시 로그인하면 이 화면으로 돌아와 내용을 되살린다) */
export function ReloginNotice({ next, message }: { next: string; message?: string }) {
  return (
    <p role="alert" className={ui.error}>
      {message ?? "로그인이 풀렸어요."} 쓰던 내용은 그대로 두었어요. 다시 로그인하고 돌아오면 이어서 쓸 수 있어요.{" "}
      <Link href={withNext("/login", next)} className="font-semibold underline underline-offset-2">
        다시 로그인하기
      </Link>
    </p>
  );
}
