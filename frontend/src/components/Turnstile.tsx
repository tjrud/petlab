"use client";

import { useEffect, useEffectEvent, useImperativeHandle, useRef, useState } from "react";

// Cloudflare Turnstile (회원가입 보안 확인). 스크립트는 처음 쓸 때 한 번만 불러온다.
// 토큰은 한 번만 쓸 수 있으므로, 서버가 요청을 거절하면 부모가 reset() 으로 새로 풀게 한다.

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type RenderOptions = {
  sitekey: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
  language: string;
};

type TurnstileApi = {
  render: (el: HTMLElement, options: RenderOptions) => string;
  reset: (widgetId?: string) => void;
  remove: (widgetId?: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!loading) {
    loading = new Promise<TurnstileApi>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile 없음")));
      script.onerror = () => {
        script.remove();
        reject(new Error("turnstile 스크립트를 불러오지 못함"));
      };
      document.head.appendChild(script);
    }).catch((e: unknown) => {
      loading = null; // 다음에 다시 시도할 수 있게
      throw e;
    });
  }
  return loading;
}

export type TurnstileHandle = {
  /** 위젯을 처음 상태로 되돌린다 (토큰은 부모가 비운다) */
  reset: () => void;
};

/** 보안 확인 위젯. 풀면 onToken(토큰), 만료·오류면 onToken(null) */
export default function Turnstile({
  siteKey,
  onToken,
  ref,
}: {
  siteKey: string;
  onToken: (token: string | null) => void;
  ref?: React.Ref<TurnstileHandle>;
}) {
  const box = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const emit = useEffectEvent((token: string | null) => onToken(token));

  useImperativeHandle(ref, () => ({
    reset: () => {
      if (widgetId.current !== null) window.turnstile?.reset(widgetId.current);
    },
  }));

  useEffect(() => {
    let cancelled = false;
    loadTurnstile().then(
      (turnstile) => {
        if (cancelled || !box.current) return;
        widgetId.current = turnstile.render(box.current, {
          sitekey: siteKey,
          language: "ko",
          callback: (token) => emit(token),
          "expired-callback": () => emit(null),
          "error-callback": () => emit(null),
        });
      },
      () => {
        if (!cancelled) setFailed(true);
      },
    );
    return () => {
      cancelled = true;
      // 화면이 숨겨지거나 사라지면 위젯을 지운다 (다시 보일 때 새로 그리므로 이전 토큰도 비운다)
      if (widgetId.current !== null) {
        window.turnstile?.remove(widgetId.current);
        widgetId.current = null;
      }
      emit(null);
    };
  }, [siteKey, attempt]);

  return (
    <div>
      <div ref={box} />
      {failed && (
        <p role="alert" className="mt-1 text-sm text-red-700">
          보안 확인을 불러오지 못했어요.{" "}
          <button
            type="button"
            className="font-semibold underline underline-offset-2"
            onClick={() => {
              setFailed(false);
              setAttempt((n) => n + 1);
            }}
          >
            다시 불러오기
          </button>
        </p>
      )}
    </div>
  );
}
