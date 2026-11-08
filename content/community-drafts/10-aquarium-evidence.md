<!-- 상태: 근거자료 (커뮤니티 글 10 「어항에 3D 출력물, 수질 면에서 써도 될까요」 용). 조사·확인일 2026-11-08 -->
# 근거자료: 「어항에 3D 출력물, 수질 면에서 써도 될까요」

이 문서는 커뮤니티 글 `10-aquarium.md`의 문장마다 어떤 자료가 뒷받침하는지 정리한 것이다. 인용문은 원문 그대로 옮기고 줄바꿈만 공백으로 바꿨으며, 영어 인용에는 한국어 뜻을 붙였다.

조사 방법: 조사자 6명이 갈래별로 자료를 모았다(수생 독성, 물속 열화, 어항 실사용, 수질 화학·금속, 접착·코팅·레진 후처리, 반대 근거). 이를 하나로 정리한 뒤 검증자 3명이 출처를 다시 열어 인용을 대조했다. 주장 35건 가운데 18건은 그대로 확인됐고, 17건은 일부만 맞아 고쳐 썼다. 아래 내용은 모두 고친 판이다.

근거 강도 표시:
- **강함**: 원문으로 확인했고, 주장과 직접 맞으며, 같은 방향의 연구가 여럿 있다.
- **중간**: 원문으로 확인했지만 대상이나 조건이 다르다. 예를 들어 배아·실험실 생물이거나, 진한 추출 조건이거나, 연구가 1편뿐이다.
- **약함**: 판매자 주장, 개인 경험담, 2차 정보다.

---

## 0. 결론

> 어항에 넣어도 수질에 안전하다고 **증명된** 3D 출력 소재는 없다. 근거가 가리키는 방향은 소재마다 분명히 다르다.
> - 레진(광경화)은 넣지 않는다.
> - FDM은 무착색 PETG가 1순위다.
> - 담수라면 무착색 PLA도 조건부로 쓸 수 있다.
>
> 글에서는 "안전하다"가 아니라 "지금 근거로는 이 조건에서 위험이 낮아 보인다"고 쓴다.

햄스터 글(08·09)과의 관계:
- 08·09의 출발 조건은 같다. 무착색 PLA·PETG, 스테인리스 노즐, 두꺼운 벽과 100% 채움, 점검이다.
- 어항에서는 출력물이 24시간 물에 잠긴다. 그래서 조건이 더 붙는다. 레진을 빼고, PETG를 우선하고, 넣기 전에 물에 담가 두고, 수질을 지켜본다.
- 세척도 다르다. 08은 햄스터 용품 소독에 락스를 권했지만, 어항용 출력물은 물로만 씻으라고 했다. 층 사이 홈에 세제가 스며들었다가 나중에 나올 수 있기 때문이다(Prusa). 소독제 잔류가 수생생물에 미치는 영향은 따로 확인하지 않았다.

---

## 1. 한눈에 보기

| 글 문장 | 근거 | 강도 |
|---|---|---|
| 어항 수질에 안전하다고 증명된 3D 출력 소재는 없어요 | 아래 7절 "아직 모르는 것" 전체. PETG 자체의 수생 독성 시험, 관상 새우 시험, 1년 넘는 어항 시험, 출력물에서 어항 물로 녹아 나오는 금속을 잰 자료가 모두 없다 | 강함(부재 확인) |
| FDM 출력물 때문에 생물이 죽었다고 확인된 사례도, 오래 넣어 두고 무해함을 측정한 사례도 찾지 못했어요 | 조사 6갈래에서 찾지 못했다. Reddit·Reef2Reef 등의 사망 일화는 봇 차단 때문에 원문을 열지 못해 제외했다. 수조 ICP 검사 주장(3DReefing)은 수치가 공개되지 않았다(5절) | 중간(검색의 한계가 있음) |

---

## 2. 연구로 알게 된 것

### 2-1. 레진

- **글**: "레진 출력물을 우린 물에서 물벼룩은 72시간 안에 모두 죽었고, 물고기 배아의 24시간 생존율은 0~10%였어요(Zhu 2015)."
  - Zhu 2015 (Biomicrofluidics), https://pmc.ncbi.nlm.nih.gov/articles/PMC4691254/
    - "extracts from SLA polymers such as Watershed 11122XC, Dreve Fototec 7150 Clear, and VisiJet SL Clear resins were toxic to Daphnia sp. neonates. All of them induced 100% mortality after 24 h of exposure to aqueous extracts … both VisiJet Crystal and Form 1 Clear extracts did not induce any statistically significant mortality after 24 h of exposure. Their effects appeared to be delayed because by 48 h, the survival rate was ca. 50%, and all specimens were dead after 72 h"
      - 뜻: SLA 레진 3종의 추출액은 24시간 만에 물벼룩을 모두 죽였다. VisiJet Crystal과 Form 1 Clear는 효과가 늦게 나타났지만 72시간이 지나자 모두 죽었다.
    - "By 24 h, the embryo survival rate was ca. 10% for VisiJet Crystal and 0% for the remaining SLA polymers"
      - 뜻: 24시간째 배아 생존율은 VisiJet Crystal이 약 10%, 나머지 SLA 레진은 0%였다.
  - 강도: **강함**. 같은 방향의 연구가 여럿이다(Macdonald 2016, Oskui 2016, Walpitagama 2019). Formlabs Form 1 Clear처럼 소비자용에 가까운 레진도 포함됐다.
  - 한계:
    - 2015년 무렵의 산업·연구용 레진이다.
    - 22°C 어둠 속에서 최대 72시간 우려낸 실험실 추출액이다.
    - VisiJet Crystal은 SLA가 아니라 MJM 방식 레진이다.
- **글**: "굳지 않은 광개시제가 첫 24시간에 최대 200 mg/L 녹아 나왔어요(Walpitagama 2019)."
  - https://pubmed.ncbi.nlm.nih.gov/31226596/
    - "Migration of unpolymerized photoinitiator, 1-hydroxycyclohexyl phenyl ketone (1-HCHPK) from a plastic solid phase to aqueous media at up to 200 mg/L in the first 24 h was detected … Both plastic extracts (LC50 22.25% v/v) and 1-HCHPK (LC50 60 mg/L) induced mortality and teratogenicity within 48 h of exposure."
      - 뜻: 굳지 않은 광개시제가 첫 24시간에 최대 200 mg/L까지 물로 옮겨 갔다. 추출액과 광개시제 모두 48시간 안에 배아를 죽이거나 기형을 만들었다.
  - 강도: **중간~강함**. 초록으로만 확인했다.
- **글**: "UV 후경화로 독성이 크게 줄었다는 연구도 있지만(Oskui 2016), 에탄올로 씻어도 배아가 모두 죽은 레진이 있었어요(Macdonald 2016)."
  - Oskui 2016 (Environ Sci Technol Lett), https://doi.org/10.1021/acs.estlett.5b00249 (초록은 OpenAlex로 확인)
    - "We also developed a simple post-printing treatment (exposure to ultraviolet light) that largely mitigates the toxicity of the STL-printed parts."
      - 뜻: 출력 뒤 자외선을 쬐는 간단한 처리로 STL(레진) 출력물의 독성을 크게 줄였다.
  - 같은 데이터를 담은 미국 특허 US10201964B2, https://patents.google.com/patent/US10201964B2/en
    - "So while UV treatment appears to significantly reduce the toxicity of STL-printed parts to zebrafish, it does not completely eliminate the toxicity of these parts"
      - 뜻: UV 처리로 독성은 크게 줄지만 완전히 없어지지는 않는다.
  - Macdonald 2016 (Lab Chip), https://pmc.ncbi.nlm.nih.gov/articles/PMC4758231/
    - "While VisiJet Crystal still exhibited high toxicity (100% mortality occurred at 72 hours – Fig. 5), in Fototec 7150 polymer printed wells, washed with ethanol, embryos developed normally, had comparable viability (88% ± 7%), while unwashed wells were highly toxic."
      - 뜻: 에탄올로 씻은 Fototec 7150에서는 배아가 정상 발달했다(생존율 88%). 하지만 VisiJet Crystal은 똑같이 처리해도 72시간에 모두 죽었다.
  - 강도: **중간**.
  - 한계:
    - UV는 산업용 장비로 1시간 쬐었다.
    - 에탄올은 99% 농도에 담근 조건이다.
    - 가정의 짧은 IPA 세척이나 경화기와는 다르다.
  - 참고(글에서는 뺐다):
    - 의료용 생체적합 인증 레진(USP Class VI인 VisiJet Crystal, 의료기기 Class IIa인 E-Shell 300)도 배아에 독했다(Macdonald 2016; https://pmc.ncbi.nlm.nih.gov/articles/PMC9031839/).
    - E-Shell 300은 우린 물에서는 독성이 거의 없었다. 그런데 배아가 표면에 직접 닿으면 최대 79%가 죽었다. 우린 물만 검사하면 표면 접촉 독성을 놓칠 수 있다는 뜻이다.

### 2-2. PLA·ABS

- **글**: "우린 물에서 물고기 배아·치어는 72시간, 윤충·물벼룩류는 24시간 시험에서 괜찮았어요(Zhu 2015)."
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC4691254/
    - "100% of zebrafish embryos exposed to ABS and PLA extracts survived and developed normally for up to 72 h"
      - 뜻: ABS·PLA 추출액에 노출된 배아는 72시간까지 모두 살아 정상 발달했다.
    - "Leachates from ABS and PLA did not induce any behavioural abnormalities"
      - 뜻: 치어의 행동에도 이상이 없었다.
    - "Acute toxicity tests with the rotifer Brachionus calyciflorus revealed 100% mortality in response to all leachates apart from PLA, ABS, and VisiJet Crystal. The latter were not toxic to rotifers over the standard exposure time of 24 h"
      - 뜻: 윤충은 PLA·ABS(그리고 VisiJet Crystal)를 뺀 모든 추출액에서 죽었다. PLA·ABS는 24시간 시험에서 독성이 없었다.
    - "Acute toxicity tests over 24 h with the freshwater crustacean Ceriodaphnia dubia provided statistically similar results to those obtained on rotifers"
      - 뜻: 물벼룩류(Ceriodaphnia) 24시간 시험도 윤충과 통계적으로 같은 결과였다.
    - 조건: "3D printed structures with a total surface area of 25 000 mm 2 were placed in a glass flask filled with 500 ml … The leachate extraction was performed in darkness at 22 °C for up to 72 h."
      - 뜻: 출력물 표면 25,000 mm²를 물 500 mL에 넣고 22°C 어둠 속에서 최대 72시간 우렸다.
  - 강도: **중간**.
  - 한계:
    - 물 양에 비해 출력물 표면이 매우 넓은 진한 단기 조건이다.
    - 출력한 프린터 이름(MakerBot Replicator 2, Stratasys uPrint SE)만 나오고 필라멘트 브랜드나 색은 나오지 않는다.
    - 큰물벼룩(Daphnia magna)에 대한 PLA·ABS 결과는 본문에 따로 없다.
- **글**: "투명 PLA 그릇에 배아를 직접 넣어도 7일 생존율이 대조군과 같았어요(Pérez-Davila 2022)."
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC9572917/
    - "These similar results in both controls proved, in the first place, that PLA C itself had no effect on the hatching or survival rates."
      - 뜻: 두 대조군(PLA 없음, 처리 안 한 PLA)의 결과가 같았으므로, PLA 자체는 부화율과 생존율에 영향이 없었다.
    - "deposited in direct contact within these PLA samples"
      - 뜻: 배아를 PLA 시료에 직접 닿게 넣었다.
    - "the survival larvae determined after 178 h (7 days)"
      - 뜻: 생존은 7일째에 쟀다.
    - 시료: "Infill density 100%", "Ingeo™ PLA 3D850 by NatureWorks, was purchased from Smart Materials 3D", "The material turned from transparent to white in the PLA SS samples"
      - 뜻: 채움 100%로 출력했고, 필라멘트는 NatureWorks의 Ingeo 3D850 수지로 만든 Smart Materials 3D 제품이다. 원래 투명했다(멸균 처리한 시료만 하얗게 변했다).
  - 강도: **중간**.
  - 한계:
    - PLA 한 제품, 배아·치어 단계만 봤고, 몸 모양은 72시간째까지만 봤다.
    - 수질은 재지 않았다.
    - 연구 목적은 의료기기 멸균법 비교였다.
- **글**: "하지만 같은 우린 물이 민물 미세조류 성장을 50% 가까이 억제했고(Zhu 2015)"
  - "Poly(lactic) acid and acrylonitrile butadiene styrene despite their perceived safety induced nearly 50% growth inhibition after 96 h of exposure."
    - 뜻: 안전하다고 여겨지는 PLA·ABS도 96시간 노출에서 미세조류 성장을 50% 가까이 억제했다.
  - 강도: **중간**. 연구 1편, 조류 1종(Pseudokirchneriella subcapitata)이다.
  - 한계: 원인 물질은 밝혀지지 않았다. 물이 훨씬 많은 어항의 수초나 산호 공생조류에서도 의미가 있는지는 모른다.
- **글**: "산업용 ABS 출력물에 배아가 직접 닿자 심장 부종이 늘었어요(Oskui 2016)."
  - 특허 US10201964B2: "FDM-exposed embryos still had deformities at a rate higher than unexposed control embryos (especially for yolk sac edema) and a statistically significant increase (p ≤0.05) in heart edema"
    - 뜻: FDM 출력물에 노출된 배아는 대조군보다 기형이 많았다(특히 난황 부종). 심장 부종은 통계적으로 유의하게 늘었다.
  - 강도: **중간**.
  - 한계:
    - Stratasys Dimension Elite로 뽑은 ABS 1종이다.
    - 서포트를 녹이려고 2% 수산화나트륨에 4시간 담갔다.
    - 원판 하나를 물 약 45 mL에 넣은 진한 조건이다.

### 2-3. 해수

- **글**: "PETG와 비슷한 코폴리에스터, PLA/PHA로 출력해 해수에 1주 길들인 타일에서 산호 유생이 정착해 12주 동안 소재 간 차이 없이 자랐고, 크로미스 행동도 그대로였어요(Ruhl·Dixson 2019). 출력물끼리만 비교했고 수질은 재지 않았어요."
  - Ruhl & Dixson 2019 (PLOS ONE), https://doi.org/10.1371/journal.pone.0221157 · https://pmc.ncbi.nlm.nih.gov/articles/PMC6697346/
    - "Two Colorfabb co-polyester based filaments were chosen for their durability (hereafter nGen and XT); a Colorfabb PLA/PHA filament … and a Proto-Pasta PLA filament … incorporation of stainless-steel shavings … All 3D printed models were conditioned in seawater for one-week prior to use."
      - 뜻: colorFabb 코폴리에스터 2종(nGen, XT), colorFabb PLA/PHA, 스테인리스 가루가 든 Proto-Pasta PLA를 썼고, 모두 해수에 1주일 길들인 뒤 사용했다.
    - "C. viridis did not discriminate or display modified behaviors between 3D printed and natural coral skeletons or between 3D printed materials."
      - 뜻: 크로미스는 출력물과 진짜 산호 골격, 그리고 출력 소재끼리를 가리지 않았고 행동도 달라지지 않았다.
    - "growth and mortality of P. astreoides settled on different 3D printed surfaces did not significantly differ."
      - 뜻: 출력 소재가 달라도 산호의 성장률과 사망률에 유의한 차이가 없었다.
    - "no treatments containing non-3D printed materials were included."
      - 뜻: 출력하지 않은 소재는 비교군에 넣지 않았다.
    - "As rates of degradation or chemical leaching of 3D printed models has not been well documented under environmental conditions"
      - 뜻: 실제 환경에서 출력물이 분해되거나 물질이 우러나는 속도는 잘 밝혀지지 않았다.
  - 강도: **중간~약함**.
  - 한계:
    - 12주 생존율은 21%(nGen)~48%(SS)였다.
    - 정착 단계는 인공해수 200 mL에 타일 하나를 넣고 14일 동안 진행했다. 성장 단계는 380 L 수조였다.
    - 물고기는 수 분~하루 동안의 서식처 선택만 봤고, 건강이나 독성 지표는 재지 않았다.
    - SPS 같은 민감한 산호와 새우는 다루지 않았다.
  - 참고(글에서는 뺐다):
    - Uribe-Echeverría & Beiras 2022(https://doi.org/10.1016/j.marenvres.2022.105605): "PLA cups and PLA/PHA filament were innocuous for the larvae"
      - 뜻: PLA 컵과 PLA/PHA 필라멘트를 우린 물은 성게 유생에게 해가 없었다.
      - 초록만 확인했고, 출력물이 아닌 필라멘트로 한 시험이다.

### 2-4. 한계

- **글**: "대부분 물에 비해 출력물이 아주 많은 진한 조건의 며칠~12주 시험이에요. PETG 자체, 관상 새우, 1년 넘는 어항 시험은 없어요."
  - 조건은 위 인용 참고: Zhu 2015는 표면 25,000 mm²에 물 500 mL를 썼고, Oskui 2016은 원판 하나에 물 45 mL를 썼다.
  - 시험 기간은 대부분 24시간~7일이고, 가장 긴 것이 산호 12주다.
  - "없다"는 7절에 정리했다.

---

## 3. 물속에서 소재는

- **글**: "PLA는 25°C 물에서 1년 동안 거의 분해되지 않았어요(Bagheri 2017)."
  - Bagheri 2017 (Global Challenges), https://pmc.ncbi.nlm.nih.gov/articles/PMC6607129/
    - "The degradation studies were carried out in SW and FW under controlled conditions in a thermostatic chamber at 25 °C … for 1 year. The water was refreshed every 2 weeks."
      - 뜻: 25°C 해수와 담수에서 1년 동안 시험했고, 물은 2주마다 갈았다.
    - "All other so‐called (bio)degradable polymers (PCL and PLA) did not show any significant degradability under tested conditions. Degradation rates of polymers were relatively same in FW and SW"
      - 뜻: PLA는 의미 있는 분해를 보이지 않았고, 담수와 해수의 차이도 거의 없었다.
  - 강도: **강함**. 같은 방향의 연구가 더 있다.
    - Deroine 2014: 25°C에서 6개월 동안 겉모습이 그대로였다.
    - Royer 2023: PLA 섬유가 바다에서 428일 넘게 분해되지 않았다(https://pmc.ncbi.nlm.nih.gov/articles/PMC10208507/).
  - 한계: 시료는 두께 320 µm 필름이었다. 생물막이 있는 실제 어항에서 시험한 것이 아니다.
- **글**: "약점은 온도라, 30°C 증류수 6개월에 연신율이 42%, 40°C에선 강도가 85% 줄었어요(Deroine 2014)."
  - Deroine 2014 (Polymer Degradation and Stability), https://archimer.ifremer.fr/doc/00173/28376/26689.pdf
    - "at 30°C, the increase in failure strain is significant after 1 month of immersion (+47%) but drops after 6 months (-42%). After 6 months at 40°C, the stress and the strain at break were greatly reduced, -85 and -92% respectively"
      - 뜻: 30°C에서 6개월 뒤 파단 연신율이 42% 줄었고, 40°C에서 6개월 뒤 파단 강도와 연신율이 각각 85%, 92% 줄었다.
  - 강도: **강함**(온도에 따라 열화 속도가 달라진다는 점).
  - 같은 방향의 자료:
    - 출력한 PLA는 50°C 물에서 58일 만에 열화됐다(Stevens).
    - 21°C에서는 거의 변하지 않았고 70°C에서는 7일 만에 크게 열화됐다(Banjo 2022).
  - 히터 접촉 금지: Fluval 히터 설명서는 "Be sure there are no rocks, decorations or gravel obstructions touching the heater"라고 쓴다.
    - 뜻: 돌, 장식물, 자갈이 히터에 닿지 않게 하라.
    - 이유는 히터 유리관 보호다(https://fluvalaquatics.com/ca/manuals/14880-4_T-Heater_Manual_NA_May7_21_AP_WEB.pdf).
    - 히터 표면 온도를 잰 자료는 없다.
- **글**: "양식용 순환여과 장치에선 일부러 넣은 PLA를 세균이 먹이로 썼어요(Zhao 2024)."
  - https://pubmed.ncbi.nlm.nih.gov/39245379/
    - "A uniquely designed and 3D printed poly (lactic acid) (PLA) structure was applied as carbon source. … Steady water quality was observed throughout the experiment period."
      - 뜻: 3D 출력한 PLA 구조물을 탄소원으로 넣었고, 실험 내내 수질은 안정적이었다.
    - "Subtilisin was one important PLA degrading enzymes in the system."
      - 뜻: 이 시스템에서는 PLA를 분해하는 효소(subtilisin)가 확인됐다.
  - 강도: **중간**. 초록만 확인했다.
  - 한계: 일부러 만든 탈질 장치였고, 해를 보였다는 근거가 아니다. 리프 수조의 PLA가 뜻하지 않은 탄소원이 된다는 것은 추론이다.
- **글**: "출력한 PETG는 8~9주 담가도 무게가 약 0.3% 늘었고 PLA는 2.5% 늘었어요(Moreno Nieto 2021)."
  - Moreno Nieto 2021 (Polymers), https://pmc.ncbi.nlm.nih.gov/articles/PMC8036839/
    - "PETG specimens became stable in all three solutions, with subtle weight changes round 0.3% after 9 weeks, whereas PLA samples mean weight increase was 2.5% after 8 weeks."
      - 뜻: PETG는 세 용액 모두에서 9주 뒤 무게 변화가 약 0.3%로 안정됐고, PLA는 8주 뒤 평균 2.5% 늘었다.
  - 강도: **중간**.
  - 한계:
    - 재활용 필라멘트를 썼다.
    - 세 용액은 증류수, 포화 소금물, 포화 설탕물이었고, 해수는 아니었다.
    - 다른 연구(Bedi 2026)에서는 측정 방법과 채움에 따라 흡수율이 5~39%까지 달랐다.
- **글**: "나일론·우드 PLA는 물을 많이 먹고 크게 약해졌어요(Banjo 2022, Islam 2026)."
  - Banjo 2022 (Composites Part C), https://doi.org/10.1016/j.jcomc.2022.100243
    - "the nylon-based materials absorbed up to 10 times more water than PLA … with the flexural modulus of nylon decreasing by as much as 60% after 7 days of immersion."
      - 뜻: 나일론 계열은 PLA보다 물을 최대 10배 흡수했고, 7일 만에 굽힘 강성이 최대 60% 떨어졌다.
  - Islam 2026 (Materials Science in Additive Manufacturing), https://doi.org/10.36922/MSAM026190041
    - "PLA-Wood absorbed approximately 50% apparent moisture in compression specimens and suffered a 57% flexural strength reduction."
      - 뜻: 우드 PLA는 겉보기 수분을 약 50% 흡수했고 굽힘 강도가 57% 떨어졌다.
    - 같은 논문에서 "PETG maintained stable wet-state tensile strengths"
      - 뜻: PETG는 젖은 상태에서도 인장강도를 안정적으로 유지했다.
  - 강도: **강함**(물성 저하).
  - 한계: 독성에 대한 근거가 아니라 물러지고 약해지는 문제다. 실크·야광·금속·카본 혼합 필라멘트의 물속 자료는 찾지 못했다.
- **글**: "PLA 미세입자는 실험에서 물고기 장을 다치게 하고 물벼룩 생존을 떨어뜨렸어요."
  - Duan 2022, https://pubmed.ncbi.nlm.nih.gov/35114456/
    - "PLA MPs were more actively ingested by fish than PET MPs. … The ingestion of PLA MPs caused gastrointestinal damage in zebrafish."
      - 뜻: 물고기는 PET 미세입자보다 PLA 미세입자를 훨씬 많이 먹었고, PLA 입자를 먹은 제브라피시는 위장관이 손상됐다.
  - Zimmermann 2020, https://pubmed.ncbi.nlm.nih.gov/32871484/
    - "PLA reduced survival most effectively. … effects of PUR and PLA plastics were induced by the mere particle."
      - 뜻: PLA가 물벼룩 생존을 가장 크게 떨어뜨렸고, 그 영향은 첨가 화학물질이 아니라 입자 자체 때문이었다.
  - 강도: **중간**.
  - 한계: 일부러 갈아 만든 입자를 넣은 실험이다(물벼룩은 10~500 mg/L). 멀쩡한 출력물이 어항에서 이만큼 입자를 내놓는다는 측정은 없다. 그래서 교체 조건의 근거로만 쓴다.
  - 반대 방향 자료:
    - 산호(Pocillopora damicornis)는 PLA 미세입자 5~50 mg/L에 72시간 노출돼도 죽거나 백화되지 않았다(https://pubmed.ncbi.nlm.nih.gov/41980291/, 2026).
    - 최고 농도에서는 항산화 효소만 늘었다.
- **글**: "\"해수의 알칼리성이 PLA를 빨리 녹인다\"는 근거가 약해요. 40°C 시험에선 해수 쪽이 오히려 느렸어요(Deroine 2014). 그래도 칼크바서 같은 강알칼리 용액에 닿는 부품엔 PLA를 쓰지 않는 게 안전해요."
  - Deroine 2014
    - "At 40°C, the stress at break of PLA decreases significantly after 6 months' immersion but with a larger reduction in distilled water (85% versus 70% in seawater)."
      - 뜻: 40°C에서 파단 강도는 증류수에서 85%, 해수에서 70% 줄었다.
    - "the degradation rate is faster in distilled water than in seawater."
      - 뜻: 분해는 해수보다 증류수에서 빨랐다.
    - 연구진은 그 이유를 pH가 아니라 염분이 물의 확산을 줄이기 때문으로 보았다.
  - 통념의 출처로 보이는 QIDI 블로그(https://qidi3d.com/blogs/print-lab/is-pla-safe-aquariums): "alkalinity roughly doubles PLA's rate of strength loss"
    - 뜻: 알칼리도가 PLA 강도 손실 속도를 대략 두 배로 만든다.
    - 이 글이 근거로 든 것은 37°C, pH 10에서 PLA 섬유를 시험한 연구다. 리프 수조(pH 8.0~8.4, 25°C 안팎)와는 조건이 다르다.
  - 강알칼리에서는 실제로 빠르다:
    - 0.1 M 수산화나트륨에서는 PLA 표면이 6일 만에 깎여 나갔다(https://pmc.ncbi.nlm.nih.gov/articles/PMC9890945/).
    - pH 10에서는 25일 동안 질량 감소가 계속 늘었다(https://pmc.ncbi.nlm.nih.gov/articles/PMC8706057/).
  - 칼크바서 권고는 직접 시험한 자료가 없는 예방 차원의 추론이다. 글에서도 "쓰지 않는 게 안전해요"로 썼다.
  - 강도: **중간**.

---

## 4. 금속

- **글**: "미국 EPA의 해수 구리 만성 기준은 3.1 µg/L이고, 물달팽이 새끼는 1.8 µg/L에서 성장이 20% 줄었어요(Brix 2011)."
  - EPA 권고 수질 기준표, https://www.epa.gov/wqc/national-recommended-water-quality-criteria-aquatic-life-criteria-table
    - 구리 행: "Copper (P) 7440508 — — 4.8 3.1 2007 Freshwater criteria calculated using the Biotic Ligand Model."
    - 뜻: 해수 용존 구리 기준은 급성 4.8 µg/L, 만성 3.1 µg/L다. 민물 기준은 수질 값을 넣어 계산하는 모델(BLM)로 정한다.
  - Brix 2011, https://pubmed.ncbi.nlm.nih.gov/21723419/
    - "in a 30-day chronic exposure using juvenile snails an EC20 of 1.8μg L(-1) Cu was estimated for snail growth making L. stagnalis the most sensitive organism tested to date for Cu."
      - 뜻: 어린 물달팽이를 30일 노출하자 구리 1.8 µg/L에서 성장이 20% 줄었다. 당시까지 시험한 생물 가운데 구리에 가장 민감했다.
  - 강도: **강함**(독성 잣대로서).
  - 한계:
    - 같은 논문에서 급성 반수치사농도는 31 µg/L로 '보통' 수준이었다. 민감한 것은 만성 노출이다.
    - 관상 새우(Neocaridina·Caridina)의 동료심사 치사농도는 찾지 못했다.
    - 이 값들은 얼마부터 해로운지를 보여 주는 잣대일 뿐, 출력물이 구리를 이만큼 내놓는다는 증거가 아니다.
  - 참고(글에서는 뺐다):
    - 산호 Acropora aspera는 구리 5.8 µg/L에서 수정 성공률이 10% 떨어졌다(https://pubmed.ncbi.nlm.nih.gov/28704691/).
    - Seachem 구리 치료제 안내: "Remove all invertebrates - these are extremely sensitive to copper"(https://www.seachem.com/cupramine.php)
      - 뜻: 무척추동물은 구리에 매우 민감하므로 모두 빼라.
- **글**: "필라멘트 속 금속량은 색·브랜드마다 달랐고, 투명 필라멘트도 출력 뒤엔 구리가 나왔어요(Beard 2026). 무착색은 정체 모를 안료·첨가제를 줄이는 예방책이지 구리가 없다는 보증은 아니에요."
  - Beard 2026, https://pmc.ncbi.nlm.nih.gov/articles/PMC13488613/
    - "Six metals (aluminum, magnesium, manganese, chromium, iron, and copper) were found in nonmetal filaments depending on polymer type, color, and brand"
      - 뜻: 금속을 넣지 않은 필라멘트에서도 금속 6종이 검출됐고, 그 양은 소재, 색, 브랜드에 따라 달랐다.
    - 표 1: 투명 ABS의 압출 뒤 구리는 86.7 ng/mg이었다. 투명 필라멘트 4종의 압출 뒤 구리는 13.3~86.7 ng/mg으로, 검정·파랑(7.85~41 ng/mg)보다 적지 않았다.
  - Prusa, https://help.prusa3d.com/article/food-safe-fdm-printing_112313
    - "Natural/pure PETG-filament without any color, would be your best bet, but it's hard to say exactly what is in it."
      - 뜻: 색을 넣지 않은 순수 PETG가 가장 낫지만, 그 안에 무엇이 들었는지는 정확히 말하기 어렵다.
  - 강도: **중간**(함량 측정).
  - 한계: 필라멘트 속 함량만 쟀고, 물로 녹아 나오는 양은 재지 않았다. 검증자가 원래 주장("무착색이면 구리가 적다")을 표 1의 수치로 반박했고, 그래서 글을 "보증은 아니에요"로 고쳤다.
- **글**: "황동 노즐 출력물을 50°C 물에 우리면 강철 노즐보다 납이 7~12배 나왔지만, 1 g당 1~1.5 ng으로 아주 적었고 구리는 검출되지 않았어요(Rindelaub 2019)."
  - Rindelaub 2019 (PLOS ONE), https://pmc.ncbi.nlm.nih.gov/articles/PMC6530847/
    - "The devices printed using the brass nozzle had 7–12 times greater concentrations of Pb compared to those printed using a steel nozzle."
      - 뜻: 황동 노즐로 뽑은 출력물은 강철 노즐로 뽑은 것보다 납 농도가 7~12배 높았다.
    - 표: 황동 노즐 출력물의 납은 1.46, 0.98, 1.08 ng/g이었다(FDA PLA, 열처리한 FDA PLA, PC). 강철 노즐 출력물은 0.13, 0.11 ng/g이었다(PLA, PETG).
    - "Of the 15 elements targeted by ICP/MS analysis …, only lead (Pb) was observed in the printed device extracts."
      - 뜻: 대상 원소 15종 가운데 추출액에서 나온 것은 납뿐이었다(구리 포함).
    - 추출 조건: ">72 hours at 50°C, as recommended by ISO 10993–12"
      - 뜻: ISO 10993-12 권고에 따라 50°C에서 72시간 넘게 우렸다.
  - 강도: **중간**.
  - 한계:
    - 노즐마다 다른 소재와 색을 썼다(황동: 빨강 FDA PLA·투명 PC, 강철: 흰 PLA·노랑 PETG). 그래서 완전한 비교가 아니다.
    - 구리 검출 한계는 본문에서 확인하지 못했다.
    - 어항 조건이 아니라 의료기기 추출 조건이다.

---

## 5. 실제로 쓰는 곳

- **글**: "해외 리프 용품 업체는 대체로 PETG로 출력해요(Charterhouse는 40여 종 전부). PLA도 괜찮다는 업체도 있어요. \"reef-safe\"는 시험 자료를 공개하지 않은 판매자 주장이에요."
  - Reef Builders, https://reefbuilders.com/2023/10/24/charterhouse-aquatics-provides-3d-printed-product-solutions
    - "It already lists over 40 own-branded products … and all are made from reef-safe PETG plastic."
      - 뜻: 자체 브랜드 제품 40종 넘게가 모두 PETG로 만들어졌다.
  - 같은 방향의 업체:
    - Clear Choice Aquatics: 프래그 플러그를 속을 꽉 채운 PETG로 출력한다.
    - Copper Coast: 낮은 흡수율과 내화학성을 이유로 PETG를 쓴다.
    - Rhino's Reef: "For anything that lives in your tank we use PETG, never PLA or resin"
      - 뜻: 수조 안에 들어가는 것에는 PETG만 쓰고, PLA나 레진은 절대 쓰지 않는다.
      - 그런데 같은 페이지에서 '색소 없음'과 '색상 선택'을 함께 내세운다.
  - 다른 의견: Aqua Print UK 인터뷰, https://reefbuilders.com/2023/02/10/faqs-on-3d-printing/
    - "There are quite a few materials that are reef safe, ABS/PETG/PLA/TPU but it all depends on what's done during the manufacture of each material. We use mostly PETG."
      - 뜻: ABS, PETG, PLA, TPU 등 리프에 쓸 수 있는 소재는 꽤 많지만, 모두 각 소재를 어떻게 만들었느냐에 달렸다. 우리는 주로 PETG를 쓴다.
  - 강도:
    - 업계 관행에 대한 근거로는 **중간**이다.
    - 안전성에 대한 근거로는 **약함**이다. 용출 시험 자료를 공개한 업체는 없다.
  - 참고(글에서는 뺐다):
    - Siddament는 형광 녹색 PETG를 "Created for Fish Tanks"라는 이름으로 판다. 하지만 같은 페이지에 "SDS / RoHS / REACH documents are not currently issued for this line."이라고 적혀 있다(https://siddament.com.au/products/electric-green-petg).
      - 뜻: 이 제품군에는 안전보건자료, RoHS, REACH 문서를 아직 발행하지 않았다.
    - 리프 구조물 설계자 3DReefing은 이렇게 쓴다(https://www.printables.com/model/1205179-3dreefing-frag-scape-system-for-reef-tanks): "tested this design extensively for over a year, including tank MS ICP tests … no abnormal leaching of contaminants", "ONLY USE PETG!"
      - 뜻: 수조 ICP-MS 검사를 포함해 1년 넘게 시험했고 이상 용출이 없었다. PETG만 쓰라.
      - 수치, 브랜드, 대조군은 공개하지 않았다. 사업상 이해관계("My company, 3DReefing")가 있다.
      - 글자 수 때문에 글에서는 뺐다. '넣기 전후 ICP 검사 비교' 권고는 이 사례와 산호의 구리 민감성에서 끌어냈다.
- **글**: "380 L 담수 수조에 코팅한 PLA와 PETG 출력물을 7개월 넣었는데 PLA가 멀쩡했다는 경험담이 있어요(Prusa 포럼). 수질 측정은 없어요."
  - https://forum.prusa3d.com/forum/english-forum-general-discussion-announcements-and-releases/which-plastic-for-aquarium-use/
    - "I have a 100 gallon freshwater setup. I used PLA and PETG and coated the former with either Modge Podge Matt sealer or Plasti Dip spray. … I have had no degradation of my PLA pieces since October 2019 when they were installed."
      - 뜻: 100갤런 담수 수조에 PLA와 PETG를 썼고, PLA는 Mod Podge나 Plasti Dip으로 코팅했다. 2019년 10월에 넣은 뒤로 PLA는 열화되지 않았다.
    - 글은 2020년 5월에 올라왔으므로 약 7개월이다. 100 US갤런은 약 378.5 L다.
  - 같은 방향의 경험담: makerbot-users 그룹(2015) "PLA fish houses … in my freshwater aquarium for about a year now and it seems just as strong"(https://groups.google.com/g/makerbot-users/c/sY9javWl7iA)
    - 뜻: 담수 어항에 PLA 은신처를 약 1년 넣어 두었는데 처음처럼 튼튼하다.
  - 강도: **약함**(개인 경험담).
- **글**: "레진 회사 Formlabs 직원은 물고기 수조엔 자사 레진을 권하지 않았어요."
  - https://forum.formlabs.com/t/materials-for-water/40323
    - "while our resins are watertight, I wouldn't recommend using them to print an aquarium that houses fish. Any 3D printed resins can leach chemicals over time"
      - 뜻: 우리 레진은 물이 새지 않지만, 물고기가 사는 수조를 출력하는 데는 권하지 않는다. 3D 출력한 레진은 시간이 지나며 화학물질이 우러날 수 있다.
  - 답변자의 직함은 'Formlabs Marketing Manager, Form Now'다. 소재 전문가는 아니다.
  - Formlabs Clear V4.1 안전보건자료(경화 전): "H411 Toxic to aquatic life with long lasting effects"
    - 뜻: 장기적 영향으로 수생생물에 유독하다.
  - 강도: **중간**. 자기 회사 제품 사용을 말리는 발언이다.
  - 참고(글에서는 뺐다):
    - 미국 해양대기청(NOAA)의 산호 프로그램은 이렇게 썼다(https://formlabs.com/blog/how-noaa-uses-sla-sls-3d-printers-for-coral-research/): SLA 부품은 "require time intensive post-curing to make them suitable for use with marine organisms"
      - 뜻: 해양 생물과 함께 쓰려면 시간이 많이 드는 후경화가 필요하다.
      - 그래서 많은 부품을 소결 나일론 12로 만들었다. 다만 후경화한 SLA 하우징을 수중 교반기에 쓰기도 했다.
    - 산호 복원 현장의 소재: Reef Design Lab(MARS)은 세라믹을 쓴다. "Ceramic has proved to be one of the best materials for artificial reef use"(https://www.dezeen.com/2015/03/06/alex-goad-mars-modular-artificial-reef-structure-restore-damaged-coral-reefs/)
      - 뜻: 세라믹은 인공어초에 가장 좋은 소재 가운데 하나로 드러났다.
      - Archireef와 바일란대는 테라코타를 쓴다. 플라스틱과 직접 비교한 시험은 없다.

---

## 6. 조건

| 글의 조건 | 근거 | 강도 |
|---|---|---|
| 무착색 PETG 1순위 | 물 흡수가 적다(Moreno Nieto 2021). 업계 관행이다(5절). 비슷한 코폴리에스터로 한 산호 12주 시험(Ruhl·Dixson 2019). 색소·첨가제를 줄인다(Prusa, Beard 2026) | 중간. PETG 자체의 수생 독성 시험은 없다 |
| 담수 25°C 안팎이면 무착색 PLA도 | 우린 물이 배아·윤충·물벼룩류에 무해했다(Zhu 2015). 직접 접촉 7일(Pérez-Davila 2022). 25°C에서 1년(Bagheri 2017). 30°C 이상에서는 열화가 빨라진다(Deroine 2014) | 중간 |
| 오래 둘 물건·여과기 속 부품은 PETG | PLA가 세균의 탄소원이 됐다(Zhao 2024). PETG는 물 흡수가 적다. 취미 설계자도 오래 둘 물건은 PETG로 하라고 권한다(Printables 96362: "I recommend printing in PETG long term") | 중간(추론 포함). 여과기 연구에서 PETG를 시험하지는 않았다 |
| 레진 빼기 | 2-1절 | 강함 |
| 나일론·우드 빼기 | 3절(Banjo 2022, Islam 2026) | 강함(물성) |
| 금속·카본·실크·야광·형광 빼기 | 물속 자료가 없다(7절). 색·첨가제에 따라 금속 함량이 다르다(Beard 2026) | 약함(자료 부재에 따른 예방) |
| ABS·ASA 기본 추천에서 빼기 | ABS는 근거가 엇갈린다. 우린 물은 무해했지만(Zhu 2015) 직접 닿으면 독성이 있었다(Oskui 2016). ASA는 수생 시험이 없다. 08 글은 스타이렌 계열이라는 이유로 동물용에서 뺀다 | 중간 |
| 노즐 스테인리스·티타늄 | Rindelaub 2019(납 7~12배). Prusa: "You would need a stainless-steel or a titanium nozzle if you are even considering printing with food in mind."(음식용으로 출력할 생각이라면 스테인리스나 티타늄 노즐이 필요하다) | 중간(양은 아주 적다) |
| 채움 100%, 외벽 3~4줄 이상 | Prusa 수밀 출력, https://help.prusa3d.com/article/watertight-prints_112324: "You want to go with at least 3-4 perimeters for a single wall."(벽 하나에 둘레선을 최소 3~4줄 넣어라) 같은 글: "may leak into the void between the inner and outer walls, creating a place where all kinds of nasty stuff can grow."(안쪽 벽과 바깥 벽 사이 빈 공간으로 물이 새어 온갖 것이 자라는 곳이 될 수 있다) PETG는 채움 100%의 흡수율이 가장 낮았다(https://doi.org/10.1108/rpj-08-2025-0386) | 중간 |
| 작은 틈만 난 속 빈 공간 금지 | MonsterFishKeepers 2008, https://www.monsterfishkeepers.com/forums/threads/be-carefull-sealing-up-aquarium-decorations.181229/: 모래를 넣고 핫글루로 막았지만 작은 구멍 몇 개를 남긴 시판 그루터기 장식이다. "No sooner was that smelly stump out of the water- it was mere hours before all my fish looked much better"(냄새 나는 그루터기를 빼자 몇 시간 만에 물고기들이 훨씬 나아 보였다). 해수 양식에서 황화수소는 낮은 농도에서도 떼죽음을 일으킬 수 있다(Bergstedt 2022, https://pubmed.ncbi.nlm.nih.gov/35917668/) | 약함. 3D 출력물이 아닌 1건이고, 황화수소를 재지 않았다. 예방 차원이다 |
| 세제·소독제 없이 물로만 | Prusa: "The same goes for soap and detergent … The layer lines can absorb these chemicals, which later can be released"(비누와 세제도 마찬가지다. 층 사이 홈이 이런 화학물질을 흡수했다가 나중에 내놓을 수 있다) | 약함. 음식 기준의 경고이고, 소독제까지 넓힌 것은 추론이다 |
| 생물 없는 물에 며칠 담갔다가 버리기 | 레진에서 용출은 처음 24시간에 많다(https://pmc.ncbi.nlm.nih.gov/articles/PMC6187525/: "leaching of compounds from plastic parts is relatively high in the first 24 h"). 산호 연구도 출력물을 해수에 1주 길들여 썼다(Ruhl·Dixson 2019) | 약함. 며칠이면 충분한지 검증한 기준은 없다. 글에도 그렇게 썼다 |
| 하나씩 넣고 관찰, 리프는 넣기 전후 ICP 비교 | 출력물에서 어항 물로 녹아 나오는 금속을 잰 자료가 없어(7절) 직접 확인하는 것이 유일한 방법이다. 산호는 구리 µg/L 수준에도 반응한다(4절) | 예방 차원 |
| 히터에 닿지 않게 | Fluval 설명서와 PLA의 온도 의존 열화(3절) | 중간 |
| 하얗게 뜨거나 갈라지거나 물러지면 교체 | PLA 미세입자 독성(3절). 고온에서 일어나는 취화(Deroine 2014) | 중간 |
| 어항용 실리콘만, 식초 냄새 ≠ 어항용 | sera FAQ, https://www.sera.de/en/service/faq/faq-detail/gluing-rocks-and-decoration-with-silicone: "Construction or household silicone may contain fungicides that can lead to terrible consequences in an aquarium"(건축·가정용 실리콘에는 어항에서 끔찍한 결과를 부를 수 있는 곰팡이 방지제가 들었을 수 있다). "silicones that cure by releasing acetic acid are automatically suitable for aquariums. This is simply wrong"(아세트산을 내며 굳는 실리콘이면 자동으로 어항용이라는 말은 틀렸다). 같은 회사 제품이라도 어항용 여부가 제품마다 다르다(Smooth-On FAQ 196) | 중간(어항 업체들의 공통 안내) |
| 산호 연구에서 순간접착제 젤로 붙여 키움 | Forsman 2015(Mote 해양연구소), https://pmc.ncbi.nlm.nih.gov/articles/PMC4614846/: "Fragments were attached to tiles using cyanoacrylate gel"(산호 조각을 순간접착제 젤로 타일에 붙였다). 생존율은 92~99%였다. AIMS 연구도 Gorilla 순간접착제 젤을 썼다(https://pmc.ncbi.nlm.nih.gov/articles/PMC12228731/) | 중간. 접착제 자체의 수생 독성 시험은 없다. '새우에 안전'하다는 근거는 판매자 주장과 경험담뿐이라 글에 넣지 않았다 |
| 코팅한 출력물을 생물로 시험한 자료 없음 | 에폭시, 플라스티딥, 아크릴 도료를 입힌 출력물을 물고기·새우·산호로 시험한 연구는 찾지 못했다. 관련 자료는 이렇다. 레진에 남은 서포트 왁스는 배아 사망을 약 40시간 늦췄을 뿐이다(Macdonald 2016). 파릴렌-C 코팅 보고는 동료심사를 거치지 않은 프리프린트다. 다 굳은 수도관용 에폭시에서도 BPA가 나왔다(https://pubmed.ncbi.nlm.nih.gov/27448038/). 어항용 에폭시의 경화 대기 시간은 24시간(Pond Shield)에서 7일(TAP)까지 다르다 | 약함(자료 부재) |
| 액상 레진·세척 IPA는 어항 근처 X, 하수구 X | Ballentine 2023, https://pubmed.ncbi.nlm.nih.gov/36792856/: "Two-day acute toxicity (LC50) ranged from 2.6 to 33 mg/L … use of isopropyl alcohol increases miscibility"(이틀 급성 반수치사농도는 2.6~33 mg/L였고, IPA를 쓰면 레진이 물에 더 잘 섞인다). 시험 생물은 Ceriodaphnia dubia다. Formlabs 폐기 안내: "Do not pour solvent (IPA, TPM) that contains dissolved resin into drains"(레진이 녹은 용제를 하수구에 버리지 마라) | 강함 |
| 칼크바서 부품엔 PLA X | 3절 | 예방 차원(직접 시험 없음) |
| 새우·달팽이: 무착색 PETG + 스테인리스 노즐만 | 무척추동물의 구리 민감성(4절). 관상 새우 시험이 없다(7절) | 예방 차원 |
| 해수·리프: 무착색 PETG, 금속 필라멘트·황동 노즐 X | 업계 관행(5절). 산호와 해수 생물의 구리 민감성(4절) | 중간 |

---

## 7. 아직 모르는 것 (조사에서 찾지 못한 것)

- 관상 새우(Neocaridina·Caridina)나 관상 고둥을 출력물 또는 출력물을 우린 물에 노출시킨 연구가 없다. 이 종들의 구리 치사농도를 다룬 동료심사 자료도 찾지 못했다.
- PETG 자체의 수생 독성·용출 시험이 없다. 가장 가까운 자료는 colorFabb nGen·XT로 한 산호 시험이다(Ruhl·Dixson 2019).
- 실제 어항 조건(22~28°C, 생물막, 사료와 배설물, 수개월~수년)에 FDM 출력물을 둔 장기 연구가 없다.
  - PLA 수명은 판매사 추정(QIDI: 열대 담수 6~18개월, 리프 3~12개월)과 실험실 결과(25°C에서 1년 동안 거의 변화 없음)가 서로 맞지 않는다.
- 황동 노즐이나 착색 필라멘트에서 구리·납·아연이 어항 물로 얼마나 녹아 나오는지를 어항 조건에서 잰 연구가 없다. Rindelaub 2019는 50°C 의료기기 추출 조건이었다.
- PLA가 어항 물의 pH·KH를 바꾸는지 정량한 연구가 없다. "pH 변화 없음"(QIDI)은 근거 없는 판매사 주장이다.
- 실크·야광·금속·카본 혼합 필라멘트와 색소 필라멘트가 물속에서 무엇을 내놓는지에 대한 자료가 없다.
- 요즘 가정용 레진(물세척 레진, '수족관 안전'을 내세운 레진)을 세척·후경화한 뒤 성어·새우·산호로 시험한 연구가 없다.
- 코팅한 출력물을 생물로 시험한 연구가 없다.
- 실험실 시험은 물 양에 비해 출력물이 매우 많아 어항보다 훨씬 진하다. 어항의 희석, 환수, 활성탄 여과를 반영해 위험을 정량한 연구가 없다.
- 속 빈 출력물 안의 산소 부족이나 황화수소를 잰 자료가 없다. 히터 표면 온도, 리프 LED의 근자외선이 미치는 영향도 자료가 없다.
- 공공 수족관이 전시나 생명유지 장치에 3D 출력 부품을 쓴다는 공식 자료를 찾지 못했다.
- 한국어 커뮤니티(네이버 카페 등)의 어항 출력물 사례를 찾지 못했다.
- 원문 확인의 한계:
  - Oskui 2016은 ACS 원문이 막혀 초록, 같은 데이터의 미국 특허, 보도자료로 확인했다.
  - Walpitagama 2019, Zhao 2024, Uribe-Echeverría 2022, Banjo 2022는 초록만 확인했다.
  - Reddit·Reef2Reef·Aquarium Co-Op의 경험담은 봇 차단 때문에 원문을 열지 못해 제외했다.

---

## 8. 쓰면 안 되는 표현

| 쓰면 안 되는 표현 | 이유 |
|---|---|
| "PLA·PETG는 어항에 안전하다" / "검증된 소재" | 어항 조건에서 증명된 소재가 없다. "이 조건이면 위험이 낮아 보인다"로 쓴다 |
| "PLA는 물속에서 몇 달이면 녹는다" | 25°C 물에서 1년 동안 거의 분해되지 않았다(Bagheri 2017) |
| "PLA는 생분해되니 무해하다" | PLA 미세입자가 물고기와 물벼룩에 해로웠다. 우린 물이 미세조류 성장을 억제했다 |
| "리프의 알칼리성 물이 PLA를 두 배 빨리 녹인다" | 근거가 37°C, pH 10 실험이다. 40°C 시험에서는 해수 쪽이 더 느렸다 |
| "무착색이면 구리가 없다" | 투명 필라멘트도 압출 뒤 구리가 나왔다(Beard 2026) |
| "레진도 충분히 경화하면 괜찮다" | 후경화 효과가 레진마다 달랐고, 같은 처리로도 치명적인 레진이 있었다 |
| "의료용·식품용 인증이면 어항에도 안전" | USP Class VI 레진도 배아에 독했다. 식품 접촉 규정(EU 10/2011)은 사람 음식 기준이다 |
| "reef-safe / fish-safe 라벨이면 믿어도 된다" | 시험 자료를 공개한 판매자는 없다 |
| "식초 냄새 나는 실리콘은 어항용" | 건축·욕실용 실리콘도 대개 아세트산을 내며 굳는다(sera) |
| "코팅하면 안전해진다" | 코팅한 출력물을 생물로 시험한 자료가 없다 |
| "물고기보다 새우가 구리에 100배 약하다" 같은 수치 비교 | 인용한 새우 논문은 물고기와 비교하지 않았다. 시험 조건이 달라 거친 비교만 가능하다 |
| "3D 출력물 때문에 물고기가 죽은 사례가 있다" | 원문으로 확인한 사례가 없다(사망 일화는 원문을 열지 못해 제외했다) |
