import { ui } from "@/lib/ui";

/** 불러오지 못했을 때의 안내와 "다시 시도" 버튼 (글 목록·글·설계 내역·이메일 인증) */
export default function RetryAlert({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className={`${ui.error} flex flex-wrap items-center justify-between gap-3`}>
      <span>{message}</span>
      <button type="button" className={ui.btnSecondary} onClick={onRetry}>
        다시 시도
      </button>
    </div>
  );
}
