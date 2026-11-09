// 로그인·회원가입·이메일 인증·로그인 안내 화면 문구
const en: Record<string, string> = {
  // 로그인
  "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't reach the server. Please try again in a moment.",
  "확인 중…": "Checking…",
  "다시 시도": "Try again",
  "이미 로그인했어요": "You're already logged in",
  "{name}님으로 로그인한 상태예요. 다른 계정으로 로그인하려면 먼저 로그아웃해 주세요.":
    "You're logged in as {name}. To use a different account, log out first.",
  "메인 화면으로": "Go to home",
  "내 정보 보기": "View my account",
  "로그아웃하는 중…": "Logging out…",
  "로그아웃": "Log out",
  "로그아웃하지 못했어요. 다시 시도해 주세요.": "Couldn't log out. Please try again.",
  "로그인하지 못했어요.": "Couldn't log in.",
  "로그인하면 설계를 만들고, 설계 내역을 보고, 커뮤니티에 글을 쓸 수 있어요.":
    "Log in to create designs, see your design history, and post in the Community.",
  "아이디": "Username",
  "비밀번호": "Password",
  "로그인 중…": "Logging in…",
  "로그인": "Log in",
  "아직 회원이 아니신가요?": "Don't have an account?",
  "회원가입": "Sign up",

  // 회원가입
  "아이디를 확인해 주세요.": "Please check your username.",
  "닉네임을 확인해 주세요.": "Please check your nickname.",
  "이메일 주소를 확인해 주세요.": "Please check your email address.",
  "비밀번호를 확인해 주세요.": "Please check your password.",
  "아이디를 입력해 주세요.": "Please enter a username.",
  "영문 소문자, 숫자, 밑줄(_)만 쓸 수 있어요.": "Use only lowercase letters, numbers, and underscores (_).",
  "아이디는 4~20자로 정해 주세요.": "Usernames must be 4–20 characters.",
  "이메일을 입력해 주세요.": "Please enter your email.",
  "비밀번호를 입력해 주세요.": "Please enter a password.",
  "비밀번호를 한 번 더 입력해 주세요.": "Please enter your password again.",
  "비밀번호가 서로 달라요. 다시 확인해 주세요.": "Passwords don't match. Please check again.",
  // me/common.tsx passwordRuleError 의 문구 (회원가입 화면에서 번역해 보여 준다)
  "비밀번호는 8자 이상이어야 해요.": "Passwords must be at least 8 characters.",
  "비밀번호는 128자 이하로 정해 주세요.": "Passwords can be up to 128 characters.",
  "비밀번호를 아이디와 다르게 정해 주세요.": "Your password must be different from your username.",
  "인증 메일을 보냈어요": "Verification email sent",
  "가입을 마쳤어요": "You're signed up",
  "{email} 주소로 보낸 메일의 링크를 누르면 인증이 끝나요. 가입은 끝났고 바로 로그인되었어요. 인증 전에도 둘러보기와 반려동물 등록은 할 수 있고, 설계·글쓰기·댓글은 인증 뒤에 쓸 수 있어요.":
    "Click the link in the email we sent to {email} to finish verifying. You're signed up and logged in. Before verifying, you can browse and add your pets; designing, posting, and commenting open up after you verify.",
  "바로 로그인되었지만 인증 메일을 보내지 못했어요. 잠시 뒤 내 정보에서 인증 메일을 다시 보내 주세요. 인증을 마쳐야 설계·글쓰기·댓글을 쓸 수 있어요.":
    "You're logged in, but we couldn't send the verification email. Please resend it from My account in a moment. You need to verify before you can design, post, or comment.",
  "계속하기": "Continue",
  "내 정보로 가기": "Go to My account",
  "지금은 회원가입을 받지 않아요": "Sign-ups are closed right now",
  "회원가입이 잠시 닫혀 있어요. 이미 계정이 있다면 로그인해 주세요.":
    "Sign-ups are temporarily closed. If you already have an account, please log in.",
  "로그인하러 가기": "Go to log in",
  "보안 확인을 먼저 마쳐 주세요.": "Please complete the security check first.",
  "회원가입하지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't sign you up. Please try again in a moment.",
  "회원가입은 무료예요. 가입하면 바로 로그인되고, 이메일 인증을 마치면 설계 내역 저장·커뮤니티를 쓸 수 있어요.":
    "Signing up is free. You'll be logged in right away, and once you verify your email you can save your designs and use the Community.",
  "회원가입은 무료예요. 가입하면 바로 로그인되고, 설계 내역 저장·커뮤니티·반려동물 정보 등록을 쓸 수 있어요.":
    "Signing up is free. You'll be logged in right away and can save your designs, use the Community, and add your pets.",
  "영문 소문자·숫자·밑줄(_) 4~20자": "4–20 lowercase letters, numbers, or underscores (_)",
  "닉네임": "Nickname",
  "이메일": "Email",
  "가입하면 이 주소로 인증 메일을 보내요. 인증을 마치면 설계·글쓰기·댓글을 쓸 수 있어요.":
    "We'll send a verification email to this address. Once verified, you can design, post, and comment.",
  "8자 이상, 아이디와 다르게 정해 주세요": "At least 8 characters, different from your username",
  "비밀번호 확인": "Confirm password",
  "보안 확인": "Security check",
  "가입하는 중…": "Signing up…",
  "가입하기": "Sign up",
  "보안 확인을 마치면 가입할 수 있어요.": "Complete the security check to sign up.",
  "이미 회원이신가요?": "Already have an account?",

  // 닉네임 규칙 (lib/nickname.ts)
  "커뮤니티에 보이는 이름이에요. 2~20자, 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.":
    "The name shown in the Community. 2–20 characters; Korean, English letters, numbers, spaces, and _ - . only.",
  "닉네임을 입력해 주세요.": "Please enter a nickname.",
  "닉네임은 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.":
    "Nicknames can use only Korean, English letters, numbers, spaces, and _ - .",
  "닉네임은 2~20자로 정해 주세요.": "Nicknames must be 2–20 characters.",

  // 보안 확인 (Turnstile)
  "보안 확인을 불러오지 못했어요.": "Couldn't load the security check.",
  "다시 불러오기": "Reload",

  // 이메일 인증 링크 화면
  "인증하지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't verify your email. Please try again in a moment.",
  "이메일을 인증하는 중이에요…": "Verifying your email…",
  "이메일 인증을 마쳤어요": "Email verified",
  "로그인하면 바로 설계·글쓰기·댓글을 쓸 수 있어요.": "Log in to start designing, posting, and commenting.",
  "이제 설계·글쓰기·댓글을 쓸 수 있어요.": "You can now design, post, and comment.",
  // 서버(backend/app/api/auth.py)가 보내는 문구
  "이메일 인증을 마쳤어요. 이제 설계·글쓰기·댓글을 쓸 수 있어요.": "Your email is verified. You can now design, post, and comment.",
  "이미 인증한 이메일이에요.": "This email is already verified.",
  "인증 링크가 올바르지 않아요": "This verification link isn't valid",
  "링크의 일부가 빠진 것 같아요. 메일에 있는 링크를 다시 눌러 주세요. 메일을 찾을 수 없다면 내 정보에서 인증 메일을 다시 보낼 수 있어요.":
    "Part of the link seems to be missing. Please click the link in the email again. If you can't find the email, you can resend it from My account.",
  "이미 인증을 마친 계정이에요": "This account is already verified",
  "인증 링크가 올바르지 않거나 만료되었어요": "This verification link is invalid or has expired",
  "이 링크는 이미 쓰였거나 만료되었지만, 지금 로그인한 계정은 이메일 인증을 마쳤어요.":
    "This link has already been used or has expired, but the account you're logged in with is already verified.",
  "인증 링크는 한 번만 쓸 수 있고, 시간이 지나면 만료돼요. 가장 최근에 받은 메일의 링크를 눌러 주시거나 인증 메일을 다시 보내 주세요.":
    "Verification links work only once and expire after a while. Please click the link in your most recent email, or resend the verification email.",
  "이미 이 링크로 인증했다면 인증은 끝났어요. 로그인하면 확인할 수 있어요.":
    "If you already used this link, you're verified. Log in to check.",
  "로그인하기": "Log in",
  "다른 계정에서 이미 인증한 이메일이에요": "This email is already verified on another account",
  "이 이메일 주소는 다른 계정에서 먼저 인증했어요. 내 정보에서 다른 이메일 주소로 바꾼 뒤 다시 인증해 주세요.":
    "Another account has already verified this email address. Please switch to a different email in My account and verify again.",

  // 인증 메일 다시 보내기·안내 띠·폼 안 안내
  "인증 메일을 보냈어요 ({email}). 메일함(스팸함 포함)을 확인해 주세요.":
    "Verification email sent ({email}). Please check your inbox, including spam.",
  "인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.": "Couldn't send the verification email. Please try again in a moment.",
  "보내는 중…": "Sending…",
  "인증 메일 다시 보내기": "Resend verification email",
  "이메일 인증 안내": "Email verification notice",
  "이메일 인증을 마치면 설계·글쓰기·댓글을 쓸 수 있어요.": "Verify your email to design, post, and comment.",
  "이메일을 등록하고 인증하면 설계·글쓰기·댓글을 쓸 수 있어요.": "Add and verify your email to design, post, and comment.",
  "내 정보에서 이메일 등록하기": "Add email in My account",
  "이메일 인증을 마치면 {action} 수 있어요.": "Verify your email to {action}.",
  "메일함에서 인증 링크를 눌러 주세요": "Click the verification link in your inbox",
  "내 정보에서 이메일을 등록하고 인증해 주세요.": "Please add and verify your email in My account.",
  "인증을 마쳤다면 다시 확인": "Already verified? Check again",
  // EmailUnverifiedNotice 의 action (부르는 쪽이 한국어 원문으로 넘긴다)
  "글을 올릴": "post",
  "댓글을 쓸": "comment",
  "맞춤 설계를 받을": "get a custom design",
  "수정을 요청할": "request changes",
  "작품을 올릴": "post your work",
  "제작·배송 신청을 할": "request building and shipping",

  // 로그인 안내 (LoginRequired). message·description 은 부르는 쪽이 한국어 원문으로 넘긴다
  "잠시만 기다려 주세요…": "One moment…",
  "로그인 후 사용할 수 있어요": "Log in to use this feature",
  "회원가입은 무료예요. 아이디·닉네임·이메일만 있으면 시작할 수 있어요.":
    "Signing up is free. All you need is a username, nickname, and email.",
  "회원가입은 무료예요. 아이디와 닉네임만 있으면 바로 시작할 수 있어요.":
    "Signing up is free. All you need is a username and nickname to get started.",
  "로그인 설정이 끝나지 않아 지금은 이 기능을 사용할 수 없어요.":
    "Login isn't set up yet, so this feature isn't available right now.",
  "로그인하면 글을 쓸 수 있어요": "Log in to write a post",
  "로그인하면 내 설계 내역을 볼 수 있어요": "Log in to see your design history",
  "로그인하면 내 정보를 관리할 수 있어요": "Log in to manage your account",
  "로그인하면 작품을 올릴 수 있어요": "Log in to post your work",
  "로그인하면 설계를 만들 수 있어요": "Log in to create a design",
  "회원이 되면 설계 내역이 저장되고 커뮤니티에 공유할 수 있어요.":
    "Members get their design history saved and can share in the Community.",

  // 로그인이 풀렸을 때 (DraftRelogin)
  "로그인이 풀렸어요.": "You've been logged out.",
  "쓰던 내용은 그대로 두었어요. 다시 로그인하고 돌아오면 이어서 쓸 수 있어요.":
    "Your draft is still here. Log in again and come back to pick up where you left off.",
  "다시 로그인하기": "Log in again",
};

export default en;
