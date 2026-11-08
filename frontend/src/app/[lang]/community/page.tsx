import type { Metadata } from "next";
import { Suspense } from "react";

import PostList, { PostListPlaceholder } from "@/components/community/PostList";
import WriteButton from "@/components/community/WriteButton";
import Header from "@/components/Header";
import { ui } from "@/lib/ui";

export const metadata: Metadata = { title: "커뮤니티" };

export default function CommunityPage() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <h1 className={ui.h1}>커뮤니티</h1>
              <p className={`${ui.muted} mt-1`}>설계와 사육 정보를 올리고 보는 곳이에요.</p>
            </div>
            <WriteButton />
          </div>
          <Suspense fallback={<PostListPlaceholder />}>
            <PostList />
          </Suspense>
        </div>
      </main>
    </>
  );
}
