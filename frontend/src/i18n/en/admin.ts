// 관리자 화면: 부품 요청 (app/[lang]/admin/part-requests, components/admin/*, AuthMenu 의 링크)
const en: Record<string, string> = {
  // 머리글·메뉴
  "부품 요청": "Part requests",
  "설계 요청에서 카탈로그에 없다고 나온 부품이에요. 많이 찾는 부품부터 만들어 부품 라이브러리에 더해요.":
    "Parts that design requests asked for but the catalog doesn't have yet. Build the most wanted ones first and add them to the part library.",
  "관리자만 쓸 수 있어요.": "Admins only.",
  "관리자로 로그인해 주세요": "Log in as an admin",
  "부품 요청은 관리자만 볼 수 있어요.": "Only admins can see part requests.",

  // 상태·정렬
  "요청 상태": "Request status",
  "새 요청": "Open",
  "만들 예정": "Planned",
  "부품 공개": "Published",
  "만들지 않음": "Rejected",
  "합친 요청": "Merged",
  "정렬": "Sort",
  "회원 많은 순": "Most members",
  "설계 많은 순": "Most designs",
  "최근 순": "Most recent",
  "이름으로 찾기": "Search by name",
  "찾기": "Search",
  "JSON 내보내기": "Export JSON",
  "내보내는 중…": "Exporting…",
  "내보내지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't export. Please try again in a moment.",

  // 목록
  "부품 요청을 불러오는 중…": "Loading part requests…",
  "부품 요청을 불러오지 못했어요.": "Couldn't load part requests.",
  "찾는 이름의 부품 요청이 없어요.": "No part requests match that name.",
  "이 페이지에는 부품 요청이 없어요.": "There are no part requests on this page.",
  "이 상태의 부품 요청이 없어요.": "No part requests with this status.",
  "부품": "Part",
  "회원 / 설계": "Members / designs",
  "종·크기": "Species and size",
  "쓰임새": "Purpose",
  "최근 예시": "Recent examples",
  "처음 / 최근": "First / last seen",
  "상태": "Status",
  "관리": "Manage",
  "접기": "Close",
  "{name} 자세히·관리": "Details and actions for {name}",
  "이미 있는 부품: {keys}": "Covered by: {keys}",
  "회원 정보는 보이지 않고, 예시는 연락처를 지운 요청 앞부분만 보여요. 설계를 지워도 부품 요청 기록은 남아요.":
    "Member details are never shown, and examples show only the start of each request with contact details removed. Deleting a design does not remove its part requests.",

  // 자세히·관리
  "최근 설계": "Recent designs",
  "최근 설계를 불러오지 못했어요.": "Couldn't load recent designs.",
  "기록된 설계가 없어요.": "No designs recorded.",
  "(예시 글을 지웠어요)": "(example removed)",
  "다른 요청에 합친 요청이에요. 메모만 고칠 수 있어요.": "This request was merged into another one. Only the note can be changed.",
  "부품 키": "Part key",
  "부품 공개로 바꾸려면 부품 라이브러리에 있는 부품 키를 적어 주세요.":
    "To mark it published, enter a part key from the part library.",
  "관리 메모": "Admin note",
  "바뀐 내용이 없어요.": "Nothing changed.",
  "다른 요청에 합치기": "Merge into another request",
  "같은 부품을 다른 이름으로 적은 요청이면 합쳐요. 횟수와 예시가 고른 요청으로 옮겨 가요. 이 페이지의 요청에서 고를 수 있어요.":
    "Merge requests that name the same part differently. Counts and examples move to the request you pick. You can pick from the requests on this page.",
  "합칠 요청 고르기": "Choose a request",
  "합치기": "Merge",
  '"{name}" 요청을 "{target}" 요청에 합칠까요? 되돌릴 수 없어요.': 'Merge "{name}" into "{target}"? This can\'t be undone.',
  "예시 지우기": "Clear examples",
  "이 요청의 예시 글을 모두 지울까요? 되돌릴 수 없어요.": "Clear all examples for this request? This can't be undone.",
  "예시 글을 지웠어요.": "Examples cleared.",

  // 부품 요청 → 부품 키 고르기 (부품 라이브러리에서)
  "부품 공개로 바꾸려면 이 요청을 채우는 라이브러리 부품을 골라 주세요.":
    "To mark it published, choose the library part that covers this request.",
  "부품 키 없음": "No part key",
  "이 요청을 채우는 부품": "Parts that cover this request",
  "다른 부품": "Other parts",

  // 부품 라이브러리 (LibraryList, 읽기 전용)
  "부품 라이브러리": "Part library",
  "게시한 부품이에요. 게시·폐기·차단은 개발 도구로만 하고, 여기서는 보기만 해요.":
    "Published parts. Publishing, retiring and blocking are done only with the developer tool; this list is read-only.",
  "부품 라이브러리를 불러오는 중…": "Loading the part library…",
  "부품 라이브러리를 불러오지 못했어요.": "Couldn't load the part library.",
  "색인과 파일이 맞지 않는 곳이 있어요. audit 으로 확인해 주세요.":
    "The index and the files don't match in some places. Check with audit.",
  "게시한 부품이 아직 없어요.": "No parts have been published yet.",
  "역할": "Role",
  "공개 상태": "Availability",
  "검증한 종·크기": "Verified species and sizes",
  "채우는 요청": "Covers requests",
  "게시일": "Published",
  "마지막 검증": "Last verification",
  "받침 부품": "Base part",
  "방 부품": "Room part",
  "붙이는 부품": "Attachment",
  "단독 부품": "Standalone part",
  "쓰는 중": "Active",
  "새 설계에 쓰지 않음": "Retired",
  "내려받기 막음": "Blocked",
  "새 판: {key}": "Replaced by: {key}",
  "검증 기록 없음": "No verification record",
  "실패": "Failed",
  "전체 검증": "Full verification",
  "빠른 검증": "Quick verification",
  "검사 {n}개 · 실패 {f}개": "{n} checks · {f} failed",
  "스키마 예산 초과: {species}": "Over the schema budget: {species}",
};

export default en;
