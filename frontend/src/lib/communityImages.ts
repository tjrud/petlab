// 커뮤니티 글에 넣을 수 있는 사진 목록 (운영팀 글 수정 화면의 사진 고르기에 보여요).
//
// 파일은 frontend/public/community-images/ 에 함께 배포해요. 외부 사이트 사진을 바로 불러오지 않아요
// (방문자 정보가 외부로 나가지 않게, 원본이 사라져도 글이 깨지지 않게).
// 재사용이 허락된 사진(CC BY·CC BY-SA·CC0·퍼블릭 도메인)만 넣고, 촬영자·라이선스·원본 주소를 꼭 적어요.
// 글에는 이 정보가 그대로 저장되므로, 파일을 바꾸면 새 이름으로 추가하세요.

import type { PostImage } from "@/lib/types";

export type CommunityImage = PostImage & {
  /** 사진 고르기에서 묶어 보여 줄 동물 이름 */
  group: string;
};

export const COMMUNITY_IMAGES: CommunityImage[] = [];
