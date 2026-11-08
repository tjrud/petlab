// 가상 케이지 에셋 카탈로그(lib/cageAssets.ts)와 커뮤니티 사진 목록(lib/communityImages.ts)의 화면 문구.
// 원본 데이터는 한국어 그대로 두고, 그리는 곳에서 t(값) 으로 바꾼다.
const en: Record<string, string> = {
  // 에셋 종류 (CATEGORIES)
  "은신처": "Hideout",
  "놀이·운동": "Play & exercise",
  "지형·층": "Terrain & levels",
  "급식·급수": "Food & water",
  "위생·휴식": "Hygiene & rest",
  "바닥재": "Bedding",

  // 내가 올린 파일 (registerFileAsset)
  "내 파일": "My files",
  "올린 {format} 파일 (실제 크기)": "Uploaded {format} file (actual size)",

  // 기본 에셋 이름·설명 (CAGE_ASSETS)
  "나무 은신처": "Wooden hideout",
  "지붕 있는 1인용 집. 앞쪽 아치 출입구": "Single hideout with a roof. Arched entrance at the front",
  "다방 은신처": "Multi-room hideout",
  "방이 나뉜 큰 은신처. 앞쪽 출입구 2개": "Large hideout with separate rooms. 2 entrances at the front",
  "통나무 아치": "Log arch",
  "앞뒤가 뚫린 반원형 굴": "Half-round burrow open at the front and back",
  "코너 은신처": "Corner hideout",
  "모서리에 붙여 쓰는 삼각 지붕 집": "Triangular-roof hideout that fits in a corner",
  "21cm 쳇바퀴": "21cm wheel",
  "지름 21cm 바퀴 + 받침대. 앞쪽으로 타고 내려요": "21cm diameter wheel on a stand. Gets on and off at the front",
  "28cm 쳇바퀴": "28cm wheel",
  "지름 28cm 바퀴 + 받침대. 앞쪽으로 타고 내려요": "28cm diameter wheel on a stand. Gets on and off at the front",
  "일자 터널": "Straight tunnel",
  "양 끝(좌우)이 뚫린 원통 터널. 안지름 80mm": "Tube tunnel open at both ends (left and right). 80mm inner diameter",
  "땅굴 상자": "Dig box",
  "깊게 파고들 수 있는 바닥재 상자. 앞쪽 턱 30mm": "Bedding box for deep digging. 30mm lip at the front",
  "2층 플랫폼": "Raised platform",
  "다리 4개로 받친 높이 15cm 선반 (아래는 비워 둬요)": "15cm-high shelf on 4 legs (keep the space below clear)",
  "경사로": "Ramp",
  "왼쪽이 낮고 오른쪽 끝이 10cm 높이": "Low on the left, 10cm high at the right end",
  "아치 다리": "Arch bridge",
  "나무 조각을 엮은 휘어지는 다리. 좌우로 건너요": "Bendable bridge of wooden slats. Crossed left to right",
  "디딤돌": "Stepping stone",
  "높이 6cm 돌. 올라서거나 건너뛰어요": "6cm-high stone to climb on or hop over",
  "밥그릇": "Food bowl",
  "지름 10cm 도자기 그릇": "10cm diameter ceramic bowl",
  "스탠드 급수기": "Water bottle with stand",
  "받침대에 세우는 물병. 앞쪽 꼭지로 마셔요": "Water bottle on a stand. Drinks from the spout at the front",
  "모래목욕통": "Sand bath",
  "모래를 담는 낮은 통. 안쪽 22×20cm, 턱 높이 30mm": "Low tray for sand. 22×20cm inside, 30mm lip",
  "코너 화장실": "Corner toilet",
  "모서리용 덮개형 화장실. 앞쪽 출입구": "Covered corner toilet. Entrance at the front",
  "쿨링 대리석": "Cooling marble",
  "더운 날 엎드려 쉬는 얇은 판": "Thin slab to lie on during hot days",
  "톱밥 바닥재 5cm": "Wood shavings 5cm",
  "바닥 전체에 5cm 깔아요. 구조물은 바닥재 위에 놓여요": "5cm across the whole floor. Items sit on top of the bedding",
  "톱밥 바닥재 15cm": "Wood shavings 15cm",
  "굴을 팔 수 있게 15cm 깊게 깔아요. 그만큼 위 공간이 줄어요":
    "15cm deep for burrowing. Reduces the space above by as much",
  "종이 깔짚 5cm": "Paper bedding 5cm",
  "먼지가 적은 종이 깔짚을 바닥 전체에 5cm 깔아요": "Low-dust paper bedding, 5cm across the whole floor",

  // 커뮤니티 사진 묶음 (COMMUNITY_IMAGES.group)
  "골든 햄스터": "Golden hamster",
  "드워프 햄스터": "Dwarf hamster",
  "저빌": "Gerbil",
  "데구": "Degu",
  "기니피그": "Guinea pig",
  "친칠라": "Chinchilla",
  "공통 (쳇바퀴·구조물)": "General (wheels & structures)",

  // 커뮤니티 사진 설명 (COMMUNITY_IMAGES.alt)
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

  // 커뮤니티 사진 라이선스 (COMMUNITY_IMAGES.license, 한국어인 것만)
  "퍼블릭 도메인": "Public domain",
};

export default en;
