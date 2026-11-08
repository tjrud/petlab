// 내 정보 화면 (components/me/*)
const en: Record<string, string> = {
  // MyInfo
  "내 정보를 불러오지 못했어요.": "Couldn't load your account info.",
  "반려동물 정보를 불러오지 못했어요.": "Couldn't load your pets.",
  "잠시 뒤 다시 시도해 주세요.": "Please try again in a moment.",
  "로그인하면 내 정보를 관리할 수 있어요": "Log in to manage your account",
  "계정 설정": "Account settings",

  // ProfileCard
  "관리자": "Admin",
  "아이디": "Username",
  "가입일": "Joined",
  "활동 요약": "Activity summary",
  "반려동물": "Pets",
  "{n}마리": "{n}",
  "내 설계": "My designs",
  "{n}개": "{n}",
  "커뮤니티 글": "Community post",
  "최근 24시간 설계": "Designs in the last 24 hours",
  "관리자는 제한 없음": "No limit for admins",
  "{used}/{limit}회": "{used}/{limit}",
  "최근 24시간 동안 쓸 수 있는 설계 횟수를 모두 썼어요. 시간이 지나면 다시 설계할 수 있어요.":
    "You've used all your designs for the last 24 hours. You can design again once some time has passed.",
  "설계 만들기와 수정 요청을 합쳐 {n}회 더 할 수 있어요. 실패한 요청도 횟수에 포함돼요.":
    "{n} left, counting new designs and revision requests together. Failed requests count too.",
  "사용량을 불러오는 중…": "Loading usage…",

  // NicknameForm
  "닉네임 바꾸기": "Change nickname",
  "관리자 닉네임은 바꿀 수 없어요.": "The admin nickname can't be changed.",
  "지금 쓰고 있는 닉네임과 같아요.": "That's already your nickname.",
  "닉네임을 바꿨어요.": "Nickname changed.",
  "닉네임을 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't change your nickname. Please try again in a moment.",
  "닉네임": "Nickname",
  "바꾸는 중…": "Saving…",
  "닉네임 변경": "Change nickname",
  "커뮤니티에 보이는 이름이에요. 2~20자, 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.":
    "The name shown in the Community. 2–20 characters; Korean, English letters, numbers, spaces, and _ - . only.",
  "닉네임을 입력해 주세요.": "Please enter a nickname.",
  "닉네임은 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.": "Nicknames can use only Korean, English letters, numbers, spaces, and _ - .",
  "닉네임은 2~20자로 정해 주세요.": "Nicknames must be 2–20 characters.",

  // EmailForm
  "새 이메일 주소를 입력해 주세요.": "Please enter a new email address.",
  "이메일 주소를 확인해 주세요.": "Please check your email address.",
  "지금 쓰고 있는 이메일과 같아요.": "That's already your email address.",
  "본인 확인을 위해 지금 쓰는 비밀번호를 입력해 주세요.": "Enter your current password to confirm it's you.",
  "새 주소로 인증 메일을 보냈어요 ({email}). 메일의 링크를 눌러 인증을 마쳐 주세요.":
    "We sent a verification email to your new address ({email}). Click the link in the email to finish verifying.",
  "이메일을 바꿨지만 인증 메일을 보내지 못했어요. 잠시 뒤 인증 메일을 다시 보내 주세요.":
    "Your email was changed, but we couldn't send the verification email. Please resend it in a moment.",
  "이메일을 바꿨어요.": "Email changed.",
  "이메일을 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't change your email. Please try again in a moment.",
  "이메일": "Email",
  "인증됨": "Verified",
  "인증 전": "Not verified",
  "아직 등록한 이메일이 없어요. 이메일을 등록하고 인증하면 설계·글쓰기·댓글을 쓸 수 있어요.":
    "You haven't added an email yet. Add and verify one to create designs, write posts, and comment.",
  "메일함에서 인증 링크를 눌러 주세요. 메일이 없다면 다시 보낼 수 있어요.":
    "Click the verification link in your inbox. Didn't get it? You can send it again.",
  "이메일 바꾸기": "Change email",
  "이메일 등록": "Add email",
  "새 이메일": "New email",
  "새 주소로 인증 메일을 보내요. 인증을 마칠 때까지는 인증 전 상태가 돼요.":
    "We'll send a verification email to the new address. It stays unverified until you finish.",
  "비밀번호 (본인 확인)": "Password (to confirm it's you)",
  "이메일 변경": "Change email",
  "취소": "Cancel",

  // PasswordForm
  "지금 쓰는 비밀번호를 입력해 주세요.": "Please enter your current password.",
  "새 비밀번호를 입력해 주세요.": "Please enter a new password.",
  "지금 쓰는 비밀번호와 다르게 정해 주세요.": "Your new password must be different from your current one.",
  "새 비밀번호를 한 번 더 입력해 주세요.": "Please enter your new password again.",
  "새 비밀번호가 서로 달라요. 다시 확인해 주세요.": "The new passwords don't match. Please check again.",
  "비밀번호는 8자 이상이어야 해요.": "Passwords must be at least 8 characters.",
  "비밀번호는 128자 이하로 정해 주세요.": "Passwords can be up to 128 characters.",
  "비밀번호를 아이디와 다르게 정해 주세요.": "Your password must be different from your username.",
  "현재 비밀번호": "Current password",
  "새 비밀번호": "New password",
  "8자 이상, 아이디와 다르게 정해 주세요": "At least 8 characters, different from your username",
  "새 비밀번호 확인": "Confirm new password",
  "비밀번호 바꾸기": "Change password",
  "관리자 비밀번호는 서버 환경변수(ADMIN_PASSWORD)로 관리해서 여기서는 바꿀 수 없어요.":
    "The admin password is managed by a server environment variable (ADMIN_PASSWORD), so it can't be changed here.",
  "비밀번호를 바꾸지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't change your password. Please try again in a moment.",
  "비밀번호를 바꿨어요. 이 기기는 그대로 로그인되어 있고, 다른 기기에서는 로그아웃됐어요.":
    "Password changed. You're still logged in on this device and have been logged out everywhere else.",
  "비밀번호 변경": "Change password",

  // PetSection
  "{name} 정보를 고쳤어요.": "Updated {name}'s info.",
  "{name} 등록했어요.": "Added {name}.",
  "{name} 정보를 삭제했어요.": "Deleted {name}'s info.",
  "삭제했어요.": "Deleted.",
  "내 반려동물": "My pets",
  "등록해 두면 설계할 때 종·크기·케이지 치수가 자동으로 채워져요.":
    "Add your pets and their species, size, and cage dimensions will be filled in automatically when you design.",
  "반려동물 등록": "Add pet",
  "반려동물은 {max}마리까지 등록할 수 있어요.": "You can add up to {max} pets.",
  "종 목록을 불러오지 못해 지금은 등록·수정할 수 없어요.": "Couldn't load the species list, so pets can't be added or edited right now.",
  "반려동물 정보를 불러오는 중…": "Loading your pets…",
  "아직 등록한 반려동물이 없어요": "No pets added yet",
  "이름·종·크기·케이지 치수를 저장해 두면 다음 설계 때 자동으로 채워져요.":
    "Save a name, species, size, and cage dimensions and they'll be filled in for your next design.",

  // PetCard
  "삭제하지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't delete. Please try again in a moment.",
  "{name} 정보를 삭제할까요? 이 아이로 만든 설계는 그대로 남아요.": "Delete {name}'s info? Designs made for this pet will stay.",
  "성별": "Sex",
  "생일": "Birthday",
  "케이지": "Cage",
  "삭제 확인": "Confirm deletion",
  "삭제하는 중…": "Deleting…",
  "네, 삭제할게요": "Yes, delete",
  "아니요": "No",
  "이 아이로 설계하기": "Design for this pet",
  "수정": "Edit",
  "삭제": "Delete",
  "수컷": "Male",
  "암컷": "Female",
  "모름": "Unknown",
  "1개월 미만": "Under 1 mo",
  "{m}개월": "{m} mo",
  "{y}살": "{y} yr",
  "{y}살 {m}개월": "{y} yr {m} mo",

  // 종·크기 (rules/species.yaml)
  "햄스터": "Hamster",
  "골든 (시리안)": "Golden (Syrian)",
  "드워프 (정글리안·캠벨·로보로브스키)": "Dwarf (Djungarian, Campbell's, Roborovski)",

  // PetForm
  "이름을 입력해 주세요.": "Please enter a name.",
  "이름에 쓸 수 없는 문자가 있어요.": "The name contains characters that aren't allowed.",
  "이름은 40자 이하로 입력해 주세요.": "Names can be up to 40 characters.",
  "종을 골라 주세요.": "Please choose a species.",
  "크기를 골라 주세요.": "Please choose a size.",
  "생일은 1990년 1월 1일부터 오늘 사이로 입력해 주세요.": "Birthday must be between January 1, 1990 and today.",
  "메모에 쓸 수 없는 문자가 있어요.": "The notes contain characters that aren't allowed.",
  "메모는 {max}자 이하로 적어 주세요.": "Notes can be up to {max} characters.",
  "가로·세로·높이를 모두 입력하거나, 치수 비우기를 눌러 주세요.": "Enter width, depth, and height, or click Clear dimensions.",
  "입력해 주세요.": "Required.",
  "{label}는 {lo}~{hi}mm 사이로 입력해 주세요.": "{label} must be between {lo} and {hi} mm.",
  "반려동물 정보 수정": "Edit pet",
  "저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't save. Please try again in a moment.",
  "이름": "Name",
  "종": "Species",
  "크기": "Size",
  "크기를 골라 주세요": "Choose a size",
  "선택": "Optional",
  "생일 지우기": "Clear birthday",
  "메모": "Notes",
  "예: 겁이 많아서 은신처를 좋아해요": "e.g. Shy and loves her hideout",
  "케이지 내부 치수": "Cage interior dimensions",
  "저장해 두면 설계할 때 자동으로 채워져요. 모르면 비워 두어도 돼요.":
    "Saved dimensions are filled in automatically when you design. Leave blank if you're not sure.",
  "소형 45×30×30cm": "Small 45×30×30cm",
  "중형 60×40×30cm": "Medium 60×40×30cm",
  "대형 80×50×40cm": "Large 80×50×40cm",
  "초대형 100×50×50cm": "Extra large 100×50×50cm",
  "치수 비우기": "Clear dimensions",
  "가로": "Width",
  "세로": "Depth",
  "높이": "Height",
  "저장 중…": "Saving…",
  "저장": "Save",
};

export default en;
