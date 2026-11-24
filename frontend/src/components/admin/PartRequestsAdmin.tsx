"use client";

import { useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useId, useMemo, useState } from "react";

import LoginRequired, { AuthChecking } from "@/components/LoginRequired";
import Pagination from "@/components/Pagination";
import RetryAlert from "@/components/RetryAlert";
import { useAuth } from "@/components/AuthProvider";
import { Link, useRouter, useT } from "@/i18n/client";
import type { TFunction } from "@/i18n/translate";
import { api, ApiError, errorText, isAuthError } from "@/lib/api";
import type {
  Paged,
  PartRequest,
  PartRequestDetail,
  PartRequestPatch,
  PartRequestSort,
  PartRequestStatus,
} from "@/lib/types";
import { formatDate, formatDateTime, ui } from "@/lib/ui";

// 관리자 화면: 부품 요청 (해석기가 카탈로그에 없다고 한 부품의 수요, backend app/api/admin.py).
// 상태·정렬·검색어·페이지는 주소에 남긴다 (?status=planned&sort=recent&q=쳇바퀴&page=2).

const BASE = "/admin/part-requests";
const PAGE_SIZE = 20;
const MAX_PAGE = 10_000; // 백엔드 허용 범위

type Filter = PartRequestStatus | "all";
const FILTERS: Filter[] = ["open", "planned", "published", "rejected", "merged", "all"];
const SORTS: PartRequestSort[] = ["users", "count", "recent"];
/** 관리자가 고를 수 있는 상태 (merged 는 '다른 요청에 합치기'로만) */
const EDITABLE: Exclude<PartRequestStatus, "merged">[] = ["open", "planned", "published", "rejected"];

function statusLabel(t: TFunction, s: Filter): string {
  switch (s) {
    case "open":
      return t("새 요청");
    case "planned":
      return t("만들 예정");
    case "published":
      return t("부품 공개");
    case "rejected":
      return t("만들지 않음");
    case "merged":
      return t("합친 요청");
    default:
      return t("전체");
  }
}

function sortLabel(t: TFunction, s: PartRequestSort): string {
  return s === "users" ? t("회원 많은 순") : s === "count" ? t("설계 많은 순") : t("최근 순");
}

const STATUS_BADGE: Record<PartRequestStatus, string> = {
  open: "bg-amber-100 text-amber-900",
  planned: "bg-sky-100 text-sky-900",
  published: "bg-emerald-100 text-emerald-900",
  rejected: "bg-stone-200 text-stone-700",
  merged: "bg-stone-100 text-stone-500",
};

type Query = { status: Filter; sort: PartRequestSort; q: string; page: number };

function parseQuery(params: URLSearchParams): Query {
  const status = params.get("status");
  const sort = params.get("sort");
  const n = Number(params.get("page"));
  return {
    status: FILTERS.includes(status as Filter) ? (status as Filter) : "open",
    sort: SORTS.includes(sort as PartRequestSort) ? (sort as PartRequestSort) : "users",
    q: (params.get("q") ?? "").trim().slice(0, 80),
    page: Number.isInteger(n) && n >= 1 && n <= MAX_PAGE ? n : 1,
  };
}

/** 기본값(open·users·1쪽)은 주소에서 뺀다 */
function hrefFor(q: Query): string {
  const sp = new URLSearchParams();
  if (q.status !== "open") sp.set("status", q.status);
  if (q.sort !== "users") sp.set("sort", q.sort);
  if (q.q) sp.set("q", q.q);
  if (q.page > 1) sp.set("page", String(q.page));
  const s = sp.toString();
  return s ? `${BASE}?${s}` : BASE;
}

/** 종/크기 열쇠("hamster/dwarf") → 화면 이름 ("햄스터 드워프"). 종 목록을 받기 전이나 모르는 열쇠는 그대로 */
function useSpeciesLabels(): (key: string) => string {
  const [names, setNames] = useState<Map<string, string>>(new Map());
  useEffect(() => {
    let alive = true;
    api.species().then(
      (r) => {
        if (!alive) return;
        const m = new Map<string, string>();
        for (const sp of r.species)
          for (const sz of sp.sizes) {
            // 크기 이름에 종 이름이 이미 들어 있으면("Golden (Syrian) hamster") 한 번만 쓴다
            const dup = sz.display_name.toLowerCase().includes(sp.display_name.toLowerCase());
            m.set(`${sp.key}/${sz.key}`, dup ? sz.display_name : `${sp.display_name} ${sz.display_name}`);
          }
        setNames(m);
      },
      () => {
        /* 열쇠 그대로 보인다 */
      },
    );
    return () => {
      alive = false;
    };
  }, []);
  return (key: string) => names.get(key) ?? key;
}

export function PartRequestsPlaceholder() {
  const t = useT();
  return (
    <div className={ui.card}>
      <p role="status" className={ui.muted}>
        {t("부품 요청을 불러오는 중…")}
      </p>
    </div>
  );
}

/** 관리자가 아니면 안내만 보인다 (API 도 403 으로 막는다) */
function Forbidden() {
  const t = useT();
  return (
    <p role="alert" className={ui.error}>
      {t("관리자만 쓸 수 있어요.")}
    </p>
  );
}

export default function PartRequestsAdmin() {
  const { status, user } = useAuth();
  if (!status) return <AuthChecking />;
  if (!status.auth_enabled) return <LoginRequired unavailable />;
  if (!user) return <LoginRequired message="관리자로 로그인해 주세요" description="부품 요청은 관리자만 볼 수 있어요." />;
  if (user.role !== "admin") return <Forbidden />;
  return <PartRequestsList userId={user.id} />;
}

type Result =
  | { key: string; kind: "ok"; data: Paged<PartRequest> }
  | { key: string; kind: "error"; message: string; status: number; authCode: string | null };

function PartRequestsList({ userId }: { userId: string }) {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const query = useMemo(() => parseQuery(new URLSearchParams(params.toString())), [params]);
  const speciesLabel = useSpeciesLabels();

  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [search, setSearch] = useState(query.q);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const key = `${userId}|${hrefFor(query)}|${attempt}`;
  const uid = useId();

  // 주소의 검색어가 바뀌면(뒤로 가기 등) 입력칸도 맞춘다
  const [shownQ, setShownQ] = useState(query.q);
  if (shownQ !== query.q) {
    setShownQ(query.q);
    setSearch(query.q);
  }

  useEffect(() => {
    let alive = true;
    api
      .adminPartRequests({ status: query.status, sort: query.sort, q: query.q, page: query.page, pageSize: PAGE_SIZE })
      .then(
        (data) => {
          if (alive) setResult({ key, kind: "ok", data });
        },
        (e: unknown) => {
          if (!alive) return;
          setResult({
            key,
            kind: "error",
            message: errorText(e, t("부품 요청을 불러오지 못했어요.")),
            status: e instanceof ApiError ? e.status : 0,
            authCode: isAuthError(e) ? (e.code ?? null) : null,
          });
        },
      );
    return () => {
      alive = false;
    };
  }, [key, query, t]);

  const go = (q: Partial<Query>) => {
    setOpen(null);
    router.replace(hrefFor({ ...query, page: 1, ...q }));
  };

  function onSearch(e: FormEvent) {
    e.preventDefault();
    go({ q: search.trim().slice(0, 80) });
  }

  async function onExport() {
    setExporting(true);
    setExportError(null);
    try {
      const data = await api.exportPartRequests();
      const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `part-requests-${data.exported_at.slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setExportError(errorText(e, t("내보내지 못했어요. 잠시 뒤 다시 시도해 주세요.")));
    } finally {
      setExporting(false);
    }
  }

  const replaceRow = (row: PartRequest) =>
    setResult((r) =>
      r && r.kind === "ok"
        ? { ...r, data: { ...r.data, items: r.data.items.map((x) => (x.id === row.id ? row : x)) } }
        : r,
    );

  const r = result?.key === key ? result : null;
  let body: React.ReactNode;
  if (!r) {
    body = <PartRequestsPlaceholder />;
  } else if (r.kind === "error") {
    if (r.authCode) body = <LoginRequired message="관리자로 로그인해 주세요" unavailable={r.authCode === "auth_unavailable"} />;
    else if (r.status === 403) body = <Forbidden />;
    else body = <RetryAlert message={r.message} onRetry={() => setAttempt((n) => n + 1)} />;
  } else if (r.data.items.length === 0) {
    body = (
      <div className={`${ui.card} text-center`}>
        <p className="font-medium">
          {query.q ? t("찾는 이름의 부품 요청이 없어요.") : r.data.total > 0 ? t("이 페이지에는 부품 요청이 없어요.") : t("이 상태의 부품 요청이 없어요.")}
        </p>
        {r.data.total > 0 && (
          <Link href={hrefFor({ ...query, page: 1 })} className={`${ui.btnSecondary} mt-4`}>
            {t("첫 페이지로")}
          </Link>
        )}
      </div>
    );
  } else {
    const { items, total, page_size } = r.data;
    const totalPages = Math.max(1, Math.ceil(total / page_size));
    body = (
      <>
        <p className={`${ui.muted} mb-3`}>{t("총 {n}개", { n: total })}</p>
        {/* relative: 표 안의 sr-only(absolute) 글자가 스크롤 칸 밖으로 나가 화면이 가로로 넘치지 않게 */}
        <div className="relative overflow-x-auto rounded-2xl border border-stone-200 bg-white">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="border-b border-stone-200 bg-stone-50 text-xs text-stone-500">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">{t("부품")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("회원 / 설계")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("종·크기")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("쓰임새")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("최근 예시")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("처음 / 최근")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("상태")}</th>
                <th scope="col" className="px-3 py-2 font-medium">
                  <span className="sr-only">{t("관리")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <RequestRows
                  key={row.id}
                  row={row}
                  expanded={open === row.id}
                  onToggle={() => setOpen((o) => (o === row.id ? null : row.id))}
                  speciesLabel={speciesLabel}
                  mergeTargets={items.filter((x) => x.id !== row.id && x.status !== "merged")}
                  onUpdated={replaceRow}
                  onMerged={() => {
                    setOpen(null);
                    setAttempt((n) => n + 1);
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <Pagination page={query.page} totalPages={totalPages} hrefFor={(p) => hrefFor({ ...query, page: p })} />
        )}
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav aria-label={t("요청 상태")} className="flex flex-wrap gap-1">
          {FILTERS.map((s) => (
            <Link
              key={s}
              href={hrefFor({ ...query, status: s, page: 1 })}
              aria-current={query.status === s ? "page" : undefined}
              onClick={() => setOpen(null)}
              className={`rounded-lg px-3 py-1.5 text-sm ${
                query.status === s ? "bg-stone-800 font-medium text-white" : "text-stone-600 hover:bg-stone-100"
              }`}
            >
              {statusLabel(t, s)}
            </Link>
          ))}
        </nav>
        <div className="flex flex-col items-end gap-1">
          <button type="button" onClick={onExport} disabled={exporting} className={ui.btnSecondary}>
            {exporting ? t("내보내는 중…") : t("JSON 내보내기")}
          </button>
          {exportError && (
            <p role="alert" className="text-xs text-red-700">
              {exportError}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 items-end gap-2" role="search">
          <div className="min-w-0 flex-1 sm:max-w-xs">
            <label htmlFor={`${uid}-q`} className={ui.label}>
              {t("이름으로 찾기")}
            </label>
            <input
              id={`${uid}-q`}
              type="search"
              value={search}
              maxLength={80}
              onChange={(e) => setSearch(e.target.value)}
              className={ui.input}
            />
          </div>
          <button type="submit" className={ui.btnSecondary}>
            {t("찾기")}
          </button>
        </form>
        <div>
          <label htmlFor={`${uid}-sort`} className={ui.label}>
            {t("정렬")}
          </label>
          <select
            id={`${uid}-sort`}
            value={query.sort}
            onChange={(e) => go({ sort: e.target.value as PartRequestSort })}
            className={`${ui.input} w-auto`}
          >
            {SORTS.map((s) => (
              <option key={s} value={s}>
                {sortLabel(t, s)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {body}

      <p className="text-xs text-stone-500">
        {t("회원 정보는 보이지 않고, 예시는 연락처를 지운 요청 앞부분만 보여요. 설계를 지워도 부품 요청 기록은 남아요.")}
      </p>
    </div>
  );
}

/** 목록의 한 줄과, 펼치면 아래에 붙는 자세히·관리 칸 */
function RequestRows({
  row,
  expanded,
  onToggle,
  speciesLabel,
  mergeTargets,
  onUpdated,
  onMerged,
}: {
  row: PartRequest;
  expanded: boolean;
  onToggle: () => void;
  speciesLabel: (key: string) => string;
  mergeTargets: PartRequest[];
  onUpdated: (row: PartRequest) => void;
  onMerged: () => void;
}) {
  const t = useT();
  const species = Object.entries(row.species_counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const panelId = `part-request-${row.id}`;
  return (
    <>
      <tr className="border-b border-stone-100 align-top last:border-b-0">
        <th scope="row" className="px-3 py-3 font-medium">
          <span className="block">{row.name_ko}</span>
          {row.name_key !== row.name_ko && <span className="block text-xs font-normal text-stone-400">{row.name_key}</span>}
          {row.fulfilled_by.length > 0 && (
            <span className={`${ui.badge} mt-1 inline-block bg-emerald-100 text-emerald-900`}>
              {t("이미 있는 부품: {keys}", { keys: row.fulfilled_by.join(", ") })}
            </span>
          )}
        </th>
        <td className="whitespace-nowrap px-3 py-3 tabular-nums">
          {row.user_count} / {row.request_count}
        </td>
        <td className="px-3 py-3">
          <ul className="flex flex-wrap gap-1">
            {species.map(([k, n]) => (
              <li key={k} className="whitespace-nowrap rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-700">
                {speciesLabel(k)} {n}
              </li>
            ))}
          </ul>
        </td>
        <td className="px-3 py-3 text-stone-700">
          {row.purposes.length > 0 ? row.purposes.join(", ") : <span className="text-stone-400">—</span>}
        </td>
        <td className="max-w-xs px-3 py-3">
          {row.examples.length > 0 ? (
            <ul className="space-y-1 text-xs text-stone-600">
              {row.examples.map((ex, i) => (
                <li key={i} className="break-words">
                  {ex.lang !== "ko" && <span className="mr-1 rounded bg-stone-100 px-1 uppercase text-stone-500">{ex.lang}</span>}
                  {ex.excerpt}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-stone-400">—</span>
          )}
        </td>
        <td className="whitespace-nowrap px-3 py-3 text-xs text-stone-600">
          {formatDate(row.first_seen_at)}
          <br />
          {formatDate(row.last_seen_at)}
        </td>
        <td className="px-3 py-3">
          <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[row.status]}`}>
            {statusLabel(t, row.status)}
          </span>
          {row.published_key && <span className="mt-1 block text-xs text-stone-500">{row.published_key}</span>}
          {row.note && <span className="mt-1 block max-w-[12rem] break-words text-xs text-stone-500">{row.note}</span>}
        </td>
        <td className="px-3 py-3 text-right">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-controls={panelId}
            aria-label={t("{name} 자세히·관리", { name: row.name_ko })}
            className="whitespace-nowrap rounded-lg border border-stone-300 px-2.5 py-1 text-xs hover:bg-stone-50"
          >
            {expanded ? t("접기") : t("관리")}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr id={panelId} className="border-b border-stone-100 bg-stone-50/60">
          <td colSpan={8} className="px-3 py-4">
            <RequestPanel
              row={row}
              speciesLabel={speciesLabel}
              mergeTargets={mergeTargets}
              onUpdated={onUpdated}
              onMerged={onMerged}
            />
          </td>
        </tr>
      )}
    </>
  );
}

type DetailState = { id: string; attempt: number } & (
  | { kind: "ok"; data: PartRequestDetail }
  | { kind: "error"; message: string }
);

/** 펼친 칸: 최근 설계 20개(자세히 보기 API), 상태·부품 키·메모 저장, 다른 요청에 합치기, 예시 지우기 */
function RequestPanel({
  row,
  speciesLabel,
  mergeTargets,
  onUpdated,
  onMerged,
}: {
  row: PartRequest;
  speciesLabel: (key: string) => string;
  mergeTargets: PartRequest[];
  onUpdated: (row: PartRequest) => void;
  onMerged: () => void;
}) {
  const t = useT();
  const merged = row.status === "merged";
  const [status, setStatus] = useState<PartRequestStatus>(row.status);
  const [publishedKey, setPublishedKey] = useState(row.published_key ?? "");
  const [note, setNote] = useState(row.note ?? "");
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const uid = useId();

  const [detailAttempt, setDetailAttempt] = useState(0);
  const [detail, setDetail] = useState<DetailState | null>(null);
  useEffect(() => {
    let alive = true;
    api.adminPartRequest(row.id).then(
      (data) => {
        if (alive) setDetail({ id: row.id, attempt: detailAttempt, kind: "ok", data });
      },
      (e: unknown) => {
        if (alive)
          setDetail({
            id: row.id,
            attempt: detailAttempt,
            kind: "error",
            message: errorText(e, t("최근 설계를 불러오지 못했어요.")),
          });
      },
    );
    return () => {
      alive = false;
    };
  }, [row.id, detailAttempt, t]);
  const d = detail && detail.id === row.id && detail.attempt === detailAttempt ? detail : null;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      await action();
    } catch (e) {
      setError(errorText(e, t("저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.")));
    } finally {
      setBusy(false);
    }
  }

  function onSave(e: FormEvent) {
    e.preventDefault();
    const body: PartRequestPatch = {};
    if (!merged && status !== row.status && status !== "merged") body.status = status;
    const key = publishedKey.trim() || null;
    if (!merged && key !== row.published_key) body.published_key = key;
    const text = note.trim() || null;
    if (text !== row.note) body.note = text;
    if (Object.keys(body).length === 0) {
      setError(null);
      setSaved(t("바뀐 내용이 없어요."));
      return;
    }
    void run(async () => {
      const updated = await api.updatePartRequest(row.id, body);
      onUpdated(updated);
      setStatus(updated.status);
      setPublishedKey(updated.published_key ?? "");
      setNote(updated.note ?? "");
      setSaved(t("저장했어요."));
    });
  }

  function onMerge() {
    const to = mergeTargets.find((x) => x.id === target);
    if (!to) return;
    if (!window.confirm(t('"{name}" 요청을 "{target}" 요청에 합칠까요? 되돌릴 수 없어요.', { name: row.name_ko, target: to.name_ko })))
      return;
    void run(async () => {
      await api.updatePartRequest(row.id, { merged_into: to.id });
      onMerged();
    });
  }

  function onClearExamples() {
    if (!window.confirm(t("이 요청의 예시 글을 모두 지울까요? 되돌릴 수 없어요."))) return;
    void run(async () => {
      const updated = await api.updatePartRequest(row.id, { clear_examples: true });
      onUpdated(updated);
      setDetailAttempt((n) => n + 1);
      setSaved(t("예시 글을 지웠어요."));
    });
  }

  const showKey = status === "published" || publishedKey !== "" || row.published_key !== null;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section aria-label={t("최근 설계")} className="min-w-0">
        <h3 className="mb-2 text-sm font-semibold">{t("최근 설계")}</h3>
        {!d ? (
          <p className={ui.muted}>{t("불러오는 중…")}</p>
        ) : d.kind === "error" ? (
          <RetryAlert message={d.message} onRetry={() => setDetailAttempt((n) => n + 1)} />
        ) : d.data.hits.length === 0 ? (
          <p className={ui.muted}>{t("기록된 설계가 없어요.")}</p>
        ) : (
          <ul className="space-y-2">
            {d.data.hits.map((h, i) => (
              <li key={i} className="rounded-lg border border-stone-200 bg-white p-2 text-xs">
                <p className="text-stone-500">
                  {formatDateTime(h.at)} · {speciesLabel(`${h.species}/${h.size}`)}
                  {h.lang !== "ko" && ` · ${h.lang.toUpperCase()}`}
                  {h.purpose_ko && ` · ${h.purpose_ko}`}
                </p>
                {h.excerpt ? (
                  <p className="mt-1 break-words text-stone-800">{h.excerpt}</p>
                ) : (
                  <p className="mt-1 text-stone-400">{t("(예시 글을 지웠어요)")}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="min-w-0 space-y-5">
        <form onSubmit={onSave} className="space-y-3">
          {merged ? (
            <p className="text-sm text-stone-600">{t("다른 요청에 합친 요청이에요. 메모만 고칠 수 있어요.")}</p>
          ) : (
            <div>
              <label htmlFor={`${uid}-status`} className={ui.label}>
                {t("상태")}
              </label>
              <select
                id={`${uid}-status`}
                value={status}
                onChange={(e) => setStatus(e.target.value as PartRequestStatus)}
                className={ui.input}
              >
                {EDITABLE.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(t, s)}
                  </option>
                ))}
              </select>
            </div>
          )}
          {!merged && showKey && (
            <div>
              <label htmlFor={`${uid}-key`} className={ui.label}>
                {t("부품 키")}
              </label>
              <input
                id={`${uid}-key`}
                aria-describedby={`${uid}-key-hint`}
                value={publishedKey}
                onChange={(e) => setPublishedKey(e.target.value)}
                placeholder="family@v1"
                maxLength={64}
                className={ui.input}
              />
              <p id={`${uid}-key-hint`} className="mt-1 text-xs text-stone-500">
                {t("부품 공개로 바꾸려면 부품 라이브러리에 있는 부품 키를 적어 주세요.")}
              </p>
            </div>
          )}
          <div>
            <label htmlFor={`${uid}-note`} className={ui.label}>
              {t("관리 메모")}
            </label>
            <textarea
              id={`${uid}-note`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              rows={2}
              className={ui.input}
            />
          </div>
          <button type="submit" disabled={busy} className={ui.btnPrimary}>
            {busy ? t("저장 중…") : t("저장")}
          </button>
        </form>

        {!merged && (
          <div className="space-y-2 border-t border-stone-200 pt-4">
            <label htmlFor={`${uid}-merge`} className={ui.label}>
              {t("다른 요청에 합치기")}
            </label>
            <p id={`${uid}-merge-hint`} className="text-xs text-stone-500">
              {t("같은 부품을 다른 이름으로 적은 요청이면 합쳐요. 횟수와 예시가 고른 요청으로 옮겨 가요. 이 페이지의 요청에서 고를 수 있어요.")}
            </p>
            <select
              id={`${uid}-merge`}
              aria-describedby={`${uid}-merge-hint`}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className={ui.input}
            >
              <option value="">{t("합칠 요청 고르기")}</option>
              {mergeTargets.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name_ko} ({x.user_count} / {x.request_count})
                </option>
              ))}
            </select>
            <button type="button" onClick={onMerge} disabled={busy || !target} className={ui.btnSecondary}>
              {t("합치기")}
            </button>
          </div>
        )}

        <div className="border-t border-stone-200 pt-4">
          <button type="button" onClick={onClearExamples} disabled={busy} className={ui.btnDanger}>
            {t("예시 지우기")}
          </button>
        </div>

        {error && (
          <p role="alert" className={ui.error}>
            {error}
          </p>
        )}
        {saved && (
          <p role="status" className={ui.success}>
            {saved}
          </p>
        )}
      </div>
    </div>
  );
}
