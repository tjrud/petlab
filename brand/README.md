# NestForge 로고 에셋

## 포함 파일
| 파일 | 용도 |
|---|---|
| `logo-on-light.svg` | **메인 로고**(심볼 + NestForge). 밝은 배경용. 글자가 도형이라 폰트 없이 그대로 표시됨 |
| `logo-on-dark.svg` | 메인 로고. 어두운 배경용 |
| `logo-on-light@2x.png`, `logo-on-dark@2x.png` | 메인 로고 투명 PNG(가로 1600px). 슬라이드·문서용 |
| `og-image.png` | 1200×630 링크 공유 미리보기 이미지 (흰 배경) |
| `fonts/Manrope-ExtraBold.ttf`, `fonts/OFL.txt` | 사이트에서 Manrope를 자체 호스팅할 때만 사용. 라이선스: SIL OFL |
| `logo-symbol.svg` | 심볼(큐브). 밝은 배경용 |
| `logo-symbol-on-dark.svg` | 심볼(큐브). 어두운 배경용 |
| `favicon.svg` | 파비콘(벡터, 둥근 사각형 배경 포함) |
| `favicon-32.png` | 파비콘 PNG 폴백 |
| `apple-touch-icon.png` | 180×180 홈 화면 아이콘 |
| `icon-512.png` | 512×512 앱/PWA 아이콘 |
| `logo-symbol-512.png`, `logo-symbol-on-dark-512.png` | 심볼 투명 PNG (슬라이드·문서용) |

## 색상
```css
:root {
  --nf-ink: #12302F;          /* 이름 글자 "Nest", 심볼 왼쪽 면 */
  --nf-teal: #2A7F79;         /* 심볼 오른쪽 면 */
  --nf-amber: #D9701A;        /* 심볼 윗면 (밝은 배경) */
  --nf-orange-text: #C25A0E;  /* 이름 글자 "Forge" (밝은 배경) */
  --nf-night: #0E2625;        /* 어두운 배경 */
  --nf-amber-on-dark: #F2A33A;/* 어두운 배경의 강조색 */
  --nf-paper: #F3F7F4;        /* 어두운 배경의 글자색 */
}
```

## 이름 글자(워드마크)
- 헤더에 로고를 그대로 넣을 때는 `logo-on-light.svg`(또는 `logo-on-dark.svg`)를 `<img>`로 쓰면 된다. 아래 HTML/CSS 조합은 글자를 텍스트로 직접 제어하고 싶을 때만 사용한다.
- 서체: Manrope ExtraBold(800), 자간 -0.03em
- "Nest"는 `--nf-ink`, "Forge"는 `--nf-orange-text` (어두운 배경: `--nf-paper` / `--nf-amber-on-dark`)
- 비율: 심볼 높이 = 글자 크기의 2배, 심볼과 글자 사이 간격 = 글자 크기의 약 0.36배

헤더 로고 예시 (심볼 40px, 글자 20px):
```html
<a class="nf-logo" href="/">
  <img src="/logo/logo-symbol.svg" alt="" width="40" height="40">
  <span class="nf-wordmark">Nest<span>Forge</span></span>
</a>
```
```css
.nf-logo { display: flex; align-items: center; gap: 7px; text-decoration: none; }
.nf-wordmark { font-family: 'Manrope', sans-serif; font-weight: 800; font-size: 20px;
  letter-spacing: -0.03em; line-height: 1; color: var(--nf-ink); }
.nf-wordmark span { color: var(--nf-orange-text); }
```

## HTML head 적용 예
```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
```

## 사용 규칙
- 밝은 배경에는 기본 파일, 어두운 배경에는 `on-dark` 파일을 쓴다.
- 색을 바꾸거나 가로세로 비율을 늘리지 않는다.
- 심볼 단독 사용은 24px 이상을 권장한다.
