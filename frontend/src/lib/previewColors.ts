// 3D 미리보기·가상 케이지·자동 대표 이미지가 함께 쓰는 색 (three.js 를 불러오지 않는 가벼운 모듈)

/** 밝은 쿨그레이 배경 (나무색 모델과 확실히 구분되게) */
export const PREVIEW_BG = "#eef1f4";
/** 채도를 조금 올린 나무색 */
export const MODEL_COLOR = "#c8874e";
/** 꺾인 모서리만 얇고 진하게 (곡면의 잔 삼각형 경계는 빼려고 25° 이상 꺾인 곳만) */
export const EDGE_STYLE = { color: "#3b2716", opacity: 0.55, thresholdDeg: 25 } as const;
/** 바깥 윤곽선 (화면 픽셀 두께) */
export const OUTLINE_STYLE = { color: "#3b2716", thickness: 1.6 } as const; // CSS 픽셀
