// 가상 케이지: 내 파일, 상단 줄, 3D 화면, 배치 검토, 화면 위 도구 모음, 배치 검토 문구(lib/cageLayout.ts)
const en: Record<string, string> = {
  // 내 파일 (MyFilesSection)
  "로그인": "Log in",
  "하면 내가 올린 STL·3MF 파일을 케이지에 놓아 볼 수 있어요.": " to place STL and 3MF files you've uploaded in the cage.",
  "올리지 못했어요.": "Couldn't upload the file.",
  '"{name}" 파일을 지울까요? 이 파일을 놓아 둔 배치안에서도 보이지 않게 돼요.':
    'Delete "{name}"? It will also disappear from any layouts that use it.',
  "지우지 못했어요.": "Couldn't delete the file.",
  "케이지에 놓을 파일 올리기": "Upload a file to place in the cage",
  "올리는 중 {pct}%": "Uploading {pct}%",
  "STL·3MF 올리기": "Upload STL/3MF",
  "단위는 mm로 봐요.": "Units are read as mm.",
  "불러오는 중…": "Loading…",
  "아직 올린 파일이 없어요.": "You haven't uploaded any files yet.",
  "SketchUp 파일은 3D로 볼 수 없어요. SketchUp에서 STL로 내보내 올려 주세요.":
    "SketchUp files can't be shown in 3D. Export to STL from SketchUp and upload that instead.",
  "크기를 읽지 못한 파일이에요.": "Couldn't read this file's size.",
  "놓기": "Place",
  "놓을 수 없음": "Can't place",
  "지우기": "Delete",
  "내 파일": "My file",

  // 상단 줄 (PlannerHeader)
  "배치안 이름": "Layout name",
  "반려동물 종·크기 (검토 기준)": "Pet species and size (for review)",
  "햄스터": "Hamster",
  "골든 (시리안)": "Golden (Syrian)",
  "드워프 (정글리안·캠벨·로보로브스키)": "Dwarf (Djungarian, Campbell's, Roborovski)",
  "저장하지 않은 변경": "Unsaved changes",
  "새로 만들기": "New",
  "새 배치안으로 저장": "Save as new layout",
  "탐색에 공유": "Share to Explore",
  "저장 중…": "Saving…",
  "저장": "Save",
  "로그인하고 저장": "Log in to save",

  // 3D 화면 (PlannerScene)
  "가로 {w}mm · 앞": "Width {w}mm · Front",
  "세로 {d}mm": "Depth {d}mm",

  // 배치 검토 (ReviewPanel)
  "배치 검토": "Layout review",
  "오류 {n}": "Errors {n}",
  "경고 {n}": "Warnings {n}",
  "구조물이 차지한 바닥 면적 ÷ 케이지 바닥 면적": "Floor area taken by structures ÷ cage floor area",
  "바닥 사용 {pct}%": "Floor used {pct}%",
  "카탈로그에서 구조물을 고르면 케이지에 놓여요. 놓을 때마다 겹침·끼임 틈·출입구 앞 공간을 확인해요.":
    "Pick a structure from the catalog to place it in the cage. Each time, we check for overlaps, gaps that could trap your pet, and clear space in front of entrances.",
  "겹치거나 케이지 밖으로 나간 구조물이 없고, 끼임 틈과 출입구 앞 공간도 기준에 맞아요.":
    "No structures overlap or stick out of the cage, and gaps and entrance clearances meet the guidelines.",
  "오류": "Error",
  "경고": "Warning",
  "카탈로그에서 빠진 구조물 {n}개는 화면에 표시하지 않았어요.":
    "{n} structure(s) no longer in the catalog aren't shown.",
  "끼임 틈·출입구·높이 기준은 선택한 종·크기의 규칙을 따라요.":
    "Gap, entrance and height limits follow the rules for the selected species and size.",
  " 규칙은 아직 전문가 검수 전 임시값이에요.": " These rules are provisional and haven't been reviewed by experts yet.",
  "종별 기준을 불러오지 못해 겹침·케이지 밖·높이만 확인했어요.":
    "Couldn't load the species guidelines, so only overlaps, out-of-cage placement and height were checked.",
  "3D 프린팅용 구조물은 설계하기 화면에서 만들 수 있어요.": "You can make 3D-printable structures on the Design page.",

  // 화면 위 도구 모음 (SceneOverlay)
  "쿨그레이 (기본)": "Cool gray (default)",
  "크림": "Cream",
  "흰색": "White",
  "하늘": "Sky blue",
  "연두": "Light green",
  "회색": "Gray",
  "남색": "Navy",
  "검정": "Black",
  "시점": "View",
  "3D": "3D",
  "위에서": "Top",
  "정면": "Front",
  "켜면 빈 곳을 끌어 화면을 옮겨요(Shift를 누르고 끌면 돌려요). 끄면 돌리고, 오른쪽 버튼이나 Shift를 누르고 끌면 옮겨요":
    "When on, drag empty space to pan (Shift-drag to rotate). When off, drag to rotate; right-drag or Shift-drag to pan",
  "화면 이동": "Pan",
  "1cm 격자": "1cm grid",
  "벽·구조물에 붙이기": "Snap to walls and structures",
  "배경": "Background",
  "배경색": "Background color",
  "배경 {color}": "Background {color}",
  "직접 고르기": "Custom",
  "배경색 직접 고르기": "Pick a custom background color",
  "되돌리기 (Ctrl+Z)": "Undo (Ctrl+Z)",
  "되돌리기": "Undo",
  "다시 하기 (Ctrl+Shift+Z)": "Redo (Ctrl+Shift+Z)",
  "다시 하기": "Redo",
  "케이지 {w}×{d}×{h}mm · 구조물 {n}개": "Cage {w}×{d}×{h}mm · {n} structures",
  "구조물 끌기: 옮기기 · R 90° 회전 · Q/E 15° · 방향키 1cm(Shift 1mm) · Del 삭제":
    "Drag a structure: move · R rotate 90° · Q/E 15° · Arrow keys 1cm (Shift 1mm) · Del delete",
  "빈 곳 끌기: 화면 이동 · Shift 끌기: 돌려 보기 · 휠: 확대": "Drag empty space: pan · Shift-drag: rotate · Wheel: zoom",
  "빈 곳 끌기: 돌려 보기 · 오른쪽 버튼·Shift 끌기: 화면 이동 · 휠: 확대":
    "Drag empty space: rotate · Right-drag or Shift-drag: pan · Wheel: zoom",
  "구조물을 끌어서 옮기고, 두 손가락으로 화면을 옮기거나 확대해요": "Drag structures to move them. Use two fingers to pan or zoom",

  // 배치 검토 문구 (lib/cageLayout.ts). 영어는 조사 없이 이름만 넣어요
  "케이지 바닥 {w}×{d}cm가 최소 기준 {minW}×{minD}cm보다 작아요. 더 넓은 케이지를 권장해요.":
    "The cage floor ({w}×{d}cm) is smaller than the minimum of {minW}×{minD}cm. A larger cage is recommended.",
  "{a} 케이지 밖으로 나가 있어요.": "{a} is outside the cage.",
  "{a} 높이 {h}에 바닥재 {bed}를 더하면 케이지 높이 {cageH}보다 높아요.":
    "{a} ({h} tall) plus {bed} of bedding is taller than the cage height of {cageH}.",
  "{a} 높이 {h}가 케이지 높이 {cageH}보다 높아요.": "{a} ({h} tall) is taller than the cage height of {cageH}.",
  "{a} 벽 사이 틈({where})에 몸이 끼일 수 있어요. 벽에 붙이거나 {gap} 이상 띄워 주세요.":
    "Your pet could get stuck in the gap between {a} and the wall ({where}). Push it against the wall or leave at least {gap}.",
  "{side} 벽 {gap}": "{side} wall {gap}",
  "왼쪽": "left",
  "오른쪽": "right",
  "앞": "front",
  "뒤": "back",
  "{a}의 안지름 {w}가 이 아이에게 좁아요 (최소 {min}).": "The inner diameter of {a} ({w}) is too narrow for your pet (minimum {min}).",
  "{a}의 출입구 폭 {w}가 이 아이에게 좁아요 (최소 {min}).": "The entrance of {a} ({w} wide) is too narrow for your pet (minimum {min}).",
  "{a} 길이 {len}가 터널 권장 최대 길이 {max}보다 길어요. 독일 동물보호연맹은 플라스틱 튜브를 몸길이의 2배 이하로 권해요 (이 크기 구분에서 가장 작은 개체 기준).":
    "{a} ({len} long) is longer than the recommended maximum tunnel length of {max}. The German Animal Welfare Federation recommends plastic tubes no longer than twice the body length (based on the smallest animals in this size group).",
  "{a} 높이 {h}는 떨어지면 다칠 수 있어요 (권장 최대 {max}).": "{a} is {h} high, so a fall could cause injury (recommended maximum {max}).",
  "{a} 위와 천장 사이({gap})에 끼일 수 있어요. 더 낮은 구조물을 쓰거나 천장이 높은 케이지가 좋아요.":
    "Your pet could get stuck between the top of {a} and the ceiling ({gap}). Use a lower structure or a cage with a higher ceiling.",
  "{a} 출입구가 {n}개라 막다른 곳이 될 수 있어요. 출입구가 {min}개 이상인 은신처를 권장해요.":
    "{a} has only {n} entrance(s), so it could become a dead end. A hideout with at least {min} entrances is recommended.",
  "{a} 안쪽 {w}×{d}가 최소 기준 {minW}×{minD}보다 작아요.": "The inside of {a} ({w}×{d}) is smaller than the minimum of {minW}×{minD}.",
  "{a} 턱 {h}가 높아 넘어 들어가기 어려워요 (권장 최대 {max}).":
    "The rim of {a} ({h}) is too high to climb over easily (recommended maximum {max}).",
  "{a} {b} 겹쳐요.": "{a} and {b} overlap.",
  "{a} {b} 사이 틈 {gap}에 몸이 끼일 수 있어요. 붙이거나 {min} 이상 띄워 주세요.":
    "Your pet could get stuck in the {gap} gap between {a} and {b}. Push them together or leave at least {min}.",
  "{a}의 {side} 출입구 앞이 {b}에 막혀 있어요. 앞에 {min} 이상 비워 주세요.":
    "The {side} entrance of {a} is blocked by {b}. Leave at least {min} clear in front of it.",
  "{a}의 {side} 출입구 앞이 벽에 막혀 있어요. 앞에 {min} 이상 비워 주세요.":
    "The {side} entrance of {a} is blocked by the wall. Leave at least {min} clear in front of it.",
  "앞쪽": "front",
  "뒤쪽": "back",
};

export default en;
