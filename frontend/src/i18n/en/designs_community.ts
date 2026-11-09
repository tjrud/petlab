// 내 설계 목록·설계 화면 제목줄·커뮤니티(글 목록·글·댓글·글쓰기)의 문구
const en: Record<string, string> = {
  // 내 설계 목록·카드
  "설계 내역을 불러오는 중이에요": "Loading your designs…",
  "설계 내역을 불러오지 못했어요.": "Couldn't load your designs.",
  "아직 만든 설계가 없어요": "No designs yet",
  "케이지 크기와 원하는 구조물을 적으면 설계를 시작할 수 있어요.":
    "Enter your cage size and the structure you want to start designing.",
  "첫 설계 만들기": "Create your first design",
  "이 페이지에는 설계가 없어요.": "There are no designs on this page.",
  "첫 페이지로": "Go to first page",
  "총 {n}개": "{n} total",
  "버전 {n}개": "Versions: {n}",
  "통과": "Passed",
  "검증 실패": "Checks failed",
  "커뮤니티 공유됨": "Shared to Community",
  "제목 없는 설계": "Untitled design",
  "{species} {size} · {n}마리": "{size} {species} × {n}",
  "케이지 {w}×{d}×{h}mm": "Cage {w}×{d}×{h}mm",
  "{date} 수정": "Edited {date}",

  // 설계 지우기
  '"{title}" 설계를 지울까요?': 'Delete the design "{title}"?',
  "버전 {n}개와 3D 파일이 모두 지워지고 되돌릴 수 없어요.":
    "All versions ({n}) and 3D files will be deleted. This can't be undone.",
  "커뮤니티 글에 첨부된 설계는 글에서 빠져요 (글은 남아요).":
    "The design will be removed from any community posts it's attached to (the posts stay).",
  "설계를 지우지 못했어요.": "Couldn't delete the design.",
  "{title} 설계 지우기": "Delete design {title}",
  "지우는 중…": "Deleting…",
  "삭제": "Delete",

  // 설계를 불러오지 못했을 때
  "설계를 불러오는 중…": "Loading design…",
  "로그인하면 내 설계를 볼 수 있어요": "Log in to see your designs",
  "만든 설계는 로그인한 뒤에 다시 열 수 있어요. 회원가입은 무료예요.":
    "Log in to open your designs again. Signing up is free.",
  "설계를 찾을 수 없어요": "Design not found",
  "설계를 불러오지 못했어요": "Couldn't load the design",
  "주소가 잘못되었거나 삭제된 설계예요. 다른 회원의 설계는 커뮤니티 글에 첨부된 버전만 볼 수 있어요.":
    "The address is wrong or the design was deleted. You can only see other members' designs in versions attached to community posts.",
  "내 설계 목록": "My designs",
  "처음으로": "Home",

  // 설계 화면 제목줄
  "회원": "a member",
  "맞춤 설계": "Custom design",
  "커뮤니티에 공유됨": "Shared to Community",
  "개발용 모의 해석기": "Mock interpreter (dev)",
  "커뮤니티에 공유": "Share to Community",
  "{owner}님의 설계예요 (관리자 보기, 읽기 전용).": "This is {owner}'s design (admin view, read-only).",
  "지금 보는 v{v}은 커뮤니티에 공유된 버전이에요.": "The v{v} you're viewing is shared to the Community.",
  "공유되지 않은 버전은 다른 사람에게 보이지 않아요.": "Versions that aren't shared are hidden from others.",
  "{owner}님이 커뮤니티에 공유한 설계예요. 공유된 버전만 볼 수 있고, 읽기 전용이에요.":
    "This design was shared to the Community by {owner}. Only shared versions are visible, and it's read-only.",
  "{owner}님의 설계예요. 읽기 전용이에요.": "This is {owner}'s design. It's read-only.",

  // 커뮤니티 공통
  "관리자": "Admin",
  "입력한 글자 수": "Characters entered",
  "제목을 입력해 주세요.": "Please enter a title.",
  "제목은 {n}자까지 쓸 수 있어요.": "Titles can be up to {n} characters.",
  "내용을 입력해 주세요.": "Please enter some content.",
  "내용은 {n}자까지 쓸 수 있어요.": "Posts can be up to {n} characters.",

  // 글 목록
  "글 목록을 불러오는 중이에요": "Loading posts…",
  "글 목록을 불러오지 못했어요.": "Couldn't load posts.",
  "아직 글이 없어요.": "No posts yet.",
  "케이지 설계나 사육 경험을 올려 주세요.": "Share your cage designs or hamster care experience.",
  "이 페이지에는 글이 없어요.": "There are no posts on this page.",
  "총 {n}개의 글": "Posts: {n}",
  "탐색": "Explore",
  "설계 첨부": "Design attached",
  "댓글 {n}": "Comments {n}",
  "글쓰기": "New post",

  // 글 보기
  "글을 불러오는 중이에요": "Loading post…",
  "목록으로": "Back to list",
  "글을 찾을 수 없어요": "Post not found",
  "주소가 잘못되었거나 삭제된 글이에요.": "The address is wrong or the post was deleted.",
  "커뮤니티로 돌아가기": "Back to Community",
  "글을 불러오지 못했어요.": "Couldn't load the post.",
  "이 글을 삭제할까요? 달린 댓글도 함께 지워지고 되돌릴 수 없어요.":
    "Delete this post? Its comments will be deleted too, and this can't be undone.",
  "글을 삭제하지 못했어요. 다시 시도해 주세요.": "Couldn't delete the post. Please try again.",
  "글 수정": "Edit post",
  "(수정됨)": "(edited)",
  "수정": "Edit",
  "삭제 중…": "Deleting…",
  "사진: {credit}": "Photo: {credit}",

  // 첨부한 설계
  "첨부한 설계": "Attached design",
  "구조물": "Structures",
  "3D로 보기": "View in 3D",

  // 댓글
  "댓글": "Comment",
  "댓글 {action}": "{action} comment",
  "댓글이 많아서 최근 {n}개만 보여요.": "There are many comments, so only the latest {n} are shown.",
  "아직 댓글이 없어요.": "No comments yet.",
  "이 댓글을 삭제할까요?": "Delete this comment?",
  "댓글을 삭제하지 못했어요. 다시 시도해 주세요.": "Couldn't delete the comment. Please try again.",
  "댓글은 회원만 남길 수 있어요.": "Only members can comment.",
  "로그인하고 댓글 쓰기": "Log in to comment",
  "댓글 내용을 입력해 주세요.": "Please enter a comment.",
  "댓글은 {n}자까지 쓸 수 있어요.": "Comments can be up to {n} characters.",
  "댓글을 올리지 못했어요. 다시 시도해 주세요.": "Couldn't post the comment. Please try again.",
  "댓글을 적어 주세요.": "Write a comment.",
  "등록 중…": "Submitting…",
  "댓글 등록": "Post comment",

  // 글쓰기·글 수정
  "글쓰기 화면을 준비하는 중이에요": "Getting the editor ready…",
  "글을 올리지 못했어요. 다시 시도해 주세요.": "Couldn't publish the post. Please try again.",
  "작성 중인 내용이 사라져요. 글쓰기를 그만둘까요?": "What you've written will be lost. Stop writing this post?",
  "취소": "Cancel",
  "등록": "Post",
  "글을 수정하지 못했어요. 다시 시도해 주세요.": "Couldn't update the post. Please try again.",
  "저장 중…": "Saving…",
  "저장": "Save",
  "제목": "Title",
  "내용": "Content",

  // 설계 첨부
  "내 설계 목록을 불러오지 못했어요.": "Couldn't load your designs.",
  "첨부하지 않음": "Don't attach",
  "내 설계를 불러오는 중이에요…": "Loading your designs…",
  "설계 없이 글을 올릴 수는 있어요.": "You can still post without a design.",
  "공유하려던 설계를 찾지 못해 첨부하지 않았어요. 목록에서 다시 골라 주세요.":
    "We couldn't find the design you wanted to share, so nothing is attached. Please pick one from the list.",
  "아직 첨부할 설계가 없어요.": "You don't have any designs to attach yet.",
  "설계를 만들면": "Create a design",
  "글에 첨부해서 보여 줄 수 있어요.": "and you can attach it to a post.",
  "선택한 버전(v{v})만 누구나 볼 수 있게 공개돼요. 나중에 고친 버전은 따로 공유하기 전까지 나만 볼 수 있어요.":
    "Only the selected version (v{v}) becomes public. Versions you edit later stay private until you share them.",

  // 사진 고르기 (운영팀)
  "사진": "Photos",
  "(운영팀만 · 최대 {n}장, 고른 순서대로 보여요)": "(staff only · up to {n}, shown in the order picked)",
  "({n}번째)": "(#{n})",
  "넣을 수 있는 사진이 아직 없어요.": "No photos available yet.",
  "목록에 없는 사진": "Photos not in the list",

  // 사진 묶음·설명 (lib/communityImages.ts)
  "골든 햄스터": "Golden hamster",
  "드워프 햄스터": "Dwarf hamster",
  "저빌": "Gerbil",
  "데구": "Degu",
  "기니피그": "Guinea pig",
  "친칠라": "Chinchilla",
  "공통 (쳇바퀴·구조물)": "General (wheels & structures)",
  "옥수수를 먹는 골든(시리안) 햄스터": "Golden (Syrian) hamster eating corn",
  "깊은 깔짚 속에 굴을 파고 쉬는 골든 햄스터": "Golden hamster resting in a burrow in deep bedding",
  "로보로브스키 햄스터": "Roborovski hamster",
  "정글리안(윈터 화이트) 햄스터": "Djungarian (Winter White) hamster",
  "정면을 보는 몽골리안 저빌": "Mongolian gerbil facing the camera",
  "나무 위에 모여 있는 저빌 가족": "A gerbil family gathered on a branch",
  "말린 바나나를 먹는 데구": "Degu eating dried banana",
  "나무 위에 모여 있는 데구 무리": "A group of degus gathered on a branch",
  "은신처와 먹이 그릇 옆에 함께 있는 기니피그들": "Guinea pigs together by a hideout and food bowl",
  "짚 위에 앉은 기니피그": "Guinea pig sitting on straw",
  "바위 위에 앉은 친칠라": "Chinchilla sitting on a rock",
  "옆에서 본 친칠라": "Chinchilla seen from the side",
  "주행면이 막힌 지름 33cm 나무 쳇바퀴": "33 cm wooden wheel with a solid running surface",
  "골든 햄스터용 큰 쳇바퀴": "Large wheel for golden hamsters",

  // 종·크기 이름 (서버가 보내는 한국어 이름)
  "햄스터": "Hamster",
  "골든 (시리안)": "Golden (Syrian) hamster",
  "드워프 (정글리안·캠벨·로보로브스키)": "Dwarf hamster (Djungarian, Campbell's, Roborovski)",
};

export default en;
