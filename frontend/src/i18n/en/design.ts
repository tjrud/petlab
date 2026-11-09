// 설계하기·설계 결과 화면 (NewDesignWizard, DesignView 와 그 패널들, 3D 뷰어, 제작·배송 대기 등록, API 기본 오류 문구)
const en: Record<string, string> = {
  // API 기본 오류 문구 (lib/api.ts)
  "서버와 통신하지 못했어요. 잠시 후 다시 시도해 주세요.": "Couldn't reach the server. Please try again in a moment.",
  "입력값을 확인해 주세요.": "Please check what you entered.",

  // 설계하기 (NewDesignWizard)
  "설계 화면을 준비하고 있어요…": "Getting the design screen ready…",
  "최근 24시간 동안 쓸 수 있는 설계 횟수({limit}회)를 모두 썼어요. 시간이 조금 지나면 다시 설계할 수 있어요.":
    "You've used all your designs for the last 24 hours ({limit}). You can design again a little later.",
  "최근 24시간 동안 쓸 수 있는 설계 횟수를 모두 썼어요. 시간이 조금 지나면 다시 설계할 수 있어요.":
    "You've used all your designs for the last 24 hours. You can design again a little later.",
  "정보를 불러오지 못했어요.": "Couldn't load the information.",
  "선택한 반려동물 정보를 찾지 못했어요. 직접 입력해 주세요.":
    "Couldn't find the selected pet. Please enter the details yourself.",
  "골라 둔 반려동물 정보가 없어져서 연결을 해제했어요. 아래 값을 확인해 주세요.":
    "The pet you picked no longer exists, so it was unlinked. Please check the values below.",
  "종을 바꿔서 반려동물 연결을 해제했어요. 아래 값을 확인해 주세요.":
    "You changed the species, so your pet was unlinked. Please check the values below.",
  "고른 반려동물과 종이 달라서 반려동물 연결을 해제했어요. 다시 누르면 반려동물 연결 없이 설계해요.":
    "The selected pet is a different species, so it was unlinked. Press the button again to design without a linked pet.",
  "{label}는 {lo}~{hi}mm 사이로 입력해 주세요.": "{label} must be between {lo} and {hi} mm.",
  "마릿수는 {min}~{max} 사이로 입력해 주세요.": "Number of pets must be between {min} and {max}.",
  "원하는 구조물이나 배치를 적어 주세요.": "Please describe the structure or layout you want.",
  "설계 중 문제가 생겼어요. 다시 시도해 주세요.": "Something went wrong while designing. Please try again.",
  "진행 단계": "Progress",
  "사육 환경": "Habitat",
  "요구사항": "Request",
  "개발용 모의 해석기": "Mock interpreter (dev)",
  "지금은 임시 저장소로 운영 중이에요. 만든 설계가 잠시 뒤 사라지거나 다시 열리지 않을 수 있으니, 필요한 파일은 바로 내려받아 주세요.":
    "We're running on temporary storage right now. Your designs may disappear or fail to reopen later, so download the files you need right away.",
  "사육 환경을 알려 주세요": "Tell us about your habitat",
  "적어 주신 요청": "Your request",
  "케이지 정보를 확인하고 다음을 누르면 이 요청으로 설계해요. 다음 단계에서 고칠 수 있어요.":
    "Check your cage details and press Next to design with this request. You can edit it in the next step.",
  "내 반려동물": "My pets",
  "직접 입력": "Enter manually",
  "등록된 케이지 치수가 없어서 종·크기만 채웠어요. 아래 치수를 확인해 주세요.":
    "No cage size is saved for this pet, so only species and size were filled in. Please check the dimensions below.",
  "고르면 종·크기와 케이지 치수가 채워져요. 채운 뒤에도 고칠 수 있어요.":
    "Pick one to fill in species, size, and cage dimensions. You can still edit them afterward.",
  "내 정보에서 반려동물을 등록하면 다음부터 자동으로 채워져요":
    "Add your pet in My account to have these filled in automatically next time",
  "종": "Species",
  "햄스터": "Hamster",
  "마릿수": "Number of pets",
  "크기": "Size",
  "케이지 내부 치수 (mm)": "Cage inner dimensions (mm)",
  "소형 45×30×30cm": "Small 45×30×30cm",
  "중형 60×40×30cm": "Medium 60×40×30cm",
  "대형 80×50×40cm": "Large 80×50×40cm",
  "초대형 100×50×50cm": "Extra large 100×50×50cm",
  "가로": "Width",
  "세로": "Depth",
  "높이": "Height",
  "케이지 {label} (mm)": "Cage {label} (mm)",
  "바닥재를 깐 상태의 내부 공간 기준으로 재 주세요.": "Measure the inside space with the bedding in place.",
  "사육장 바닥 최소 기준은 {w}×{d}cm예요. 설계는 할 수 있지만 더 넓은 사육장을 권장해요.":
    "The minimum recommended floor size is {w}×{d}cm. You can still design, but a larger enclosure is recommended.",
  "다음": "Next",
  "원하는 구조물을 적어 주세요": "Describe the structure you want",
  // 영어 크기 이름에는 동물 이름이 들어 있어(예: "Golden (Syrian) hamster", "Nano fish (…)") 종 이름을 다시 붙이지 않는다
  "{species} {size} · {count}마리 · 케이지 {w}×{d}×{h}mm": "{size} · {count} pet(s) · Cage {w}×{d}×{h}mm",
  "예: 환기구가 있는 은신처를 만들어 주세요": "e.g. Make a hideout with air vents",
  "출입구가 두 개 있는 은신처를 만들어 주세요": "Make a hideout with two entrances",
  "케이지 한쪽에 놓을 긴 터널이 필요해요": "I need a long tunnel for one side of the cage",
  "완만한 경사로를 하나 만들어 주세요": "Make a gentle ramp",
  "모래 목욕용 통을 하나 만들고 싶어요": "I'd like a sand bath",
  "이전": "Previous",
  "결과 화면을 여는 중…": "Opening the result…",
  "설계하는 중…": "Designing…",
  "맞춤 설계 받기": "Get a custom design",
  "최근 24시간 남은 설계 횟수: {n}회 · 실패한 요청도 횟수에 포함돼요.":
    "Designs left in the last 24 hours: {n} · Failed requests count too.",
  "요구사항 해석 → 구조물 생성 → 안전 검증까지 최대 1분 정도 걸려요.":
    "Reading your request → building structures → safety checks can take up to about a minute.",
  // 설계하기: 어항 (수조 치수·물 깊이, 경고, 예시)
  "수조 정보를 확인하고 다음을 누르면 이 요청으로 설계해요. 다음 단계에서 고칠 수 있어요.":
    "Check your tank details and press Next to design with this request. You can edit it in the next step.",
  "등록된 수조 치수가 없어서 종·크기만 채웠어요. 아래 치수를 확인해 주세요.":
    "No tank size is saved for this pet, so only species and size were filled in. Please check the dimensions below.",
  "수조 크기와 물 깊이 (mm)": "Tank size and water depth (mm)",
  "수조 버튼은 흔한 수조의 겉 크기예요. 물 깊이는 수조 높이에서 바닥재 약 5cm와 수면 위 여유 약 3cm를 뺀 값으로 채워요.":
    "The tank buttons use common outer tank sizes. Water depth is filled in as the tank height minus about 5 cm of substrate and about 3 cm of space above the water.",
  "수조 버튼 이름은 흔한 수조의 겉 크기예요. 누르면 유리 두께 {g}mm를 빼서 안쪽 가로·세로를 채우고, 물 깊이는 수조 높이에서 바닥 유리와 바닥재 약 5cm, 수면 위 여유 약 3cm를 뺀 값으로 채워요. 내 수조와 다르면 고쳐 주세요.":
    "The tank buttons are named after common outer tank sizes. They fill in the inside width and depth by subtracting {g} mm of glass, and the water depth as the tank height minus the bottom glass, about 5 cm of substrate and about 3 cm of space above the water. Adjust them if your tank is different.",
  "가로·세로는 수조 안쪽 치수로, 물 깊이는 바닥재 위부터 수면까지 재 주세요.":
    "Measure width and depth inside the tank, and water depth from the top of the substrate to the water surface.",
  // 설계하기·반려동물 등록이 함께 쓴다
  "가로·세로는 수조 안쪽 치수(유리 안쪽 사이)로, 물 깊이는 바닥재 위부터 수면까지 재 주세요. 바닥·부피 기준은 유리 두께를 더한 겉 크기로 비교해요.":
    "Measure width and depth inside the tank (between the inner faces of the glass), and water depth from the top of the substrate to the water surface. The minimum floor and volume are checked at outer size, adding the glass thickness.",
  "수조 바닥 최소 기준은 {w}×{d}cm예요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The minimum recommended tank footprint is {w}×{d}cm. You can still design, but a larger tank is recommended.",
  "수조 바닥 최소 기준은 겉 크기 {w}×{d}cm예요. 입력한 안쪽 치수에 유리 두께 {g}mm를 더하면 약 {ow}×{od}mm라 모자라요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The minimum tank footprint is {w}×{d}cm at outer size. Your inside measurements plus {g} mm of glass come to about {ow}×{od}mm, which is smaller. You can still design, but a larger tank is recommended.",
  "수조 부피가 약 {v}L(물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더해 어림)로 {count}마리 기준 권장 최소 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The tank holds about {v} L (estimated from the water depth plus {s} mm of substrate and {a} mm above the water), less than the recommended minimum of {need} L for {count} animals. You can still design, but a larger tank is recommended.",
  "수조 부피가 약 {v}L(물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더해 어림)로 권장 최소 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The tank holds about {v} L (estimated from the water depth plus {s} mm of substrate and {a} mm above the water), less than the recommended minimum of {need} L. You can still design, but a larger tank is recommended.",
  "수조 부피가 약 {v}L(물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더해 어림)로 최소 기준 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The tank holds about {v} L (estimated from the water depth plus {s} mm of substrate and {a} mm above the water), less than the minimum of {need} L. You can still design, but a larger tank is recommended.",
  "수조 부피가 약 {v}L(안쪽 치수에 유리 두께 {g}mm, 물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더한 겉 크기로 어림)로 {count}마리 기준 권장 최소 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The tank holds about {v} L (estimated at outer size: the inside width and depth plus {g} mm of glass, and the water depth plus {s} mm of substrate and {a} mm above the water), less than the recommended minimum of {need} L for {count} animals. You can still design, but a larger tank is recommended.",
  "수조 부피가 약 {v}L(안쪽 치수에 유리 두께 {g}mm, 물 깊이에 바닥재 {s}mm·수면 위 여유 {a}mm를 더한 겉 크기로 어림)로 최소 기준 {need}L보다 작아요. 설계는 할 수 있지만 더 큰 수조를 권장해요.":
    "The tank holds about {v} L (estimated at outer size: the inside width and depth plus {g} mm of glass, and the water depth plus {s} mm of substrate and {a} mm above the water), less than the minimum of {need} L. You can still design, but a larger tank is recommended.",
  "{species} {size} · {count}마리 · 수조 {w}×{d}mm · 물 깊이 {h}mm":
    "{size} · {count} animal(s) · Tank {w}×{d}mm · Water depth {h}mm",
  "예: 새우가 숨을 수 있는 작은 동굴을 만들어 주세요": "e.g. Make a small cave where shrimp can hide",
  // 어항 예시 요청 (영어 화면에서는 이 영어 문장이 요청으로 들어간다: 모의 해석기도 cave·tunnel·through 를 알아듣는다).
  // 동물 이름이 든 예시는 그 동물의 크기 구분을 골랐을 때만 보인다 (NewDesignWizard 의 AQUARIUM_EXAMPLE_PROMPTS)
  "새우가 숨을 수 있는 작은 동굴을 만들어 주세요": "Make a small cave where shrimp can hide",
  "네온 테트라 무리가 지나갈 터널과 동굴을 만들어 주세요": "Make a tunnel and a cave for a school of neon tetras",
  "코리도라스용으로 앞뒤가 뚫린 동굴 두 개": "Two pass-through caves for Corydoras",
  "새우와 작은 물고기가 함께 숨을 수 있는 동굴을 만들어 주세요": "Make a cave where shrimp and small fish can hide together",
  "앞뒤가 뚫린 동굴을 하나 만들어 주세요": "Make a cave open at the front and back",
  "터널 하나와 동굴 하나를 만들어 주세요": "Make one tunnel and one cave",

  // 설계 결과 화면 (DesignView)
  "3D 뷰어 준비 중…": "Preparing 3D viewer…",
  "설계를 불러오지 못했어요.": "Couldn't load the design.",
  "버전을 불러오지 못했어요.": "Couldn't load the version.",
  "수정 중 문제가 생겼어요. 다시 시도해 주세요.": "Something went wrong while revising. Please try again.",
  "지운 설계예요.": "This design was deleted.",
  "설계를 불러오는 중…": "Loading design…",
  "드래그로 회전, 휠로 확대·축소, 구조물을 누르면 상세 정보를 볼 수 있어요.":
    "Drag to rotate, scroll to zoom, and click a structure for details.",
  "요청": "Request",
  "설계 설명": "Design notes",

  // 3D 뷰어 (CageViewer)
  "케이지 내부 {w} × {d} × {h} mm": "Cage interior {w} × {d} × {h} mm",
  "수조 {w} × {d} mm · 물 깊이 {h} mm": "Tank {w} × {d} mm · Water depth {h} mm",
  "앞(관찰 면)": "Front (viewing side)",
  "물 (바닥재 위~수면)": "Water (substrate to surface)",
  "일부 구조물의 3D 형상을 불러오지 못했어요. 이 버전을 만든 뒤 서비스가 바뀌어 형상을 다시 확인하지 못했을 수 있어요. 같은 요청으로 새 버전을 만들어 주세요.":
    "Couldn't load the 3D shape of some structures. The service may have changed since this version was made, so the shapes couldn't be rechecked. Please create a new version with the same request.",

  // 검증 (ValidationPanel)
  "안전·출력 검증": "Safety & print check",
  "통과": "Passed",
  "문제 {n}건": "{n} issue(s)",
  "케이지 적합, 겹침, 끼임 틈새, 벽 두께, 서포트 없는 출력을 모두 확인했어요.":
    "Checked cage fit, overlaps, pinch gaps, wall thickness, and support-free printing.",
  "수조 적합, 물 깊이, 겹침, 끼임 틈새, 벽 두께, 넘어짐, 서포트 없는 출력을 모두 확인했어요.":
    "Checked tank fit, water depth, overlaps, pinch gaps, wall thickness, tipping, and support-free printing.",
  "해결이 필요한 문제": "Issues to fix",
  "주의": "Warnings",
  "자동 보정한 내용": "Auto-corrected",
  "참고": "Notes",

  // 수정 요청 (RevisePanel)
  "수정 요청": "Request changes",
  "커뮤니티에 공유한 버전({versions})만 다른 사람이 볼 수 있어요. 새로 만든 버전은 다시 공유하기 전까지 나만 볼 수 있어요.":
    "Others can only see the versions shared in Community ({versions}). New versions are visible only to you until you share them.",
  "지금 v{base}을 보고 있어요. 이 버전을 기준으로 수정하면 새 버전 v{next}이 만들어지고, 기존 버전은 그대로 남아요.":
    "You're viewing v{base}. Revising from this version creates a new version v{next}, and existing versions stay as they are.",
  "수정할 내용": "Changes to make",
  "예: 은신처를 조금 더 크게, 환기구는 더 많이": "e.g. Make the hideout a bit bigger, with more vents",
  "조금 더 크게 해 주세요": "Make it a bit bigger",
  "환기구를 10개로 늘려 주세요": "Increase the vents to 10",
  "오른쪽으로 옮겨 주세요": "Move it to the right",
  // 어항 설계의 수정 요청 예시
  "예: 동굴을 조금 더 크게, 출입구는 더 넓게": "e.g. Make the cave a bit bigger, with wider entrances",
  "출입구를 더 넓게 해 주세요": "Make the entrances wider",
  "다시 설계하고 있어요…": "Redesigning…",
  "v{n} 기준으로 다시 설계": "Redesign from v{n}",
  "수정 요청도 최근 24시간 설계 횟수에 들어가요. 실패한 요청도 횟수에 포함돼요.":
    "Revisions count toward your 24-hour design limit. Failed requests count too.",

  // 구조물 목록 (ItemList, lib/templates.ts)
  "구조물 ({n})": "Structures ({n})",
  "배치 실패": "Couldn't place",
  "출력 크기 {size}mm (서포트 없이 출력하는 자세 기준)": "Print size {size}mm (in the support-free print orientation)",
  "출입구 폭": "Entrance width",
  "출입구 개수": "Entrances",
  "환기구 개수": "Vents",
  "환기구 지름": "Vent diameter",
  "벽 두께": "Wall thickness",
  "길이": "Length",
  "내경": "Inner diameter",
  "휨 각도": "Bend angle",
  "경사각": "Slope angle",
  "단 수": "Steps",
  "턱 높이": "Lip height",
  "안쪽 깊이": "Inner depth",
  "꼭대기 구멍": "Top opening",
  "지붕 기울기": "Roof slope",
  "경사로": "None (ramp)",
  "{n}단": "{n} steps",
  "{n}개": "{n}",

  // 받기 (DownloadPanel)
  "파일을 받지 못했어요. 잠시 후 다시 시도해 주세요.": "Couldn't download the file. Please try again in a moment.",
  "받기": "Download",
  "STL (zip) 받기": "Download STL (zip)",
  "STL 받기": "Download STL",
  "3MF 받기": "Download 3MF",
  "검증 문제를 해결해야 파일을 내려받을 수 있어요. 위의 수정 요청란에 바꿀 내용을 적어 다시 설계하면 돼요.":
    "Fix the check issues to download the files. Describe the changes in the request box above and redesign.",
  "제작·배송 신청하기": "Request printing & shipping",
  "파일은 mm 단위이며, 서포트 없이 출력할 수 있는 자세로 놓여 있어요.":
    "Files are in mm and oriented to print without supports.",

  // 버전 (VersionList)
  "설계 버전": "Design versions",
  "공유된 설계 버전": "Shared design versions",
  "커뮤니티 글에 첨부된 버전만 볼 수 있어요.": "Only versions attached to Community posts are visible.",
  "공유됨": "Shared",
  "최신": "Latest",
  "검증 통과": "Checks passed",
  "검증 문제 있음": "Check issues found",

  // 제작·배송 대기 등록 (WaitlistForm)
  "알림 수신에 동의해 주세요.": "Please agree to receive notifications.",
  "이메일 주소를 확인해 주세요.": "Please check your email address.",
  "등록하지 못했어요.": "Couldn't sign you up.",
  "대기 등록 완료": "You're on the waitlist",
  "설계로 돌아가기": "Back to design",
  "출력·배송 서비스는 준비 중이에요. 이메일을 남기면 서비스가 열릴 때 알림 메일을 보내요.":
    "Printing & shipping is coming soon. Leave your email and we'll let you know when it opens.",
  "선택한 설계: {design}": "Selected design: {design}",
  "이메일": "Email",
  "서비스 오픈 알림을 받기 위해 이메일 주소를 수집·이용하는 데 동의합니다.":
    "I agree to the collection and use of my email address to receive a launch notification.",
  "등록 중…": "Signing up…",
  "대기 명단에 등록하기": "Join the waitlist",
  // 터널 단면·휘는 모양 (lib/templates.ts)
  "단면 모양": "Cross-section",
  "휘는 모양": "Bend style",
  "뾰족 아치": "Pointed arch",
  "둥근 아치": "Round arch",
  "둥근 관": "Round tube",
  "네모": "Square",
  "집 모양": "House shape",
  "한 방향 곡선": "Single curve",
  "S자": "S-curve",
  "둥근 원통형 터널을 만들어 주세요": "Make a round tube tunnel",
  // 집(house) 템플릿: 부품 이름·값 (lib/templates.ts), 출력 파트 (ItemList, DownloadPanel)
  "바닥판": "Floor plate",
  "바닥판 두께": "Floor plate thickness",
  "지붕 모양": "Roof shape",
  "지붕 경사": "Roof pitch",
  "지붕 꼭대기 각도": "Roof tip angle",
  "층 수": "Floors",
  "2층 바닥 높이": "Second-floor height",
  "층판 두께": "Floor plate thickness",
  "오르는 수단": "Way up",
  "내부 경사로 폭": "Internal ramp width",
  "내부 경사로 경사": "Internal ramp slope",
  "2층 출입구 면": "Second-floor entrance side",
  "출입구 면": "Entrance sides",
  "창 개수": "Windows",
  "창 지름": "Window diameter",
  "터널 연결부 면": "Tunnel port sides",
  "연결부 폭": "Port width",
  "플랜지 길이": "Flange length",
  "앞": "Front",
  "뒤": "Back",
  "왼쪽": "Left",
  "오른쪽": "Right",
  "평 지붕": "Flat roof",
  "경사 지붕": "Pitched roof",
  "둥근 지붕": "Rounded roof",
  "내부 경사로": "Internal ramp",
  "바깥 램프": "Outside ramp",
  "있음": "Yes",
  "없음": "None",
  "{n}층": "{n} floor(s)",
  "본체": "Body",
  "지붕": "Roof",
  "2층 바닥판": "Second-floor plate",
  "출력 파트 {n}개 (서포트 없이 출력하는 자세 기준)": "{n} print parts (sizes in the support-free print orientation)",
  "조립형 구조물은 파트를 따로 출력해 끼워 맞춰요. STL은 파트 {n}개가 zip 하나로, 3MF는 파일 하나에 파트를 모두 담아요.":
    "Assembled structures print as separate parts that fit together. STL comes as one zip with {n} part files; 3MF holds every part in one file.",
  // 장식 (lib/templates.ts describeDecor, ItemList)
  "장식": "Decoration",
  "줄무늬": "Stripes",
  "점무늬": "Dots",
  "비늘무늬": "Scales",
  "벽돌무늬": "Brick",
  "물결무늬": "Wave",
  "벌집무늬": "Honeycomb",
  "바깥 벽": "Outer walls",
  "파내기": "engraved",
  "돋을새김": "relief",
  "각인 '{text}' ({face}, 글자 {h}mm)": "Engraving '{text}' ({face}, {h}mm letters)",
  "{pattern} ({mode}, {face}, 깊이 {d}mm)": "{pattern} ({mode}, {face}, {d}mm deep)",
};

export default en;
