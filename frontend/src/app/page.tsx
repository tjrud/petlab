import Header from "@/components/Header";
import Hero from "@/components/home/Hero";
import HowItWorks from "@/components/home/HowItWorks";
import MemberArea from "@/components/home/MemberArea";
import RecentPosts from "@/components/home/RecentPosts";
import SectionCards from "@/components/home/SectionCards";

// 메인 화면: 소개·이용 순서·메뉴 안내는 서버에서 그리고, 로그인 상태에 따른 영역과 최근 글은 브라우저에서 불러온다
export default function Home() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        <Hero />
        <HowItWorks />
        <SectionCards />
        <MemberArea />
        <RecentPosts />
      </main>
    </>
  );
}
