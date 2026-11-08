"use client";

import { Link } from "@/i18n/client";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { EmailUnverifiedNotice, useEmailBlocked } from "@/components/EmailVerification";
import { api, ApiError, isEmailUnverified } from "@/lib/api";

export default function WaitlistForm() {
  const params = useSearchParams();
  const designId = params.get("design") ?? undefined;
  const versionParam = params.get("version");
  const version = versionParam ? Number(versionParam) : undefined;

  const [email, setEmail] = useState("");
  const [agree, setAgree] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { emailUnverified } = useAuth();
  /** 서버가 이메일 인증 전이라고 거절했다 */
  const [emailBlocked, setEmailBlocked] = useEmailBlocked();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setEmailBlocked(false);
    if (!agree) {
      setError("알림 수신에 동의해 주세요.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await api.joinWaitlist(email.trim(), designId, version);
      setDone(r.message_ko);
    } catch (err) {
      if (isEmailUnverified(err)) {
        setEmailBlocked(true);
        return;
      }
      setError(err instanceof ApiError ? (err.status === 422 ? "이메일 주소를 확인해 주세요." : err.messageKo) : "등록하지 못했어요.");
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center" role="status">
        <h2 className="mt-2 text-xl font-bold">대기 등록 완료</h2>
        <p className="mt-2 text-stone-700">{done}</p>
        {designId && (
          <Link href={`/designs/${designId}`} className="mt-4 inline-block text-amber-700 underline">
            설계로 돌아가기
          </Link>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-amber-200 bg-white p-6">
      <p className="text-stone-700">
        출력·배송 서비스는 준비 중이에요. 이메일을 남기면 서비스가 열릴 때 알림 메일을 보내요.
        {designId && <span className="block text-sm text-stone-500">선택한 설계: {designId.slice(0, 8)}{version ? ` · v${version}` : ""}</span>}
      </p>
      <label className="block">
        <span className="mb-1 block text-sm font-medium">이메일</span>
        <input
          type="email"
          required
          autoComplete="email"
          className="w-full rounded-lg border border-stone-300 px-3 py-2"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1" />
        <span>서비스 오픈 알림을 받기 위해 이메일 주소를 수집·이용하는 데 동의합니다.</span>
      </label>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {(emailUnverified || emailBlocked) && <EmailUnverifiedNotice action="제작·배송 신청을 할" />}
      <button
        type="submit"
        disabled={submitting || emailUnverified}
        className="w-full rounded-xl bg-amber-500 px-6 py-3 font-semibold text-white hover:bg-amber-600 disabled:bg-amber-300"
      >
        {submitting ? "등록 중…" : "대기 명단에 등록하기"}
      </button>
    </form>
  );
}
