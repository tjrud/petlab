import type { Metadata } from "next";
import { Suspense } from "react";

import PostDetail, { PostPlaceholder } from "@/components/community/PostDetail";
import Header from "@/components/Header";

export const metadata: Metadata = { title: "커뮤니티 글" };

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
