// 화면(page)·메인 화면·헤더·공통 작은 컴포넌트의 문구
const en: Record<string, string> = {
  // 레이아웃·메타데이터
  "NestForge – 햄스터 맞춤 케이지 구조물 설계": "NestForge – Custom cage accessories for hamsters",
  "햄스터 케이지 치수에 맞춘 은신처·터널·경사로·모래목욕통, 어항에 넣을 물속 동굴·터널 설계와 3D 프린팅 파일(STL·3MF).":
    "Hideouts, tunnels, ramps and sand baths designed to fit your hamster's cage, plus underwater caves and tunnels for aquariums, with 3D printing files (STL, 3MF).",
  "케이지 치수를 정하고 은신처·쳇바퀴·모래목욕통 같은 구조물을 놓아 보며 겹침과 끼임 틈을 미리 확인해요.":
    "Set your cage size, place hideouts, wheels and sand baths, and check for overlaps and trap gaps ahead of time.",
  "보호자들이 만든 은신처·터널·경사로 SKP·3MF·STL 파일과 가상 케이지 배치를 나누는 곳.":
    "Share hideout, tunnel and ramp files (SKP, 3MF, STL) and virtual cage layouts made by hamster owners.",
  "커뮤니티 글": "Community post",
  "공유 작품": "Shared work",
  "작품 올리기 · 탐색": "Upload a work · Explore",

  // 화면 제목·소개
  "가상 케이지 시뮬레이션": "Virtual cage simulation",
  "케이지 치수를 정하고 카탈로그의 구조물을 놓고, 옮기고, 돌려 보세요. 놓을 때마다 겹침·케이지 밖·끼임 틈·출입구 앞 공간을 확인해요. 용품을 사거나 배치를 바꾸기 전에 미리 맞춰 볼 수 있어요.":
    "Set your cage size, then place, move and rotate items from the catalog. Each time you place one, we check for overlaps, anything outside the cage, trap gaps and space in front of entrances. Try it out before you buy supplies or rearrange your layout.",
  "목록으로": "Back to list",
  "글쓰기": "New post",
  "설계와 사육 정보를 올리고 보는 곳이에요.": "Share and read designs and hamster care tips.",
  "맞춤 설계하기": "Create a custom design",
  "사육 환경과 원하는 구조물을 적으면 설계와 함께 안전·출력 기준 검사 결과가 나와요. 결과는 3D로 보고 STL·3MF 파일로 내려받을 수 있어요.":
    "Describe your hamster's setup and the structure you want, and you'll get a design along with safety and print checks. View the result in 3D and download it as STL or 3MF files.",
  "설계를 불러오는 중…": "Loading design…",
  "만든 설계를 최근 수정한 순서로 보여요.": "Your designs, most recently edited first.",
  "새 설계": "New design",
  "작품 올리기": "Upload a work",
  "보호자들이 만든 구조물 파일(SKP·3MF·STL)과 가상 케이지 배치를 내려받고 나누는 곳이에요.":
    "Download and share structure files (SKP, 3MF, STL) and virtual cage layouts made by hamster owners.",
  "로그인": "Log in",
  "회원가입": "Sign up",
  "이메일 인증": "Email verification",
  "제작·배송 신청": "Request printing and delivery",

  // 헤더·메뉴
  "NestForge 홈": "NestForge home",
  "서버에 연결하지 못했어요": "Couldn't connect to the server",
  "확인 중…": "Checking…",
  "다시 시도": "Try again",
  "관리자": "Admin",
  "로그아웃": "Log out",
  "로그아웃하지 못했어요. 다시 시도해 주세요.": "Couldn't log out. Please try again.",

  // 페이지 이동
  "페이지 이동": "Pagination",
  "이전": "Previous",
  "다음": "Next",
  "{page} / {total} 페이지": "Page {page} of {total}",

  // 메인: 소개
  "햄스터 케이지·어항 맞춤 구조물": "Custom accessories for hamster cages and aquariums",
  "필요한 구조물을 적어 보세요": "Describe the structure you need",
  "은신처, 터널, 계단, 모래목욕통, 어항에 넣을 물속 동굴. 원하는 구성과 위치를 적으면 케이지나 수조 치수에 맞게 설계하고, 3D 프린팅 파일(STL·3MF)로 받을 수 있어요.":
    "Hideouts, tunnels, stairs, sand baths, and underwater caves for aquariums. Describe what you want and where, and we'll design it to fit your cage or tank and give you 3D printing files (STL, 3MF).",
  "맞춤 설계 요청": "Custom design request",
  "원하는 구조물": "Structure you want",
  "예: 환기구가 있는 은신처": "e.g. A hideout with air vents",
  "예시": "Examples",
  "출입구가 두 개 있는 은신처를 만들어 주세요": "Make a hideout with two entrances",
  "케이지 한쪽에 놓을 긴 터널이 필요해요": "I need a long tunnel for one side of the cage",
  "완만한 경사로를 하나 만들어 주세요": "Make a gentle ramp",
  "안전 기준 자동 검증": "Automatic safety checks",
  "3D로 미리 보기": "3D preview",
  "STL·3MF 파일 내려받기": "Download STL and 3MF files",
  "은신처": "Hideout",
  "터널": "Tunnel",
  "램프·계단": "Ramp & stairs",
  "모래목욕통": "Sand bath",
  "물속 동굴": "Underwater cave",

  // 메인: 이용 순서
  "이렇게 만들어요": "How it works",
  "세 단계로 진행돼요.": "It takes three steps.",
  "{n}단계": "Step {n}",
  "사육 환경 입력": "Describe your setup",
  "종·크기·마릿수와 케이지 내부 치수(어항은 수조 크기와 물 깊이)를 고르고, 원하는 구조물을 적어요.":
    "Choose the species, size and number of animals, plus the inner cage dimensions (tank size and water depth for aquariums), then describe the structure you want.",
  "설계·안전 검증": "Design & safety check",
  "적은 내용대로 구조물 치수를 정하고, 출입구 크기·오르는 높이·벽 두께·물속 공기 빠짐 같은 안전·출력 기준을 확인해요.":
    "We size the structure from your description and check safety and print rules like entrance size, climb height, wall thickness and air release underwater.",
  "3D 확인·프린팅 파일(STL·3MF)": "3D review & print files (STL, 3MF)",
  "3D로 돌려 보며 확인하고, 바꿀 부분은 글로 다시 요청해요. 끝나면 STL·3MF 파일로 내려받아요.":
    "Rotate it in 3D to check, and describe any changes in words. When you're done, download STL or 3MF files.",

  // 메인: 주요 기능
  "주요 기능": "Features",
  "바로 가기": "Go",
  "케이지나 수조 치수와 원하는 구조물을 적으면 치수에 맞춘 설계와 3D 프린팅 파일이 나와요.":
    "Enter your cage or tank size and the structure you want to get a design that fits, plus 3D printing files.",
  "케이지 치수를 등록하고 은신처·쳇바퀴·모래목욕통을 놓아 보며 겹침과 끼임 틈을 미리 확인해요.":
    "Enter your cage size, place hideouts, wheels and sand baths, and check for overlaps and trap gaps ahead of time.",
  "보호자들이 만든 SKP·3MF·STL 파일과 가상 케이지 배치를 내려받고, 내가 만든 구조물을 올릴 수 있어요.":
    "Download SKP, 3MF and STL files and virtual cage layouts made by other owners, and upload your own structures.",
  "내 설계 내역": "My design history",
  "지금까지 만든 설계와 버전을 한곳에서 보고, 이어서 고치거나 다시 내려받을 수 있어요.":
    "See all your designs and versions in one place, keep editing them or download them again.",
  "다른 보호자의 설계와 사육 이야기를 보고, 내 설계를 공유할 수 있어요.":
    "Read other owners' designs and care stories, and share your own designs.",
  "내 정보·반려동물": "My account & pets",
  "반려동물과 케이지·수조 정보를 등록해 두면 다음 설계 때 바로 불러올 수 있어요.":
    "Save your pets and their cage or tank details to load them right away next time you design.",

  // 메인: 회원 영역
  "내 정보를 확인하는 중이에요": "Checking your account…",
  "내 공간": "My space",
  "{name}님의 최근 설계와 등록한 반려동물이에요.": "{name}'s recent designs and pets.",
  "다시 로그인하기": "Log in again",
  "다시 불러오기": "Reload",
  "반려동물 정보를 불러오지 못했어요.": "Couldn't load your pets.",
  "내 반려동물": "My pets",
  "관리하기": "Manage",
  "반려동물 정보를 불러오는 중이에요": "Loading your pets…",
  "등록된 반려동물이 없어요.": "No pets yet.",
  "아이와 케이지 정보를 등록해 두면 다음 설계 때 바로 불러올 수 있어요.":
    "Save your hamster and cage details to load them right away next time you design.",
  "반려동물 등록하기": "Add a pet",
  "그 밖에 {n}마리가 더 있어요.": "{n} more not shown.",
  "모두 보기": "View all",
  "이 아이로 설계하기": "Design for this pet",
  "케이지 {w}×{d}×{h}mm": "Cage {w}×{d}×{h}mm",
  "설계 내역을 불러오지 못했어요.": "Couldn't load your designs.",
  "최근 내 설계": "My recent designs",
  "총 {n}개": "{n} total",
  "전체 내역": "View all",
  "최근 설계를 불러오는 중이에요": "Loading recent designs…",
  "아직 만든 설계가 없어요.": "No designs yet.",
  "케이지 크기와 원하는 구조물을 적으면 설계를 시작할 수 있어요.":
    "Enter your cage size and the structure you want to start designing.",
  "첫 설계 시작하기": "Start your first design",
  "제목 없는 설계": "Untitled design",
  "{date} 수정": "Edited {date}",
  "검증 통과": "Checks passed",
  "검증 문제 있음": "Check issues found",
  "커뮤니티 공유됨": "Shared to Community",

  // 메인: 가입 안내
  "가입하면 설계를 저장하고 공유할 수 있어요": "Sign up to save and share your designs",
  "로그인하면 설계를 저장하고 공유할 수 있어요": "Log in to save and share your designs",
  "설계 만들기는 회원만 할 수 있어요.": "Only members can create designs.",
  "가입은 무료이고, 아이디·닉네임·이메일만 있으면 돼요.":
    "Signing up is free and only needs a username, nickname and email.",
  "가입은 무료이고, 아이디와 닉네임만 있으면 돼요.": "Signing up is free and only needs a username and nickname.",
  "만든 설계가 저장돼서 언제든 다시 보고 고칠 수 있어요": "Your designs are saved so you can view and edit them anytime",
  "반려동물 정보를 등록해 두면 케이지 치수를 다시 입력하지 않아도 돼요":
    "Save your pet's details so you don't have to re-enter cage dimensions",
  "커뮤니티에 글과 댓글을 남기고 내 설계를 공유할 수 있어요": "Post and comment in the Community and share your designs",

  // 메인: 최근 글
  "커뮤니티 글을 불러오지 못했어요.": "Couldn't load community posts.",
  "최근 커뮤니티 글": "Recent community posts",
  "다른 보호자들은 어떤 구조물을 만들었을까요?": "See what other owners have built.",
  "전체 보기": "View all",
  "최근 글을 불러오는 중이에요": "Loading recent posts…",
  "아직 올라온 글이 없어요.": "No posts yet.",
  "설계나 사육 이야기를 올려 주세요.": "Share a design or a hamster care story.",
  "커뮤니티로 가기": "Go to Community",
  "설계 첨부": "Design attached",
  "댓글 {n}": "Comments {n}",

  // 종·크기 이름 (서버가 보내는 한국어 이름)
  "햄스터": "Hamster",
  "골든 (시리안)": "Golden (Syrian) hamster",
  "드워프 (정글리안·캠벨·로보로브스키)": "Dwarf hamster (Djungarian, Campbell's, Roborovski)",
};

export default en;
