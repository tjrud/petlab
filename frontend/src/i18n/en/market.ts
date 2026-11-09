// 탐색 (공유 작품 목록·보기·올리기·3D 미리보기)
const en: Record<string, string> = {
  // 분류 (화면·서버 category_name_ko)
  "추천": "Recommended",
  "전체": "All",
  "은신처": "Hideout",
  "터널": "Tunnel",
  "경사로·계단": "Ramps & stairs",
  "모래목욕통": "Sand bath",
  "케이지 전체": "Whole cage",
  "가상 케이지 배치": "Virtual cage layout",
  "기타": "Other",

  // 파일 형식
  "SKP": "SKP",
  "3MF": "3MF",
  "STL": "STL",
  "NestForge 설계": "NestForge design",
  "SketchUp 모델": "SketchUp model",
  "3D 프린팅용 (슬라이서에서 열기)": "For 3D printing (open in a slicer)",
  "3D 프린팅용 메시": "Mesh for 3D printing",
  "파일 형식": "File formats",

  // 크기 이름 (배치 예시)
  "골든 (시리안)": "Golden (Syrian)",
  "드워프 (정글리안·캠벨·로보로브스키)": "Dwarf (Djungarian, Campbell's, Roborovski)",

  // 추천한 까닭 (서버 문구)
  "많이 내려받은 작품": "Popular download",
  "새로 올라온 작품": "Newly added",
  "3D로 보고 가상 케이지에 놓아 볼 수 있어요": "View in 3D and try it in your virtual cage",
  "내가 올린 작품": "Posted by you",
  "내 가상 케이지 배치와 비슷해요": "Similar to your virtual cage layout",
  "내 반려동물과 같은 종·크기의 배치예요": "A layout for your pet's species and size",
  "반려동물 케이지에 맞는 작품이에요": "A good fit for your pet's cage",
  "내 설계에 {name} 구조물이 있어요": "Based on {name} in your designs",
  "내 배치안에 {name} 있어요": "Based on {name} in your layouts",
  "자주 본 {name} 분류예요": "You often view {name}",

  // 목록
  "작품 목록을 불러오는 중이에요": "Loading items",
  "작품 목록을 불러오지 못했어요.": "Couldn't load items.",
  "분류": "Category",
  "SKP·3MF·STL 파일이나 가상 케이지 배치를 올려 주세요.": "Share SKP, 3MF or STL files, or a virtual cage layout.",
  "3D로 바로 볼 수 있는 작품과 많이 내려받은 작품, 새 작품을 골랐어요.": "Picked from items you can view in 3D, popular downloads and new uploads.",
  "내 설계·가상 케이지 배치안·반려동물·최근에 본 작품을 바탕으로 골랐어요.":
    "Picked based on your designs, virtual cage layouts, pets and recently viewed items.",
  "3D로 바로 볼 수 있는 작품, 많이 내려받은 작품, 새 작품 순이에요. 로그인하면 내 설계와 반려동물에 맞춘 추천이 보여요.":
    "Items you can view in 3D come first, then popular downloads, then new uploads. Log in for picks tailored to your designs and pets.",
  "아직 추천할 작품이 없어요.": "No recommendations yet.",
  "아직 올라온 작품이 없어요.": "Nothing has been shared yet.",
  "이 분류에는 아직 작품이 없어요.": "Nothing in this category yet.",
  "작품 {n}개": "{n} items",
  "내려받기 {n}": "{n} downloads",

  // 카드
  "공유 작품": "Shared item",
  "파일 받기 →": "Get files →",

  // 작품 보기
  "작품을 불러오는 중이에요": "Loading item",
  "작품을 불러오지 못했어요.": "Couldn't load this item.",
  "작품을 찾을 수 없어요": "Item not found",
  "주소가 잘못되었거나 지워진 작품이에요.": "The link is wrong or the item was deleted.",
  "탐색으로": "Back to Explore",
  "파일을 받지 못했어요. 잠시 뒤 다시 해 주세요.": "Couldn't download the file. Please try again in a moment.",
  "이 파일로는 이미지를 만들 수 없어요.": "Can't create an image from this file.",
  "대표 이미지를 만들지 못했어요.": "Couldn't create the cover image.",
  "담지 못했어요.": "Couldn't add it.",
  "가상 케이지에서 저장하지 않은 작업이 이 배치로 바뀌어요. 계속할까요?":
    "Your unsaved work in the virtual cage will be replaced by this layout. Continue?",
  "{name} (탐색)": "{name} (Explore)",
  "이 작품을 지울까요? 올린 파일도 함께 지워지고 되돌릴 수 없어요. 커뮤니티 소개 글은 남아요.":
    "Delete this item? Its files will be deleted too, and this can't be undone. The Community post will stay.",
  "지우지 못했어요.": "Couldn't delete it.",
  "{title} 미리보기": "{title} preview",
  "내려받기 {n}회": "{n} downloads",
  "3D 미리보기": "3D preview",
  "가상 케이지에 놓아 보기": "Try in virtual cage",
  "미리 볼 파일": "File to preview",
  "3D로 보기 ({size})": "View in 3D ({size})",
  "가상 케이지에 놓으면 지금 작업 중인 케이지의 빈 자리에 실제 크기로 들어가요. 저장은 가상 케이지에서 해요.":
    "It goes into an empty spot in the cage you're working on, at actual size. Save it from the virtual cage.",
  "대표 이미지 만드는 중…": "Creating cover image…",
  "이 3D 모습으로 대표 이미지 다시 만들기": "Recreate cover image from this 3D view",
  "이 3D 모습으로 대표 이미지 만들기": "Create cover image from this 3D view",
  "담는 중…": "Adding…",
  "내 가상 케이지로 담기": "Add to my virtual cage",
  "케이지 {w}×{d}×{h}mm": "Cage {w}×{d}×{h}mm",
  "담으면 내 배치안으로 저장되고 가상 케이지에서 바로 열려요.": "It's saved as your layout and opens right away in the virtual cage.",
  "담으면 가상 케이지에서 바로 열려요. 저장하려면 로그인하세요.": "It opens right away in the virtual cage. Log in to save it.",
  "파일": "Files",
  "{name} 케이지에 놓기": "Place {name} in cage",
  "케이지에 놓기": "Place in cage",
  "{name} 내려받기": "Download {name}",
  "내려받기": "Download",
  "SketchUp(SKP) 파일은 브라우저에서 3D로 볼 수 없어 3D 미리보기와 가상 케이지에서 쓸 수 없어요.":
    "SketchUp (SKP) files can't be viewed in 3D in the browser, so they can't be used in the 3D preview or virtual cage.",
  "올린 사람이 만든 파일이에요. NestForge 안전 검증을 거치지 않았으니 크기와 틈을 확인하고 쓰세요.":
    "These files were made by the uploader and haven't passed NestForge safety checks. Check sizes and gaps before use.",
  "커뮤니티 소개 글에서 댓글 보기 →": "See comments on the Community post →",
  "지우는 중…": "Deleting…",
  "작품 지우기": "Delete item",

  // 배치 그림
  "케이지 {w}×{d}mm 배치를 위에서 본 그림, 구조물 {n}개": "Top view of a {w}×{d}mm cage layout, {n} structures",

  // 올리기
  "올리기 화면을 준비하는 중이에요": "Preparing the upload form",
  "로그인하면 작품을 올릴 수 있어요": "Log in to post your work",
  "작품을 올릴": "post your work",
  "배치안을 불러오지 못했어요.": "Couldn't load the layout.",
  "올리지 못했어요.": "Upload failed.",
  "파일은 {n}개까지 올릴 수 있어요.": "You can upload up to {n} files.",
  "제목을 입력해 주세요.": "Please enter a title.",
  "소개를 입력해 주세요.": "Please enter a description.",
  "파일을 하나 이상 올려 주세요.": "Please upload at least one file.",
  "파일을 다 올린 뒤에 등록해 주세요.": "Please wait until all files are uploaded.",
  "작품을 올리지 못했어요. 다시 시도해 주세요.": "Couldn't post your item. Please try again.",
  "지금은 파일을 올릴 수 없어요. 가상 케이지 배치는 그대로 공유할 수 있어요.":
    "File uploads are unavailable right now. You can still share the virtual cage layout.",
  "지금은 파일을 올릴 수 없어요. 가상 케이지에서 저장한 배치는 '탐색에 공유'로 올릴 수 있어요.":
    "File uploads are unavailable right now. You can share saved layouts from the virtual cage with 'Share to Explore'.",
  "공유할 가상 케이지 배치": "Virtual cage layout to share",
  "구조물 {n}개": "{n} structures",
  "배치에 넣은 내 파일(STL·3MF)도 이 배치를 보는 사람이 3D로 볼 수 있게 공개돼요.":
    "Your files (STL, 3MF) in this layout will also be public so viewers can see them in 3D.",
  "불러오는 중…": "Loading…",
  "제목": "Title",
  "소개": "Description",
  "크기, 만든 프로그램, 출력 설정, 어떤 케이지에 맞는지 등을 적어 주세요.":
    "Describe the size, software used, print settings, which cages it fits, and so on.",
  "완성 파일": "Files",
  "(SKP·3MF·STL, 최대 {n}개, 파일당 {size})": "(SKP, 3MF, STL; up to {n} files, {size} each)",
  "3D 미리보기와 가상 케이지에는 STL·3MF가 필요해요. SKP만 있다면 STL로도 내보내 함께 올려 주세요.":
    "The 3D preview and virtual cage need STL or 3MF. If you only have SKP, export an STL too and upload both.",
  "완성 파일 고르기": "Choose files",
  "파일 고르기": "Choose files",
  "미리보기 이미지": "Preview image",
  "(선택 · PNG·JPG·WEBP)": "(Optional · PNG, JPG, WEBP)",
  "올린 3D 파일로 미리보기 이미지를 만드는 중이에요.": "Creating a preview image from your 3D file.",
  "고르지 않으면 올린 STL·3MF의 3D 모습으로 만들어 넣어요.": "If you don't choose one, we'll create it from your STL or 3MF in 3D.",
  "미리보기 이미지 고르기": "Choose preview image",
  "다른 이미지로 바꾸기": "Use a different image",
  "이미지 고르기": "Choose image",
  "커뮤니티에 소개 글도 올리기": "Also post to Community",
  "댓글은 소개 글에서 받아요.": "Comments are collected on the post.",
  "올리는 중…": "Posting…",
  "미리보기 만드는 중…": "Creating preview…",
  "파일 올리는 중…": "Uploading files…",
  "탐색에 올리기": "Post to Explore",
  "올림": "Uploaded",
  "3D 파일로 만든 이미지": "Image made from 3D file",
  "{name} 올리는 중": "Uploading {name}",
  "{name} 빼기": "Remove {name}",
  "빼기": "Remove",

  // 3D 미리보기
  "이 브라우저에서는 3D 미리보기를 볼 수 없어요. 파일을 내려받아 확인해 주세요.":
    "3D preview isn't available in this browser. Please download the file to view it.",
  "{name} 3D 미리보기": "{name} 3D preview",
  "가벼운 미리보기를 불러오지 못했어요.": "Couldn't load the lightweight preview.",
  "원본 3D 파일로 보기 ({size})": "View original 3D file ({size})",
  "3D 파일을 불러오지 못했어요. 내려받아 확인해 주세요.": "Couldn't load the 3D file. Please download it to view.",
  "3D 파일을 불러오는 중이에요 ({size})": "Loading 3D file ({size})",
  "끌어서 돌리고, 확대·축소할 수 있어요": "Drag to rotate, scroll to zoom",
  "끌어서 돌려 볼 수 있어요": "Drag to rotate",
};

export default en;
