"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import LoginRequired from "@/components/LoginRequired";
import { api, ApiError, errorText, isAuthError } from "@/lib/api";
import type { Me, Pet, SpeciesOption } from "@/lib/types";
import { ui } from "@/lib/ui";

import EmailForm from "./EmailForm";
import NicknameForm from "./NicknameForm";
import PasswordForm from "./PasswordForm";
import PetSection from "./PetSection";
import ProfileCard from "./ProfileCard";

/** 내 정보: 프로필·활동 요약·설계 사용량, 내 반려동물, 계정 설정 (회원 전용) */
export default function MyInfo() {
  const { status, user } = useAuth();
  const userId = user?.id ?? null;
  const [authError, setAuthError] = useState<ApiError | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [pets, setPets] = useState<Pet[] | null>(null);
  const [petsError, setPetsError] = useState<string | null>(null);
  const [species, setSpecies] = useState<SpeciesOption[] | null>(null);
  const [speciesError, setSpeciesError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    const fail = (setErr: (m: string) => void, fallback: string) => (e: unknown) => {
      if (!alive) return;
      if (isAuthError(e)) setAuthError(e); // 사용 중 세션이 만료된 경우
      else setErr(errorText(e, fallback));
    };
    api
      .me()
      .then((m) => {
        if (!alive) return;
        setMe(m);
        setMeError(null);
      })
      .catch(fail(setMeError, "내 정보를 불러오지 못했어요."));
    api
      .pets()
      .then((p) => {
        if (!alive) return;
        setPets(p);
        setPetsError(null);
      })
      .catch(fail(setPetsError, "반려동물 정보를 불러오지 못했어요."));
    api
      .species()
      .then((s) => {
        if (!alive) return;
        setSpecies(s.species);
        setSpeciesError(null);
      })
      .catch((e: unknown) => alive && setSpeciesError(errorText(e, "잠시 뒤 다시 시도해 주세요.")));
    return () => {
      alive = false;
    };
  }, [userId]);

  // /me#pets·/me#email 로 들어온 경우: 내용을 불러온 뒤에 그 영역으로 스크롤한다 (처음에는 그 영역이 아직 없다)
  const ready = (me !== null || meError !== null) && (pets !== null || petsError !== null);
  useEffect(() => {
    const hash = window.location.hash;
    if (ready && (hash === "#pets" || hash === "#email")) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [ready]);

  const onAuthError = (e: ApiError) => setAuthError(e);

  if (authError) {
    return (
      <LoginRequired unavailable={authError.code === "auth_unavailable"} message="로그인하고 내 정보를 관리해 보세요" />
    );
  }
  if (!status) {
    return (
      <div className={ui.card}>
        <p role="status" className={ui.muted}>
          잠시만 기다려 주세요…
        </p>
      </div>
    );
  }
  if (!user) return <LoginRequired message="로그인하고 내 정보를 관리해 보세요" />;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:grid-rows-[auto_1fr] lg:items-start">
      <div className="lg:col-start-1 lg:row-start-1">
        <ProfileCard user={user} me={me} meError={meError} petCount={pets?.length ?? null} />
      </div>

      <div className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
        <PetSection
          pets={pets}
          petsError={petsError}
          species={species}
          speciesError={speciesError}
          onPetsChange={setPets}
          onAuthError={onAuthError}
        />
      </div>

      <section aria-labelledby="account-title" className={`${ui.card} lg:col-start-1 lg:row-start-2`}>
        <h2 id="account-title" className={ui.h2}>
          계정 설정
        </h2>
        <div className="mt-4 space-y-6 divide-y divide-stone-200 [&>*+*]:pt-6">
          <NicknameForm user={user} onAuthError={onAuthError} />
          <EmailForm user={user} onAuthError={onAuthError} />
          <PasswordForm user={user} onAuthError={onAuthError} />
        </div>
      </section>
    </div>
  );
}
