import type { Metadata } from "next";
import { Suspense } from "react";

import PostDetail, { PostPlaceholder } from "@/components/community/PostDetail";
import Header from "@/components/Header";
import { getT } from "@/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t("커뮤니티 글") };
}

export default function CommunityPostPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <Suspense fallback={<PostPlaceholder />}>{params.then(({ id }) => <PostDetail id={id} />)}</Suspense>
      </main>
    </>
  );
}
