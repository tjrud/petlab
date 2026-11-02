"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import DesignLoadError from "@/components/designs/DesignLoadError";
import DesignTitleBar, { seesUnsharedVersions } from "@/components/designs/DesignTitleBar";
import DownloadPanel from "@/components/DownloadPanel";
import { useEmailBlocked } from "@/components/EmailVerification";
import ItemList from "@/components/ItemList";
import LoginRequired from "@/components/LoginRequired";
import RevisePanel from "@/components/RevisePanel";
import ValidationPanel from "@/components/ValidationPanel";
import VersionList from "@/components/VersionList";
import { api, ApiError, isAuthError, isEmailUnverified } from "@/lib/api";
import type { Design } from "@/lib/types";
import { ui } from "@/lib/ui";

const CageViewer = dynamic(() => import("@/components/CageViewer"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-stone-500">3D 뷰어 준비 중…</div>,
});

/**
 * 설계 화면. 내 설계는 수정·공유할 수 있고, 남의 설계는 읽기 전용으로 보여 준다
 * (다른 사람에게는 커뮤니티 글에 첨부된 버전만 오고, 관리자도 남의 설계는 고치거나 공유하지 못한다).
 */
export default function DesignView({ id, initialVersion }: { id: string; initialVersion?: number }) {
  const [design, setDesign] = useState<Design | null>(null);
  const [loadError, setLoadError] = useState<{ status: number; message: string } | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<ApiError | null>(null);
  /** 수정 요청이 로그인 문제로 실패했다 (쓴 요청은 지우지 않고 다시 로그인하게 한다) */
  const [reviseNeedsLogin, setReviseNeedsLogin] = useState(false);
  /** 수정 요청을 서버가 이메일 인증 전이라고 거절했다 */
  const [reviseEmailBlocked, setReviseEmailBlocked] = useEmailBlocked();

  useEffect(() => {
    let alive = true;
    api
      .getDesign(id, initialVersion)
      .then((d) => {
        if (alive) setDesign(d);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (isAuthError(e)) setAuthError(e as ApiError);
        else
          setLoadError(
            e instanceof ApiError
              ? { status: e.status, message: e.messageKo }
              : { status: 0, message: "설계를 불러오지 못했어요." },
          );
      });
    return () => {
      alive = false;
    };
  }, [id, initialVersion]);

  async function pickVersion(v: number) {
    setBusy(true);
    setActionError(null);
    try {
      setDesign(await api.getDesign(id, v));
      setSelected(null);
    } catch (e) {
      if (isAuthError(e)) setAuthError(e as ApiError);
      else setActionError(e instanceof ApiError ? e.messageKo : "버전을 불러오지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  async function revise(prompt: string): Promise<boolean> {
    if (!design?.is_owner) return false;
    setBusy(true);
    setActionError(null);
    setReviseEmailBlocked(false);
    try {
      setDesign(await api.reviseDesign(id, prompt, design.current.version));
      setSelected(null);
      setReviseNeedsLogin(false);
      return true;
    } catch (e) {
      // 화면 전체를 로그인 안내로 바꾸지 않는다: 쓰던 수정 요청이 사라지지 않게
      if (isAuthError(e)) setReviseNeedsLogin(true);
      else if (isEmailUnverified(e)) setReviseEmailBlocked(true);
      else setActionError(e instanceof ApiError ? e.messageKo : "수정 중 문제가 생겼어요. 다시 시도해 주세요.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const errorItems = new Set<number>(
    (design?.current.validation.issues ?? [])
      .filter((i) => i.severity === "error" && !i.auto_fixed && i.item_index !== null)
      .map((i) => i.item_index as number),
  );

  if (authError) {
    return (
      <div className="mx-auto max-w-xl">
        <LoginRequired unavailable={authError.code === "auth_unavailable"} />
      </div>
    );
  }
  if (loadError && !design) {
    return <DesignLoadError status={loadError.status} message={loadError.message} />;
  }
  if (!design) {
    return <div className="py-20 text-center text-stone-500">설계를 불러오는 중…</div>;
  }

  const cur = design.current;
  const h = design.habitat;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="min-w-0 space-y-3">
        <DesignTitleBar design={design} />
        <div
          data-testid="viewer"
          className="h-[420px] overflow-hidden rounded-2xl border border-amber-200 bg-white sm:h-[560px]"
        >
          <CageViewer
            cage={h.cage}
            items={cur.items}
            selected={selected}
            errorItems={errorItems}
            onSelect={setSelected}
          />
        </div>
        <p className="text-xs text-stone-500">드래그로 회전, 휠로 확대·축소, 구조물을 누르면 상세 정보를 볼 수 있어요.</p>
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <p className="text-xs font-medium text-stone-500">요청</p>
          <p className="mt-1 whitespace-pre-wrap break-words">{cur.prompt}</p>
          <p className="mt-3 text-xs font-medium text-stone-500">설계 설명</p>
          <p className="mt-1 leading-relaxed">{cur.summary_ko}</p>
          {cur.notes_ko.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm text-stone-600">
              {cur.notes_ko.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <aside className="space-y-6 rounded-2xl border border-stone-200 bg-white p-4">
        <ValidationPanel validation={cur.validation} items={cur.items} onSelect={setSelected} />
        {design.is_owner && (
          <RevisePanel
            baseVersion={cur.version}
            latestVersion={design.versions[design.versions.length - 1].version}
            sharedVersions={design.shared_versions}
            busy={busy}
            error={actionError}
            needsLogin={reviseNeedsLogin}
            emailBlocked={reviseEmailBlocked}
            draftKey={`revise:${design.id}`}
            loginNext={`/designs/${encodeURIComponent(design.id)}`}
            onSubmit={revise}
          />
        )}
        <ItemList items={cur.items} selected={selected} errorItems={errorItems} onSelect={setSelected} />
        <DownloadPanel
          designId={design.id}
          version={cur.version}
          allowed={cur.export_allowed}
          partCount={cur.items.length}
        />
        {!design.is_owner && actionError && (
          <p role="alert" className={ui.error}>
            {actionError}
          </p>
        )}
        {/* 남의 설계에서 고를 버전이 하나뿐이면 목록을 보이지 않는다 (다른 회원에게는 공유된 버전만 온다) */}
        {(design.is_owner || design.versions.length > 1) && (
          <VersionList
            versions={design.versions}
            current={cur.version}
            loading={busy}
            onPick={pickVersion}
            allVersions={design.is_owner || seesUnsharedVersions(design)}
            sharedVersions={design.shared_versions}
          />
        )}
      </aside>
    </div>
  );
}
