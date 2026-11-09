// 여러 화면이 함께 쓰는 문구 (헤더·메뉴·언어 선택 등)
const en: Record<string, string> = {
  "설계하기": "Design",
  "가상 케이지": "Virtual cage",
  "내 설계": "My designs",
  "탐색": "Explore",
  "커뮤니티": "Community",
  "내 정보": "My account",
  "주 메뉴": "Main menu",
  "내 정보 메뉴": "Account menu",
  "언어": "Language",
  "한국어로 보기": "View in Korean",
  "영어로 보기": "View in English",

  // 사육 환경 종류(케이지·어항)에 따른 낱말 (lib/habitatKind.ts, 카드·요약 한 줄)
  "수조": "Tank",
  "물 깊이": "Water depth",
  "수조 가로 (mm)": "Tank width (mm)",
  "수조 세로 (mm)": "Tank depth (mm)",
  "물 깊이 (mm)": "Water depth (mm)",
  "수조 {w}×{d}mm · 물 깊이 {h}mm": "Tank {w}×{d}mm · Water depth {h}mm",
  // 수조 프리셋 (겉 크기 이름. 숫자만 있는 이름도 t() 로 보이므로 같은 값을 둔다)
  "30큐브 30×30×30cm": "30 cm cube 30×30×30cm",
  "45×30×30cm": "45×30×30cm",
  "60×30×36cm": "60×30×36cm",
  "60×45×45cm": "60×45×45cm",
  "90×45×45cm": "90×45×45cm",
  // 어항 종·크기 이름 (서버가 영어로 보내지만, 한국어 이름이 오면 여기서 번역한다. 백엔드 domain.json 과 같다)
  "어항 (담수 관상어·새우)": "Aquarium (freshwater fish and shrimp)",
  "새우 (체리·비 새우 등 소형 새우만 키울 때)": "Shrimp (cherry, bee and other dwarf shrimp only)",
  "나노 어종 (네온·엠버 테트라, 보라라스 등 성체 3cm 이하)": "Nano fish (neon and ember tetras, Boraras, etc.; adults up to 3 cm)",
  "소형 어종 (코리도라스·베타·구피 등 성체 7.5cm 이하, 몸높이 3cm 이하)":
    "Small fish (Corydoras, bettas, guppies, etc.; adults up to 7.5 cm long and 3 cm tall)",
  "합사 수조 (새우·나노·소형 어종을 함께 키울 때)": "Community tank (shrimp, nano and small fish kept together)",
  // 어항 출력 안전 안내 (AquariumPrintNotice: 설계하기·내려받기 화면)
  "어항에 넣을 출력물 안전 안내": "Print safety for aquarium pieces",
  "소재·노즐·채움·세척 조건을 지켜야 어항에 넣어도 위험이 낮아요. 아래 글에서 확인해 주세요.":
    "The risk in an aquarium stays low only if you follow the material, nozzle, infill and rinsing conditions. See the post below.",
  "근거와 자세한 설명: 커뮤니티 글 「어항에 3D 출력물, 수질 면에서 써도 될까요」":
    "Evidence and details: community post \"Are 3D prints safe for aquarium water?\"",
  // 가상 케이지는 케이지 종만 (가상 케이지·탐색의 배치 담기)
  "가상 케이지는 케이지에서 키우는 동물만 지원해요.": "The virtual cage only supports animals kept in cages.",
  "가상 케이지는 케이지에서 키우는 동물만 지원해요. 검토 기준 종·크기를 기본값으로 바꿨어요.":
    "The virtual cage only supports animals kept in cages, so the species and size used for checks were reset to the default.",
};

export default en;
