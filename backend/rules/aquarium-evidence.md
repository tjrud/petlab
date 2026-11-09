# 어항(담수 관상어·새우) 설계 기준 근거

`rules/species.yaml` 의 `aquarium` 값과 물속 동굴(cave) 템플릿 규칙의 근거를 모은 문서다.
값마다 [근거](공개 문서에 수치가 있음) / [임시](수치 출처를 찾지 못함, 전문가 검수 때 우선 확인)를 단다.
아직 수의사·수생동물 전문가 검수 전이다 (`reviewed: false`).

조사 방법: 조사 갈래 6개(몸 크기·동굴·끼임·수중 출력 공학·수조 크기·마릿수)가 원문 인용을 모으고,
갈래별 출처 대조 검증(원문을 다시 열어 인용·계산 확인)을 거쳤다. 판정 71건: 확인 42, 일부 수정 23, 틀림 3, 근거 부족 3.
틀림·근거 부족 판정은 아래 '채택하지 않은 제안'과 값 조정에 반영했다.

## 채택한 값

| 항목 | 새우 | 나노 어종 | 소형 어종 | 합사 수조 | 근거 |
|---|---|---|---|---|---|
| 구분 기준 | 몸길이 ≤ 30mm | SL 20~30mm | SL 30~75mm, 체고 ≤ 30mm | 위 구분 함께 | [근거] OATA·MS18, SF |
| 출입구 최소 폭 (mm) | 15 | 20 | 45 | 45 | [임시] N2A 판매 치수 / 체고 계산값 × 여유 |
| 터널 최소 내경 (mm) | 15 | 20 | 45 | 45 | [임시] 출입구와 같게 |
| 터널 최대 길이 | 없음 | 없음 | 없음 | 없음 | 긴 관이 해롭다는 출처 없음 (햄스터 DTSchB 기준은 옮기지 않음) |
| 끼임 안전 틈 safe_max (mm) | 1.0 | 2.0 | 3.0 | 1.0 | [임시] |
| 통과 가능 틈 passable_min (mm) | 15 | 20 | 45 | 45 | [임시] 출입구와 같게 |
| 최소 벽 두께 (mm) | 2.0 | 2.0 | 2.4 | 2.4 | [근거] Prusa 둘레선 4줄 / [임시] 소형 어종 여유 |
| 동굴 출입구 최소 개수 | 1 | 2 | 2 | 2 | [임시] 행동 근거·제조사 경고 |
| 동굴 천장 최소 경사 | 30° | 45° | 30° | 45° | [임시] 남는 공기 계산값 (템플릿은 출력 때문에 40° 이상) |
| 구조물 위 최소 물 깊이 (mm) | 30 | 30 | 75 | 75 | [임시] 스위스 '수심 ≥ 몸길이' 해석 |
| 수조 최소 부피 (L) | 10 | 54 | 54 | 54 | [근거] OATA / 오스트리아·독일·스위스 |
| 마리당 부피 (L) | — | 1.5 | 5.6 | — | [근거] 스위스 동물보호령 표 8 |
| 수조 최소 바닥 (mm) | — | 600×300 | 600×300 | 600×300 | [근거] 오스트리아·독일 '60cm' 등급 |
| 권장 최소 마릿수 | 5 | 10 | 5 (코리도라스 6) | — | [근거] OATA / BLV / 오스트리아·독일 |
| 높이 ÷ 바닥 짧은 변 | 1.5 | 1.5 | 1.5 | 1.5 | [임시] 넘어짐 |

공통: 부력 계산 소재 밀도 1.24 g/cm³ (PLA·PETG 보수값), 물 25°C 담수 0.997 g/cm³ [근거].
수조 부피는 입력한 가로·세로 × (물 깊이 + 바닥재 어림 두께 + 윗여유 30mm)로 어림한다 (표준 부피는 외형 치수 기준이라).

## 설계 판단

- **공기 갇힘**: 햄스터 은신처(바닥이 열린 상자, 평평한 지붕)를 물에 넣으면 출입구 꼭대기 위에 공기가 갇힌다.
  기본 치수에서 약 376cm³ (뜨는 힘 약 375gf) 대 출력물 물속 무게 PLA 약 40gf (계산값). 그래서 어항에는 은신처를 쓰지 않고,
  지붕이 꼭대기 구멍 쪽으로 기울어 공기가 빠지는 **물속 동굴(cave)** 템플릿을 새로 둔다.
  꼭대기 구멍은 passable_min 이상(끼임 구간을 피하고 위쪽 출구도 된다), 지붕 모서리선 경사는 종 기준과 출력 한계(40°) 중 큰 값 이상이다.
  작은 환기구(≤ safe_max)는 기포가 구멍 가장자리에 걸려 공기가 남을 수 있어 쓰지 않는다 (새우는 2.4mm 구멍에 끼어 죽은 사례도 있다).
- **속 빈 공간**: 물이 돌지 않는 반쯤 닫힌 속 빈 공간은 만들지 않는다 (글10). 동굴은 바닥·출입구·꼭대기가 열려 있고, 벽은 3.2mm 이하라
  둘레선만으로 꽉 찬다 (0.45mm 선폭·0.2mm 층에서 바깥·안쪽 4줄씩이면 약 3.3mm).
- **터널**: 양쪽이 열려 있지만 수평으로 놓으면 꼭대기를 따라 공기 띠가 남을 수 있다 (내경 30·길이 100mm 에서 약 6cm³, 계산값).
  형상으로 막지 않고 설치 안내(물속에서 기울여 공기 빼기, 하루 동안 뜨는지 확인)를 띄운다.
- **물속 무게**: 출력물은 물속 무게가 마른 무게의 약 20%라 가볍다. 설계 결과에 물속 무게를 알려 준다.
- **합사**: 크기 구분을 하나만 받으므로, 여러 구분을 함께 키우면 가장 엄격한 값을 합친 '합사 수조' 구분을 고르게 한다.
- **소재·노즐·채움·세척·히터·접착제**: 형상으로 강제할 수 없어 설계 화면·내려받기 화면 안내로 둔다 (`print_notes_ko`, 글10 과 같은 조건).
- **해수(리프)**: 다루지 않는다.

## 채택하지 않은 제안

- 출구 하나인 방의 안쪽 최소 폭(dead_end_min_clear_width, 나노 25·소형 60~61mm): 계수 0.6 의 출처가 없고 나노 값은 근거 부족 판정.
  물고기 동굴은 출입구 2개(관통형)만 허용해 필요가 없다.
- 소형 어종 기준 체고 29.6mm 를 그대로 둔 채 SL 만으로 구분: 블랙 스커트 테트라(체고 약 38mm)가 들어와 45mm 출입구가 좁아진다(틀림 판정).
  → 구분에 '몸높이 3cm 이하'를 더하고 몸이 높은 종을 뺐다.
- 새우 환기구 4mm 예외: 2.4mm 구멍에 새끼 새우가 끼어 죽은 사례 → 작은 구멍을 쓰지 않는다.
- 나노 어종 터널 '25mm 이상 권장' 문구: 근거 부족 판정.
- 터널 경고 길이 200·250mm: 근거 부족 판정.
- 모서리 반경 1.0~2.0mm: 원칙(날카로운 면 금지)은 근거가 강하지만 반경 수치 출처가 없다. 동굴 바깥 모서리와 출입구 테두리는 출력 후 다듬는 안내로 둔다.
- 히터 거리 50mm: 제조사 수치가 없어(사육 안내의 1~2인치) 검사 대신 안내 문구로만 쓴다. 히터 위치를 입력받지 않는다.
- 브리슬노즈·드워프 구라미·쿨리 로치·아마노 새우·달팽이·가재: 크기·행동 자료가 부족해 구분에 넣지 않았다.

## 남은 확인 사항

- 작은 물고기 머리 폭·몸 폭 실측 (safe_max 근거가 가장 약하다), 새우 몸높이 실측.
- 남는 공기 계산의 실측: PLA·PETG 시편을 물에 넣어 경사 천장·꼭대기 구멍 형상에서 공기가 남는지 확인.
- 독일 BMEL 감정서 개정(2025~) 이후 54L·마릿수 값 재확인. 한국 국내 어류 사육 기준은 조사하지 않았다.

# 부록: 조사 항목별 인용과 검증

## A. 몸 크기·동굴·터널·출입구

### [shrimp] size_class 경계 (성체 전장)

- 조사 제안값: 전장 ≤ 30mm (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 몸길이(눈 뒤 가장자리부터 꼬리마디 끝까지) ≤ 30mm. 이마뿔을 넣은 전장은 이보다 조금 길 수 있다
- 내용: shrimp 구분은 성체 몸길이 30mm 이하의 소형 담수 새우(체리·비 새우 계열)로 정한다. OATA는 이들을 약 3cm로 적는다. 일본 하천 조사(Mitsugi & Suzuki 2018, 논문 PDF)에서 가장 큰 암컷은 몸길이 30.0mm였다. 다만 이 몸길이는 눈 뒤 가장자리부터 꼬리마디 끝까지 잰 값이라 이마뿔이 빠져 있다. 그래서 이마뿔까지 넣은 전장은 30mm를 조금 넘을 수 있다. 동료심사 실험에 쓴 체리새우(이마뿔 끝부터 꼬리마디 끝까지)는 평균 16.4mm(11.2~22.4mm)였는데, 암수와 성장 단계를 가리지 않은 표본이다. 아마노 새우(약 5cm)는 이 구분에 넣지 않는다.
- 한계: 몸높이·몸 폭을 잰 자료가 없다. OATA는 체리새우를 Caridina cantonensis 색변이로 적었는데, 분류상으로는 Neocaridina davidi다. 판매점(greenaqua)은 성체를 15~40mm로 적어 실제 상한이 더 클 수 있다. 달팽이·가재는 행동과 크기가 달라 뺐다.
- 출처:
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-tropical-algae-eaters/
    > The other common species of shrimp are colour variants of Caridina cantonensis, which include cherry and bee shrimp. They are much more colourful than Amano shrimp and will likely breed in the home aquarium if cover is provided. They are smaller (3cm) than Amano shrimp and therefore tank mates shoul…
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC8069546/
    > The mean length of shrimp used in the experiments was 16.4 mm (SD: 2.68 mm, range: 11.2–22.4 mm).
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_article
    > while the largest female was 7.7 mm (carapace length) and 30.0 mm (body length)
  - https://www.nature2aqua.de/Garnelen-im-Aquarium
    > Die Garnele Red Fire wird bis zu 2,5 cm groß und stammt ursprünglich aus Taiwan.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-tropical-algae-eaters/
    > They are smaller (3cm) than Amano shrimp and therefore tank mates should be selected carefully.
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_pdf/-char/en
    > the maximum body length (from the postorbital margin to the end of the telson) was recorded for males and females
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_pdf/-char/en
    > while the largest female was 7.7 mm (carapace length) and 30.0 mm (body length)
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC8069546/
    > The shrimp were measured from the tip of the rostrum to the posterior edge of the telson.
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC8069546/
    > We did not determine their sex, assuming that an animal has to be able to successfully hide from predators on the preferred background irrespective of its sex or life stage.

### [nano_fish] size_class 경계 (성체 표준체장)

- 조사 제안값: SL ≤ 30mm (전장 약 36~40mm 이하, 지느러미 연장 제외) (근거)
- 출처 대조 검증: 확인
- 내용: nano_fish는 성체 최대 표준체장이 30mm 이하인 어종이다. Seriously Fish 기준으로 엠버 20, 보라라스 브리지타에 20, CPD 21, 엔들러 25, 네온 30, 피그미 코리 30mm다. 가장 큰 네온의 전장은 FishBase 비율(SL = TL의 82.6%)로 계산하면 약 36mm다. 구피(OATA 약 5cm)와 할리퀸(SL 45mm)은 small_fish로 보낸다.
- 한계: SF 값은 최대 표준체장이라 보통 사육 개체보다 크다. 오토싱클루스는 OATA의 '약 4cm'만 있고 SL이 없어 경계에 걸친다. 구피는 조사 갈래마다 수컷을 nano에 넣기도 했다. 하지만 FishBase가 구피를 5.0cm SL(male/unsexed)로 적고 수조에는 암수가 함께 있으므로, 암수 모두 small_fish에 넣었다. 스위스 법의 크기 등급 1(KL ≤ 5cm)보다 좁게 잡은 구분이다.
- 출처:
  - https://www.seriouslyfish.com/species/paracheirodon-innesi/
    > Standard length 30 mm SL
  - https://www.seriouslyfish.com/species/hyphessobrycon-amandae/
    > Standard length 20 mm SL
  - https://www.seriouslyfish.com/species/boraras-brigittae/
    > Standard length 20 mm SL
  - https://www.seriouslyfish.com/species/danio-margaritatus/
    > Standard length 21 mm SL
  - https://www.seriouslyfish.com/species/poecilia-wingei/
    > Standard length 25 mm SL
  - https://www.seriouslyfish.com/species/corydoras-pygmaeus/
    > Standard length 30 mm
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Painn_u7.jpg&genusname=Paracheirodon&speciesname=innesi&id=10691
    > Standard length 82.6 % TL ... Body depth 26.0 % TL
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-guppies-and-mollies/
    > Traditional guppies (Poecilia reticulata) are larger at about 5cm, whilst Endler guppies (Poecilia wingei) are the smaller species which grow to around 2.5cm.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-tropical-algae-eaters/
    > They stay small, only growing to about 4cm, and are highly social so it is recommended that a group of five or more is kept.
  - https://www.fishbase.se/summary/Poecilia-reticulata.html
    > Max length : 5.0 cm SL male/unsexed; (Ref. 59043 ); 6.0 cm SL (female)
  - https://www.fishbase.se/summary/Corydoras-pygmaeus.html
    > Max length : 2.1 cm SL male/unsexed
  - https://www.seriouslyfish.com/species/trigonostigma-hengeli/
    > Standard length 30 mm SL
  - https://www.seriouslyfish.com/species/trigonostigma-espei/
    > Standard length 30 mm SL

### [small_fish] size_class 경계 (성체 표준체장)

- 조사 제안값: SL 30 초과 ~ 75mm 이하 (전장 약 100mm 이하, 지느러미 연장 제외) (근거)
- 출처 대조 검증: 확인
- 내용: small_fish는 성체 최대 표준체장이 75mm 이하인 어종이다. SF 기준으로 할리퀸 45, 판다 코리 50, 허니 구라미 55, 구피 60, 베타 70, 팔레아투스 70, 아에네우스 75, 아피스토 카카투오이데스 수컷 75mm(암컷 50mm)다. 아에네우스의 전장은 FishBase 비율로 약 96mm다. 독일 TVT가 수조 크기를 나누는 '가장 큰 물고기 전장 10cm' 경계 안에 든다. 브리슬노즈(SF 125mm SL, OATA 약 15cm)와 드워프 구라미(SF 88mm SL)는 이 범위를 넘어서 뺀다.
- 한계: TVT의 10cm 경계는 수조 바닥 크기용이고, 은신처 치수용이 아니다. SF는 베타를 70mm SL로 적어 FishBase 최대 6.5cm TL보다 크게 잡는다. 베타·구피의 긴 지느러미와 아피스토 수컷의 높은 등지느러미는 길이에 넣지 않았다. 램(SL 약 40mm)은 SF 원문 인용을 확보하지 못했다.
- 출처:
  - https://www.seriouslyfish.com/species/corydoras-aeneus/
    > Standard length 75 mm SL
  - https://www.seriouslyfish.com/species/corydoras-paleatus/
    > Standard length 70 mm SL
  - https://www.seriouslyfish.com/species/corydoras-panda/
    > Standard length 50 mm SL
  - https://www.seriouslyfish.com/species/betta-splendens/
    > Standard length 70 mm SL
  - https://www.seriouslyfish.com/species/apistogramma-cacatuoides/
    > Standard length ♂ 75 · ♀ 50 mm SL
  - https://www.seriouslyfish.com/species/trichogaster-chuna/
    > Standard length 55 mm SL
  - https://www.seriouslyfish.com/species/trigonostigma-heteromorpha/
    > Standard length 45 mm SL
  - https://www.seriouslyfish.com/species/poecilia-reticulata/
    > Standard length 60 mm
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Coaen_u0.jpg&genusname=Osteogaster&speciesname=aenea&id=7777
    > Standard length 78.0 % TL ... Body depth 30.8 % TL
  - https://www.tierschutz-tvt.de/alle-merkblaetter-und-stellungnahmen/?no_cache=1&download=TVT-MB_37_S%C3%BC%C3%9Fwasser-Zierfische__Checkliste_Zoofachhandel__Mai_2015_.pdf&did=106
    > Bei Fischen mit einer Gesamtlänge des größten Fisches (ohne Flossenfortsätze) von über 10 cm ist ein Becken mit Mindestkantenlängen (Länge x Breite) von 100 x 40 cm
  - https://www.seriouslyfish.com/species/ancistrus-cf-cirrhosus/
    > Standard length 125 mm SL
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-tropical-algae-eaters/
    > Bristlenose catfish are much smaller than some of their larger relatives, growing to about 15cm.
  - https://www.seriouslyfish.com/species/trichogaster-lalius/
    > Standard length 88 mm
  - https://www.seriouslyfish.com/species/mikrogeophagus-ramirezi/
    > Standard length 40 mm SL
  - https://www.seriouslyfish.com/species/gymnocorymbus-ternetzi/
    > Standard length 60 mm SL

### [nano_fish] ref_max_body_depth_mm (기준 최대 체고, 신규)

- 조사 제안값: 9.4 (네온, 지느러미 제외). 가장 낮은 종(보라라스·칠리)은 약 5 (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 약 10.9 (트리고노스티그마 에스페이, 지느러미 제외). 헨겔리 약 10.0, 네온 9.4, 피그미 코리 약 9.1, 가장 낮은 종(보라라스) 약 5
- 내용: nano_fish에서 몸이 가장 높은 종은 네온이 아니라 트리고노스티그마 에스페이로, 최대 체고는 약 10.9mm다. SF 최대 30mm SL을 FishBase 비율(SL 78.5% TL, 체고 28.6% TL)로 환산했다. 같은 방식으로 헨겔리는 약 10.0mm, 네온은 약 9.4mm, 피그미 코리는 약 9.1mm다. 엠버(약 6.3mm)와 보라라스(약 5.1mm)는 더 낮다. 이 값이 입구, 통로, passable_min을 정하는 출발점이다(계산값, 종마다 사진 1장).
- 한계: FishBase 비율은 종마다 사진 1장으로 잰 값이다(n=1). 몸 폭(두께)과 머리 폭 자료는 없다. 접히는 지느러미와 알 밴 암컷의 배는 체고에 들어 있지 않다. mm 값은 두 출처를 조합해 계산했다.
- 출처:
  - https://www.seriouslyfish.com/species/paracheirodon-innesi/
    > Standard length 30 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Painn_u7.jpg&genusname=Paracheirodon&speciesname=innesi&id=10691
    > Standard length 82.6 % TL ... Body depth 26.0 % TL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Bobri_u2.jpg&genusname=Boraras&speciesname=brigittae&id=22509
    > Body depth 19.7 % TL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Hyama_m0.JPG&genusname=Hyphessobrycon&speciesname=amandae&id=12376
    > Body depth 24.5 % TL
  - https://www.seriouslyfish.com/species/trigonostigma-espei/
    > Standard length 30 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Raesp_u0.gif&genusname=Trigonostigma&speciesname=espei&id=27073
    > Standard length 78.5 % TL ... Body depth 28.6 % TL
  - https://www.seriouslyfish.com/species/trigonostigma-hengeli/
    > Standard length 30 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Rahen_u1.jpg&genusname=Trigonostigma&speciesname=hengeli&id=12182
    > Standard length 73.8 % TL ... Body depth 24.6 % TL

### [small_fish] ref_max_body_depth_mm (기준 최대 체고, 신규)

- 조사 제안값: 29.6 (코리 아에네우스). 아피스토 수컷 약 26, 베타 몸통 약 20.5 (근거)
- 출처 대조 검증: 틀림 — 고친 값: 약 38.3 (블랙 스커트 테트라, SF 60mm SL × FishBase 비율). FishBase 최대 7.5cm SL로 계산하면 약 47.8. 체고 30mm 넘는 종을 small_fish에서 빼면 29.6(코리 아에네우스)을 유지할 수 있다
- 내용: small_fish 안에서 몸이 가장 높은 종은 코리도라스 아에네우스가 아니다. 블랙 스커트 테트라(SF 60mm SL)는 FishBase 비율(SL 77.0% TL, 체고 49.1% TL)로 환산하면 최대 체고가 약 38.3mm다. FishBase 최대 길이 7.5cm SL로 계산하면 약 47.8mm가 된다. 같은 방식으로 타이거 바브는 약 28.7mm, 코리 아에네우스는 약 29.6mm, 아피스토 카카투오이데스 수컷은 약 26mm, 베타 몸통은 약 20.5mm다(베타는 FishBase SL 73.9% TL, 체고 21.6% TL). 그래서 기준 체고를 약 38mm로 올리거나, 드워프 구라미처럼 체고가 30mm를 넘는 종(블랙 스커트 테트라 등)을 small_fish에서 빼야 한다.
- 한계: 비율은 사진 1장(n=1)에서 잰 값이고 몸 폭 자료는 없다. 베타 하프문 같은 긴 지느러미, 아피스토 수컷의 등지느러미, 알 밴 암컷은 반영하지 않았다. 베타 20.5mm는 조사 갈래가 SL 대비 체고 비율로 낸 값인데, 베타의 SL/TL 비율 인용은 확보하지 못했다.
- 출처:
  - https://www.seriouslyfish.com/species/corydoras-aeneus/
    > Standard length 75 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Coaen_u0.jpg&genusname=Osteogaster&speciesname=aenea&id=7777
    > Standard length 78.0 % TL ... Body depth 30.8 % TL
  - https://www.seriouslyfish.com/species/apistogramma-cacatuoides/
    > Standard length ♂ 75 · ♀ 50 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Apcac_u3.jpg&genusname=Apistogramma&speciesname=cacatuoides&id=12282
    > Standard length 74.3 % TL ... Body depth 25.7 % TL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Bespl_u1.gif&genusname=Betta&speciesname=splendens&id=4768
    > Body depth 21.6 % TL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Colal_u4.jpg&genusname=Trichogaster&speciesname=lalius&id=4774
    > Body depth 39.1 % TL
  - https://www.seriouslyfish.com/species/gymnocorymbus-ternetzi/
    > Standard length 60 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Gyter_u1.jpg&genusname=Gymnocorymbus&speciesname=ternetzi&id=4682
    > Standard length 77.0 % TL ... Body depth 49.1 % TL
  - https://www.fishbase.se/summary/Gymnocorymbus-ternetzi.html
    > Max length : 7.5 cm SL male/unsexed
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Bespl_u1.gif&genusname=Betta&speciesname=splendens&id=4768
    > Standard length 73.9 % TL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Putet_u0.jpg&genusname=Puntigrus&speciesname=tetrazona&id=4766
    > Standard length 81.5 % TL ... Body depth 39.0 % TL

### [shrimp] entrance_min_diameter_mm

- 조사 제안값: 15 (임시)
- 출처 대조 검증: 확인
- 내용: 새우 은신처의 입구 최소 지름은 15mm로 둔다. 새우 몸높이를 잰 자료가 없어서, 독일 점토 은신처 제조사가 '새우와 작은 어항 동물'용으로 파는 가장 작은 동굴(안지름 약 15mm)에 맞췄다. 같은 제조사의 13mm 동굴은 소형 가재용이다.
- 한계: 근거 약함: 제조사 판매 정보이고 최소 기준으로 제시된 값이 아니다. 수제품이라 치수 편차가 있다고 제조사가 스스로 밝힌다. 다른 조사 갈래는 몸높이를 6~7mm로 어림하고 1.5배를 곱해 10mm를 제안했다. 물고기는 막고 새우만 들어가게 하는 최대 입구 크기 자료는 없다.
- 출처:
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh2
    > Kleine Fronteingangshöhle mit ca. 15 mm Innendurchmesser und 7 cm Länge. Geeignet als geschützter Rückzugsort für kleine L-Welse wie z. B. L280 Micracanthicus vandragti, Garnelen und andere kleine Aquarienbewohner.
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh3
    > Kleine Fronteingangshöhle mit ca. 20 mm Innendurchmesser und 7 cm Länge. Geeignet als geschützter Rückzugsort für kleine L-Welse wie z. B. L280 Micracanthicus vandragti, Garnelen und andere kleine Aquarienbewohner.
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh1
    > Kleine Krebshöhle mit Fronteingang, ca. 13 mm Innendurchmesser und 5-6 cm Länge für CPO und andere kleine Zwergflusskrebse.
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh2
    > Da unsere Tonartikel handwerklich gefertigt werden, können die Maße geringfügig abweichen
  - https://www.nature2aqua.de/tonroehre-rh1s
    > Beidseitig offene Tonröhre für kleine Hexenwelse

### [shrimp] tunnel_min_inner_diameter_mm

- 조사 제안값: 15 (임시)
- 출처 대조 검증: 확인
- 내용: 새우용 터널 최소 내경은 입구와 같은 15mm다. 같은 제조사는 안지름 15·20mm 동굴과 25mm 양쪽 열린 관을 새우가 쓸 수 있다고 적는다.
- 한계: 근거 약함: 판매 정보다. mm 값은 새우용으로 표기된 가장 작은 제품에 맞춘 것이다.
- 출처:
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh2
    > Kleine Fronteingangshöhle mit ca. 15 mm Innendurchmesser und 7 cm Länge. Geeignet als geschützter Rückzugsort für kleine L-Welse wie z. B. L280 Micracanthicus vandragti, Garnelen und andere kleine Aquarienbewohner.
  - https://www.nature2aqua.de/tonroehre-rh3s
    > Je nach Körpergröße eignet sie sich zum Beispiel für kleinere Welse und Dornaugen. Auch Garnelen können die Röhre als geschützten Aufenthaltsbereich nutzen.
  - https://www.nature2aqua.de/Krebs-Garnelenhoehlen
    > Tonröhren für Aquarien - 3er-Stapel, 15 mm Ø

### [nano_fish] entrance_min_diameter_mm

- 조사 제안값: 20 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 20 유지 시 여유는 약 1.8배(기준 체고 10.9mm). 2배 여유를 지키려면 22
- 내용: nano_fish 은신처의 입구 최소 지름은 20mm다. nano_fish에서 몸이 가장 높은 트리고노스티그마 에스페이의 최대 체고는 약 10.9mm(계산값)이다. 20mm는 여기에 약 1.8배 여유를 준 값이다. 여유 배수에는 출처가 없고, 2배를 지키려면 22mm가 된다. 동료심사 실험에서 몸길이 4.5~5.0cm인 큰가시고기도 지름 22mm 관에 들어갔지만, 좁은 관에 들어간 경우는 적었다.
- 한계: 큰가시고기는 온대 야생종이고, 시험은 PVC 관으로 했다. 두 조사 갈래가 같은 20mm를 냈지만 배수(×2, 또는 ×1.5 뒤 올림)는 둘 다 근거가 없다. 체고 9.4mm 자체는 [근거] 계산값이다.
- 출처:
  - https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/28947/Jones-2023-AnimalBehaviour-Three-spined-sticklebacks_CC.pdf?sequence=1&isAllowed=y
    > Two tubes had equal diameters (2.2 cm) but one, called the short-narrow tube, was shorter, at 5 cm long (just long enough for most of a 4–5 cm fish to fit in), and the other 10 cm long, the long-narrow tube. The third, long-wide tube, was 10 cm long with a 5 cm diameter.
  - https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/28947/Jones-2023-AnimalBehaviour-Three-spined-sticklebacks_CC.pdf?sequence=1&isAllowed=y
    > We used fish of undetermined sex that had body lengths between 4.5 and 5.0 cm
  - https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/28947/Jones-2023-AnimalBehaviour-Three-spined-sticklebacks_CC.pdf?sequence=1&isAllowed=y
    > few fish sheltered within the two narrower tubes

### [nano_fish] tunnel_min_inner_diameter_mm

- 조사 제안값: 20 (화면 안내: 25 이상 권장) (임시)
- 출처 대조 검증: 근거 부족
- 내용: nano_fish 터널 최소 내경은 입구와 같은 20mm다. 물고기는 통과할 수 있는 관 가운데서도 넓은 관을 유의하게 더 자주 골랐으므로(5cm 관 > 2.2cm 관), 화면에서는 25mm 이상을 권장 문구로 안내한다.
- 한계: 선호 실험은 큰가시고기 대상이다. 머문 시간은 관 크기에 따라 차이가 없었다. 25mm 권장 값에는 출처가 없다.
- 출처:
  - https://research-portal.st-andrews.ac.uk/en/publications/three-spined-sticklebacks-show-dimension-specific-preferences-for/
    > The fish showed a clear preference, using larger diameter shelters more frequently than either of the other two options.
  - https://research-portal.st-andrews.ac.uk/en/publications/three-spined-sticklebacks-show-dimension-specific-preferences-for/
    > Certainly, our results suggest that housing sticklebacks with larger diameter shelters may be a simple and convenient means to improve welfare.
  - https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/28947/Jones-2023-AnimalBehaviour-Three-spined-sticklebacks_CC.pdf?sequence=1&isAllowed=y
    > We found no statistically significant difference in duration of time spent in a shelter across shelter types

### [small_fish] entrance_min_diameter_mm

- 조사 제안값: 45 (임시)
- 출처 대조 검증: 틀림 — 고친 값: 약 58 (블랙 스커트 테트라 체고 38.3 × 1.5). 또는 체고 30mm 넘는 종을 small_fish에서 빼고 45 유지
- 내용: small_fish 은신처 입구 최소 지름을 45mm로 두면, 같은 구분에 드는 블랙 스커트 테트라(SF 60mm SL, 체고 약 38.3mm)에게 여유가 약 1.17배밖에 없다. FishBase 최대 길이(7.5cm SL)로 계산한 체고 약 47.8mm보다는 오히려 좁다. 기준 체고를 38.3mm로 고치고 1.5배 여유를 주면 약 58mm가 된다. 45mm를 유지하려면 체고가 30mm를 넘는 종(블랙 스커트 테트라, 드워프 구라미 등)을 small_fish에서 빼야 한다. 여유 배수 1.5에는 출처가 없다.
- 한계: Ramos 2013은 개체 수가 5마리였고, PVC 관이 가장 덜 선호됐다. 1.5배 여유에는 출처가 없다. 다른 갈래는 1.35배를 적용해 40을 냈다. 드워프 구라미(최대 체고 약 41mm)는 45mm에서 여유가 거의 없어 이 구분에서 뺐다. 베타 지느러미 높이는 반영하지 않았다.
- 출처:
  - https://www.alice.cnptia.embrapa.br/bitstream/doc/980854/1/shelterB1.pdf
    > (iii) polyvinyl chloride (PVC) pipes (4 cm ø), all having similar internal volumes (ca. 80 cm2)
  - https://www.alice.cnptia.embrapa.br/bitstream/doc/980854/1/shelterB1.pdf
    > Mean total lengths and weights (SD) of experimental specimens were 6.49 ± 0.52 cm and 3.28 ± 0.72 g, respectively.
  - https://www.nature2aqua.de/Welshoehlen
    > Bei der Auswahl einer Welshöhle sind nicht allein die Gesamtlänge des Welses, sondern auch seine Körperbreite und Körperhöhe entscheidend.
  - https://www.alice.cnptia.embrapa.br/bitstream/doc/980854/1/shelterB1.pdf
    > spent in each shelter during day-time observations (n = 5 fish)
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Gyter_u1.jpg&genusname=Gymnocorymbus&speciesname=ternetzi&id=4682
    > Standard length 77.0 % TL ... Body depth 49.1 % TL
  - https://www.fishbase.se/summary/Gymnocorymbus-ternetzi.html
    > Max length : 7.5 cm SL male/unsexed

### [small_fish] tunnel_min_inner_diameter_mm

- 조사 제안값: 45 (임시)
- 출처 대조 검증: 틀림 — 고친 값: 입구와 같이 약 58, 또는 체고 30mm 넘는 종을 small_fish에서 빼고 45 유지
- 내용: small_fish 터널 최소 내경은 입구와 같게 둔다. 블랙 스커트 테트라처럼 몸이 높은 종(체고 약 38mm)이 이 구분에 들어 있으므로, 1.5배 여유를 주면 약 58mm가 된다. 제조사는 양쪽이 열린 40mm 관을 '메기와 가재'용으로 파는데, 몸이 높은 종에게는 좁다. 45mm를 유지하려면 체고가 30mm를 넘는 종을 small_fish에서 빼야 한다.
- 한계: 판매 정보와 다른 종의 선호 실험을 근거로 했다. 45 자체는 계산과 여유 배수에서 나온 값이다.
- 출처:
  - https://www.nature2aqua.de/tonroehre-rh4s
    > Beidseitig offene, runde Tonröhre mit 40 mm Innendurchmesser für Welse und Krebse wie den Blauen Floridakrebs ( Procambarus alleni ).
  - https://research-portal.st-andrews.ac.uk/en/publications/three-spined-sticklebacks-show-dimension-specific-preferences-for/
    > The fish showed a clear preference, using larger diameter shelters more frequently than either of the other two options.
  - https://www.nature2aqua.de/Krebs-Garnelenhoehlen
    > Offene Tonhöhle rund 40 mm Ø x 15 cm für Welse und Blauen Floridakrebs
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Gyter_u1.jpg&genusname=Gymnocorymbus&speciesname=ternetzi&id=4682
    > Standard length 77.0 % TL ... Body depth 49.1 % TL

### [all (shrimp·nano_fish·small_fish)] tunnel_max_length_mm

- 조사 제안값: 안전상 상한 없음(null). 청소 경고만 둠: shrimp·nano_fish 200, small_fish 250 (임시)
- 출처 대조 검증: 근거 부족
- 내용: 어항 터널에는 길이 상한을 두지 않는다. 긴 관이 물고기에게 해롭다는 출처가 없다. 판매되는 양쪽 열린 관은 안지름의 약 4~8배 길이다(13mm×10cm, 50mm×20cm, 휘핏 메기용 25~30mm×18cm). 위험은 길이보다 막다른 곳과 청소 어려움에서 온다. 그래서 TVT의 '청소를 불필요하게 어렵게 하지 말 것'만 경고 길이로 반영한다. 햄스터의 DTSchB '몸길이 2배' 규칙은 소형 포유류 근거라 옮기지 않는다.
- 한계: 판매 치수는 위험을 시험한 값이 아니다. 경고 길이 200·250mm에는 출처가 없고, shrimp 200은 이번 정리에서 nano에 맞춰 붙였다. 지금 loader는 tunnel_max_length_mm를 필수 양수(≥ 80)로 받으므로 어항용 스키마에서는 선택값으로 바꿔야 한다. 다른 갈래가 낸 몸길이 2배 값(nano 80, small 190)은 근거가 햄스터용이라 채택하지 않았다.
- 출처:
  - https://www.nature2aqua.de/tonroehre-rh1s
    > Innen-Ø ca. 13 mm | Länge ca. 10 cm | beidseitig offen
  - https://www.nature2aqua.de/tonroehre-rh10
    > Innen-Ø ca. 50 mm | Länge ca. 20 cm | beidseitig offen
  - https://www.nature2aqua.de/Welsroehren-fuer-Hexenwelse
    > Die Röhre ist ungefähr 18 cm lang, besitzt einen Innendurchmesser von etwa 25 bis 30 mm und ist an beiden Enden offen.
  - https://www.tierschutz-tvt.de/alle-merkblaetter-und-stellungnahmen/?no_cache=1&download=TVT-MB_37_S%C3%BC%C3%9Fwasser-Zierfische__Checkliste_Zoofachhandel__Mai_2015_.pdf&did=106
    > Dabei sollte das Herausfangen der Fische nicht unnötig behindert und eine Reinigung der Becken nicht unnötig erschwert werden. Als Versteckmöglichkeiten, Unterstand oder zur weiteren Strukturierung bieten sich Röhren, Steine und spezielle Wurzeln an.
  - https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/28947/Jones-2023-AnimalBehaviour-Three-spined-sticklebacks_CC.pdf?sequence=1&isAllowed=y
    > versus long-narrow: emmean contrast 2.09; z test: z ¼ 6.892, P < 0.001; versus short-narrow: emmean contrast 2.01

### [shrimp] hideout_min_entrances

- 조사 제안값: single 1, group 1 (막힌 동굴 허용, 돌아설 폭 요구 없음) (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 새우만 있는 수조: single 1, group 1. 물고기와 함께 키우는 수조: 물고기 구분 규칙(출입구 2개, 또는 dead_end_min_clear_width 이상)을 따른다
- 내용: 새우만 키우는 수조라면 새우 은신처는 입구 하나로 충분하다고 본다. 갑각류는 배를 빠르게 접어 뒤로 튀어 나가는 탈출 반응을 쓰므로 막힌 동굴에서도 뒤로 빠져나올 수 있다(인용 논문은 남극 크릴 연구로, 체리새우를 직접 시험하지 않았다). 제조사도 앞 입구 하나뿐인 동굴을 새우용으로 판다. 다만 15mm 입구에는 nano_fish(체고 약 5~11mm)도 들어갈 수 있다. 그래서 물고기와 함께 키우는 수조에서는 물고기 규칙을 그대로 적용한다. 수치 근거가 아니라 행동 근거라서 [임시]다.
- 한계: 근거 약함: 인용 논문은 남극 크릴 연구이고 체리새우를 직접 시험하지 않았다. 달팽이는 뒤로 가지 못하므로 함께 키우면 이 값이 맞지 않는다.
- 출처:
  - https://www.nature.com/articles/s41598-023-31676-8
    > The caridoid escape response, a fast-start mechanism unique to crustaceans, occurs when the animal performs a series of rapid abdominal flexions and tail flipping that results in powerful backward strokes.
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh2
    > Kleine Fronteingangshöhle mit ca. 15 mm Innendurchmesser und 7 cm Länge. Geeignet als geschützter Rückzugsort für kleine L-Welse wie z. B. L280 Micracanthicus vandragti, Garnelen und andere kleine Aquarienbewohner.
  - https://www.seriouslyfish.com/species/boraras-brigittae/
    > Standard length 20 mm SL

### [nano_fish] hideout_min_entrances

- 조사 제안값: single 2, group 2 (출구 하나인 동굴은 안쪽 폭이 dead_end_min_clear_width 이상일 때만 허용) (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: single 2, group 2. 두 출입구 모두 entrance_min_diameter 이상이어야 2개로 센다. 출구 하나인 방은 안쪽 폭이 dead_end_min_clear_width 이상일 때만 허용한다
- 내용: 물고기 은신처는 관통형(출입구 2개)을 기본으로 하고, 두 출입구 모두 입구 최소 지름 이상이어야 한다. 많은 물고기는 좁은 곳에서 뒤로 잘 빠져나오지 못한다. 포럼에서는 제브라 다니오가 놀라 장식의 좁은 구멍에 머리부터 들어갔다가 끼었고, 다른 사용자도 램, 테트라, 엔젤을 같은 식으로 잃었다고 적었다. 이 사례들은 몸보다 좁은 구멍에 끼는 경우라서, 출입구 수와 함께 '통과 최소 폭보다 좁은 구멍·틈을 만들지 않는 것(gap_trap)'이 직접적인 대책이다. 제조사도 뒤로 못 나오는 종이 막힌 동굴에 들어가면 끼어 죽을 수 있다고 경고한다. nano_fish는 늘 무리로 키우므로 single도 2로 둔다.
- 한계: 근거 약함: 제조사 경고와 포럼 사례뿐이고 수치 근거나 사례 통계가 없다. 휘핏 메기는 이 구분의 대표 종이 아니다.
- 출처:
  - https://fishprofiles.com/forums/General_Freshwater/Fish_stuck_half_in_half_out_/31723
    > They get stuck because they can't or won't swim backward and they don't fit forward so they wedge themselves in really tight.
  - https://www.nature2aqua.de/Welsroehren-fuer-Hexenwelse
    > Hexenwelse können aus einer engen Röhre nicht rückwärts herausschwimmen. Gelangt ein Tier in eine Höhle mit geschlossenem hinteren Ende, in der es sich nicht umdrehen kann, bleibt es stecken. Im schlimmsten Fall verendet der Wels in der Höhle.
  - https://www.nature2aqua.de/tonroehre-gkr4
    > Beidseitig offene Tonröhre mit 30 mm Innendurchmesser für kleinere Welse und Krebse. Als geschützter Rückzugsort und Durchgang geeignet, mit Fluchtmöglichkeit zu beiden Seiten.
  - https://fishprofiles.com/forums/General_Freshwater/Fish_stuck_half_in_half_out_/31723
    > The fish is a zebra danio.
  - https://fishprofiles.com/forums/General_Freshwater/Fish_stuck_half_in_half_out_/31723
    > Happens fairly frequently actually. I've lost a ram, a tetra, and even an angel that way.

### [small_fish] hideout_min_entrances

- 조사 제안값: single 2, group 2 (출구 하나인 동굴은 안쪽 폭이 dead_end_min_clear_width 이상일 때만 허용) (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: single 2, group 2. 두 출입구 모두 entrance_min_diameter 이상이어야 2개로 센다. 출구 하나인 방은 안쪽 폭이 dead_end_min_clear_width 이상일 때만 허용한다
- 내용: small_fish도 관통형을 기본으로 하고, 두 출입구 모두 입구 최소 지름 이상이어야 한다. 옆 입구로 들어간 약 23cm(9인치) 재규어 시클리드가 안에서 돌지도 뒤로 빠지지도 못해 머리를 크게 다친 사례가 있다. 입구 하나는 크고 다른 구멍은 작은 통나무 장식에 플레코가 들어갔다가 돌지 못하고 낀 사례도 있다. 이 플레코는 통나무만큼 두꺼울 정도로 자란 개체였다. 구멍이 여럿이어도 작은 구멍은 출구 구실을 못 한다는 뜻이다. 두 사례 모두 small_fish보다 큰 물고기라서 근거가 약하다. 제조사는 뒤로 못 나오는 종의 수조에는 막힌 동굴을 절대 두지 말라고 한다.
- 한계: 근거 약함: 포럼 사례(큰 물고기)와 제조사 경고뿐이다. 아피스토·메기 같은 동굴 산란 어종은 일부러 입구 하나짜리 좁은 동굴을 쓴다. 이 예외(산란 동굴 모드)는 이번 제안에 넣지 않았다.
- 출처:
  - https://www.monsterfishkeepers.com/forums/threads/help-9-jaguar-cichlid-stuck-in-ornament.751101
    > He entered through a side entrance that I guess he was big enough to still fit into once he was in it was like a fish trap. I couldn't turn him around and he couldn't swim backwards and he really beat up the top of his head struggling.
  - https://www.monsterfishkeepers.com/forums/threads/pleco-small-hollow-log-bad.121748/
    > one opening is big, and easy to get into, while the others are too small. He got in, was too big to turn around, and got stuck. We had to pry him out, and the ornament broke in the process.
  - https://www.nature2aqua.de/Laichhoehlen-fuer-Hoehlenbrueter
    > (In Becken mit Hexenwelsen sollten niemals geschlossene Höhlen liegen! Die Tiere schwimmen hinein und kommen nicht mehr heraus, im schlimmsten Fall sterben sie darin.
  - https://www.monsterfishkeepers.com/forums/threads/help-9-jaguar-cichlid-stuck-in-ornament.751101
    > my beautiful 9" Jag was stuck in a Tiki head ornament
  - https://www.monsterfishkeepers.com/forums/threads/pleco-small-hollow-log-bad.121748/
    > he is about as thick as the log

### [nano_fish] dead_end_min_clear_width_mm (출구 하나인 방의 안쪽 최소 폭, 신규)

- 조사 제안값: 25 (임시)
- 출처 대조 검증: 근거 부족
- 내용: 출구가 하나인 방을 허용하려면 안쪽 최소 폭이 25mm 이상이어야 한다. 식은 max(passable_min 20, 0.6 × 최대 전장 약 36mm = 22)이고, 올림했다. 몸을 돌릴 공간이 따로 필요하다는 생각은 재규어 시클리드 사례와 Walker 2000(돌아서는 데 필요한 공간을 따로 재는 지표)에서 왔다. 0.6이라는 계수에는 출처가 없다.
- 한계: Walker 2000 본문(L/2 값)은 403으로 열지 못했다. 다른 갈래는 대안으로 막힌 동굴 깊이를 몸길이 1.5배 이하로 제한하자고 했다. 이 값은 제조사의 산란 동굴 경험칙을 안전 기준으로 끌어온 것이다.
- 출처:
  - https://www.monsterfishkeepers.com/forums/threads/help-9-jaguar-cichlid-stuck-in-ornament.751101
    > He entered through a side entrance that I guess he was big enough to still fit into once he was in it was like a fish trap. I couldn't turn him around and he couldn't swim backwards and he really beat up the top of his head struggling.
  - https://pubmed.ncbi.nlm.nih.gov/11044378/
    > The observed space required by O. meleagris to turn is slightly greater than its theoretical minimum but much greater than that of highly flexible fish.
  - https://pubmed.ncbi.nlm.nih.gov/11044378/
    > The radius of the minimum space required to turn is an alternative measure of maneuverability.
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Rahen_u1.jpg&genusname=Trigonostigma&speciesname=hengeli&id=12182
    > Standard length 73.8 % TL ... Body depth 24.6 % TL

### [small_fish] dead_end_min_clear_width_mm (출구 하나인 방의 안쪽 최소 폭, 신규)

- 조사 제안값: 60 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 최소 61 (0.6 × 아피스토 카카투오이데스 수컷 전장 약 101mm). 입구를 58로 고치면 max(58, 61) = 61. '단단한 몸' 논리를 그대로 쓰면 전장 1배(약 100mm)에 가깝다. 모두 [임시]
- 내용: small_fish에서 출구 하나인 방의 안쪽 최소 폭은 61mm 이상이다. 식은 max(passable_min, 0.6 × 구분 최대 전장)이다. 구분 최대 전장은 코리 아에네우스(약 96mm)가 아니라 아피스토 카카투오이데스 수컷(약 101mm, SF 75mm SL ÷ FishBase 74.3%)이다. 계수 0.6에는 출처가 없다. 몸이 단단한 물고기는 유연한 물고기보다 돌아설 공간이 훨씬 더 필요하다(Walker 2000 초록). 완전히 단단한 몸이 제자리에서 돌려면 제 몸길이만 한 폭이 필요하므로, 코리도라스의 갑옷 몸을 근거로 삼는다면 0.6배가 아니라 전장 1배(약 100mm)에 가까운 값이 맞다.
- 한계: 계수 0.6에는 출처가 없다. 다른 갈래는 '구분 최대 성체 길이'인 80mm를 제안했다. 몸길이 대비 돌아설 폭을 잰 자료는 찾지 못했다.
- 출처:
  - https://www.monsterfishkeepers.com/forums/threads/pleco-small-hollow-log-bad.121748/
    > one opening is big, and easy to get into, while the others are too small. He got in, was too big to turn around, and got stuck. We had to pry him out, and the ornament broke in the process.
  - https://pubmed.ncbi.nlm.nih.gov/11044378/
    > The observed space required by O. meleagris to turn is slightly greater than its theoretical minimum but much greater than that of highly flexible fish.
  - https://www.seriouslyfish.com/species/apistogramma-cacatuoides/
    > Standard length ♂ 75 · ♀ 50 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Apcac_u3.jpg&genusname=Apistogramma&speciesname=cacatuoides&id=12282
    > Standard length 74.3 % TL ... Body depth 25.7 % TL


## B. 끼임 틈·모서리·수중 출력 공학 (환기구·벽·히터·소재)

### [all (shrimp·nano_fish·small_fish)] gap_trap 판정 방식과 적용 대상

- 조사 제안값: safe_max < 틈 < passable_min 이면 끼임 위험. 적용 대상: 환기구, 장식 창문·구멍, 터널 양 끝과 중간 단면(좁아지는 출구 금지), 구조물끼리의 틈 (근거)
- 출처 대조 검증: 확인
- 내용: 햄스터의 gap_trap 판정을 어항에도 그대로 쓴다. 그물 연구에 따르면 물고기는 아가미뚜껑 뒤 둘레보다 작은 구멍에는 못 들어가고, 최대 둘레보다 큰 구멍은 그냥 지나간다. 그 사이 크기에서 걸리고 뒤로 빠지지 못한다. 어항 장식에서도 같은 양상이 보고됐다. 큰 입구 옆의 작은 '창문' 구멍에 로치가 몸 중간까지 끼었고, 입구는 크고 다른 구멍은 작은 통나무 장식에 플레코가 끼었다. 그래서 출구 쪽이 좁아지는 터널도 같은 판정으로 막는다. 판정 방식은 근거가 있고, 수치는 아래 항목에서 모두 [임시]다.
- 한계: 그물 원리는 어항 장식을 직접 시험한 것이 아니다. DFO 문서 표지에 '저자 허락 없이 인용하지 말 것'이라고 적혀 있어 Mahon 2000과 함께 쓴다. 포럼 사례에는 구멍의 mm 기록이 없다. 물고기 몸은 눌리면 줄어들어 실제 경계는 계산보다 좁을 수 있다.
- 출처:
  - https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/79444.pdf
    > The most important factors causing a fish to be caught by a gillnet are its girth behind the operculum and its maximum girth.
  - https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/79444.pdf
    > Fish with a maximum girth larger than the net lumen and an operculum smaller than the net lumen are likely to be retained by the net for some period of time
  - https://www.cavehill.uwi.edu/wp-content/uploads/sites/38/Docs/Flying-Fish-Book/FF_ch_21.pdf
    > There are three ways in which a fish can be caught in a gillnet: wedged or held tightly by a mesh around the body; gilled or prevented from backing out of the net, by a mesh caught behind the gill cover; or tangled in the net by teeth, maxillaries, etc.
  - https://www.fishforums.net/threads/weirdest-emergency-ever.271044
    > It has one large hole (about 1 inch wide) and some small holes (as 'windows') and one of the loaches has tried to fit through the small hole and is now stuck halfway through.
  - https://www.monsterfishkeepers.com/forums/threads/pleco-small-hollow-log-bad.121748/
    > one opening is big, and easy to get into, while the others are too small. He got in, was too big to turn around, and got stuck. We had to pry him out, and the ornament broke in the process.
  - https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/79444.pdf
    > NOT TO BE CITED WITHOUT PERMISSION OF AUTHORS
  - https://www.cavehill.uwi.edu/wp-content/uploads/sites/38/Docs/Flying-Fish-Book/FF_ch_21.pdf
    > the compressibility of the fish body and the flexibility of twine are important considerations in the method
  - https://www.monsterfishkeepers.com/forums/threads/pleco-small-hollow-log-bad.121748/
    > it turned out he was stuck, because he is about as thick as the log.

### [shrimp] gap_trap.safe_max_mm

- 조사 제안값: 1.0 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 1.0 [임시] (값은 유지하되 근거 서술과 코드 충돌을 고칠 것)
- 내용: 새우의 safe_max는 1.0mm다[임시]. 일본 하천 조사에서 가장 작은 개체의 갑각 길이는 0.8mm였다. 다만 채집망 그물코가 1.0mm여서 그보다 작은 새끼는 빠져나갔을 수 있다. 갑각 길이는 몸 폭이 아니다. 판매점 자료가 적은 갓 부화한 새끼 1~2mm도 몸길이다. 지름 약 2.4mm(3/32인치) 구멍에 작은 새우 4마리가 머리부터 끼어 1마리가 죽은 사례가 있다. 그러니 1.0mm 이하만 안전으로 보는 것은 보수적으로 타당하다. '0.4mm 노즐로 안정적으로 뽑히는 최소 구멍'이라는 말에는 출처가 없다.
- 한계: 몸 폭 실측 자료가 없다. 1~2mm는 판매점 블로그 값이다. 손으로 쓸어 담는 야외 채집이라 가장 작은 새끼는 덜 잡혔을 수 있다. 새우에게 이 판정은 경고로만 쓴다(아래 심각도 항목).
- 출처:
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_article
    > Carapace length of the collected specimens was in the range 0.8–7.7 mm.
  - https://greenaqua.hu/en/blog/post/how-to-protect-shrimp-from-filter-and-surface-skimmer-intake
    > With a full-grown length of 15 mm to 40 mm, these shrimps are not one of the giant aquarium inhabitants we could keep. We can also expect offspring (newly hatched 1-2 mm)
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_pdf/-char/en
    > Carapace length of the collected specimens was in the range 0.8–7.7 mm.
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_pdf/-char/en
    > using a hand net with a 25 cm-wide mouth (mouth area of approximately 420 cm2 mouth area and mesh size of 1.0 mm)
  - https://www.wafishbox.com/forums/threads/shrimp-climbing-into-spray-bar-holes.15535/
    > I had drilled them to 3/32.
  - (저장소) backend/app/templates/hideout.py
    > vent_diameter_mm=min(4.0, s.gap_trap.safe_max_mm),
  - (저장소) backend/app/templates/hideout.py
    > 4, ge=2, le=10

### [shrimp] gap_trap.passable_min_mm

- 조사 제안값: 15 (임시)
- 출처 대조 검증: 확인
- 내용: 새우의 passable_min은 입구 최솟값과 같은 15mm다(햄스터 규칙과 같은 방식). 가장 큰 암컷이 몸길이 30.0mm·갑각 7.7mm이므로 몸높이는 그보다 훨씬 작을 것으로 본다.
- 한계: 몸높이 실측이 없다. 다른 갈래는 몸높이를 6~7mm로 어림하고 1.5배를 곱해 10mm를 제안했다. 이번 정리에서는 입구와 맞추려고 15로 올렸다.
- 출처:
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_article
    > while the largest female was 7.7 mm (carapace length) and 30.0 mm (body length)
  - https://www.nature2aqua.de/welshoehle-krebshoehle-gkh2
    > Kleine Fronteingangshöhle mit ca. 15 mm Innendurchmesser und 7 cm Länge. Geeignet als geschützter Rückzugsort für kleine L-Welse wie z. B. L280 Micracanthicus vandragti, Garnelen und andere kleine Aquarienbewohner.
  - https://www.jstage.jst.go.jp/article/crustacea/47/0/47_9/_pdf/-char/en
    > 7.7 mm (carapace length) and 30.0 mm (body
  - (저장소) backend/rules/species.yaml
    > passable_min_mm: 50   # [근거] 출입구 최소 폭(TVT-Z 5cm)과 같게 둔다

### [shrimp] gap_trap 심각도 (신규)

- 조사 제안값: 경고(warning), 오류 아님 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 슬롯 모양 틈과 구조물 사이 틈(1~15mm)은 경고. 단, 지름 1.0mm 초과 4mm 미만의 둥근 구멍(환기구·장식 창문)은 새우에게도 오류
- 내용: 새우의 끼임 판정은 대체로 경고로 둔다. 다만 작은 둥근 구멍은 오류로 막는다. 지름 약 2.4mm로 넓힌 스프레이바 구멍에 작은 새우 4마리가 머리부터 들어가 꼬리만 내민 채 끼었고, 1마리가 죽었다. 그러니 꼬리 치기 도피 반사만 믿을 수 없다. 장식에 끼어 죽은 사례는 아직 찾지 못했지만, 구멍 모양은 NestForge 환기구와 같다. 새끼 새우에게 가장 큰 위험은 여전히 여과기 흡입구다.
- 한계: 도피 반응 논문은 크릴 대상이다. 새우가 장식에 낀 사례를 다룬 Aquarium Co-Op 글은 403으로 열지 못했다. 달팽이나 물고기 치어를 함께 키우면 경고만으로는 부족할 수 있다.
- 출처:
  - https://www.nature.com/articles/s41598-023-31676-8
    > The caridoid escape response, a fast-start mechanism unique to crustaceans, occurs when the animal performs a series of rapid abdominal flexions and tail flipping that results in powerful backward strokes.
  - https://www.aquasabi.com/aquascaping-wiki/invertebrate/making-the-filter-shrimp-proof
    > Dwarf shrimp offspring are only a few milimeters small, so there is a risk of them getting sucked into the filter
  - https://www.wafishbox.com/forums/threads/shrimp-climbing-into-spray-bar-holes.15535/
    > noticed four shrimp with their tails sticking out of the spray bar holes! All but one was still alive and I was able to gently get them to back out of the holes
  - https://www.wafishbox.com/forums/threads/shrimp-climbing-into-spray-bar-holes.15535/
    > I had drilled them to 3/32.
  - https://www.wafishbox.com/forums/threads/shrimp-climbing-into-spray-bar-holes.15535/
    > The holes are too small for the large amano, but smaller amano or cherries could climb in it seems.

### [nano_fish] gap_trap.safe_max_mm

- 조사 제안값: 2.0 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 2.0 [임시]으로 두고 nano_fish를 성체 SL 20mm 이상인 종으로 한정해 명시. B. micros(SL 13mm)·B. urophthalmoides(SL 16mm)까지 넣으려면 약 1.5
- 내용: nano_fish의 safe_max는 2.0mm다[임시]. 기준 종은 칠리 라스보라(Boraras brigittae, 최대 SL 20mm)다. FishBase 비율(SL 77.3% TL, 체고 19.7% TL)로 계산한 최대 체고는 약 5.1mm이고, 그 약 40%로 어림했다. 하지만 이 종이 가장 작은 성체는 아니다. B. micros는 최대 SL 13mm(같은 비율이면 체고 약 3.3mm, 40%는 약 1.3mm), B. urophthalmoides는 SL 16mm(약 4.1mm, 약 1.6mm)다. 게다가 B. urophthalmoides는 brigittae라는 이름으로 흔히 팔린다. 참고로 미국 NMFS는 연어 치어 보호 스크린의 둥근 구멍을 3/32인치(2.38mm), 슬롯을 1.75mm 이하로 정했다.
- 한계: 머리 폭 실측이 없다. 치어는 더 작다. 2mm 환기구는 공기가 잘 빠지지 않아 경사 천장이 필요하다(환기구 항목).
- 출처:
  - https://www.seriouslyfish.com/species/boraras-brigittae/
    > Standard length 20 mm SL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Bobri_u2.jpg&genusname=Boraras&speciesname=brigittae&id=22509
    > Body depth 19.7 % TL
  - https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/79444.pdf
    > those fish with an operculum girth much larger than the lumen of the net easily escape
  - https://www.seriouslyfish.com/species/boraras-micros/
    > Max size 13 mm SL
  - https://www.seriouslyfish.com/species/boraras-urophthalmoides/
    > Max size 16 mm SL
  - https://www.seriouslyfish.com/species/boraras-brigittae/
    > The congener B. urophthalmoides is often traded under its name, but B. brigittae is larger
  - https://www.seriouslyfish.com/species/boraras-brigittae/
    > tend to have a slimmer, more elongate body profile than those from Indochina
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Bobri_u2.jpg&genusname=Boraras&speciesname=brigittae&id=22509
    > Pre-pectoral length 19.7 % TL Body depth 19.7 % TL Head length (HL) 19.7 % TL
  - https://www.fs.usda.gov/media/113404
    > Circular Screens: Circular screen face openings must not exceed 3/32 inch in diameter.
  - https://www.fs.usda.gov/media/113404
    > Slotted Screens: Slotted screen face openings must not exceed 1.75 mm (approximately 1/16 inch) in the narrow direction.

### [nano_fish] gap_trap.passable_min_mm

- 조사 제안값: 20 (임시)
- 출처 대조 검증: 확인
- 내용: nano_fish의 passable_min은 입구 최솟값과 같은 20mm다. 기준은 지금 개체가 아니라 그 종의 성체 최대 크기다. 어릴 때 지나다니던 구멍에 자라서 끼는 사례가 있기 때문이다. 그물 연구에서 최대 둘레가 구멍보다 크고 아가미뚜껑 둘레가 구멍보다 작으면 걸린다.
- 한계: 성장 후 끼임 사례는 1건(로치)이다. 20은 계산 체고 9.4mm에 출처 없는 여유를 준 값이다.
- 출처:
  - https://forums.loaches.com/viewtopic.php?p=50152
    > They've been in there with it for about 10 months and never showed any interest even when they were small enough to probably fit right through.
  - https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/79444.pdf
    > Fish with a maximum girth larger than the net lumen and an operculum smaller than the net lumen are likely to be retained by the net for some period of time

### [small_fish] gap_trap.safe_max_mm

- 조사 제안값: 3.0 (nano_fish와 함께 키우면 2.0) (임시)
- 출처 대조 검증: 확인
- 내용: small_fish의 safe_max는 3.0mm다. 근거 수치는 없다. 코리도라스는 날카로운 가슴지느러미 가시가 그물코에 잘 걸리고, 바위 구멍에 끼어 머리와 꼬리만 보였다는 사례도 있다. 그래서 가시가 걸릴 만한 격자·그물 무늬와 중간 크기 구멍을 피한다.
- 한계: 근거 약함: 포럼 일화와 사육 정보뿐이다. 끼임이 시작되는 구멍 크기의 수치는 없다. 이 구분에서 가장 작은 성체(SL 약 40~45mm)의 머리 폭 실측도 없다.
- 출처:
  - https://www.seriouslyfish.com/species/corydoras-panda/
    > They also have very sharp pectoral fin spines, which are easily caught in the mesh of aquarium nets and can also produce a painful "sting" if they penetrate the skin.
  - https://www.fishforums.net/threads/corydora-stuck-in-hole.166054
    > It's been missing for a day or two, and we just found it out of sight, stuck in a hole in a rock. Its tail is poking out one end (slightly) and we can see its face, but nothing in between.
  - https://www.fs.usda.gov/media/113404
    > Circular Screens: Circular screen face openings must not exceed 3/32 inch in diameter.

### [small_fish] gap_trap.passable_min_mm

- 조사 제안값: 45 (임시)
- 출처 대조 검증: 확인
- 내용: small_fish의 passable_min은 입구 최솟값과 같은 45mm다. 물고기는 몸높이의 절반밖에 안 되는 구멍에도 머리를 밀어 넣는다. 몸높이 약 3인치인 세베룸이 약 1.5인치 구멍에 박힌 사례가 있다. 장식 속에 들어가 보이지 않는 곳에서 죽은 시클리드 사례도 있다. 그러므로 passable_min은 최대 체고(29.6mm)보다 넉넉히 커야 한다.
- 한계: 큰 물고기 사례이고 크기는 글쓴이가 어림한 값이다. 1.5배 여유에는 출처가 없다.
- 출처:
  - https://www.fishforums.net/threads/fish-is-stuck.68895
    > that fish is about 3 inches in width ,that hole is about 1 and half inches
  - https://www.fishforums.net/threads/grisly-how-to-remove-fish-from-ornament.399117
    > we know that there was a cichlid who wedged himself into an ornament in the tank
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Coaen_u0.jpg&genusname=Osteogaster&speciesname=aenea&id=7777
    > Standard length 78.0 % TL ... Body depth 30.8 % TL
  - https://www.fishbase.se/physiology/MorphMetSummaryV2.php?picname=Coaen_u0.jpg&genusname=Osteogaster&speciesname=aenea&id=7777
    > Body depth 30.8 % TL

### [all (shrimp·nano_fish·small_fish)] 여러 구분 결합 규칙 (신규)

- 조사 제안값: 수조에 함께 키우는 모든 구분 가운데 가장 작은 safe_max, 가장 큰 passable_min·입구·통로·모서리 반경, 가장 엄격한 소재(새우가 있으면 PETG만)를 적용 (임시)
- 출처 대조 검증: 확인
- 내용: 어항은 여러 종을 함께 키우는 것이 기본이다. 햄스터처럼 한 구분만 고르면 함께 사는 다른 종에게 덫이 되는 크기를 놓친다. 예를 들어 nano와 small을 함께 키우면 2~45mm 틈이 모두 위험 구간이 된다. 출처는 합사가 흔하다는 점만 보여 주고, 결합 방식은 규칙의 논리에서 나왔다.
- 한계: 결합 방식 자체를 다룬 출처는 없다. 지금 코드는 한 설계에 종·크기 하나만 받는다.
- 출처:
  - https://www.seriouslyfish.com/species/paracheirodon-innesi/
    > Try to buy a mixed-sex group of at least 8-10 specimens, include other schooling fishes to provide security, and you'll be rewarded with a more natural-looking spectacle.
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Gesellig: Fische, die auch von anderen Fischen begleitet werden sollen um ihr arttypisches Verhalten zu zeigen. Neben anderen Fischen sind mindesten fünf Tiere dieser Art zusammen zu halten.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-invertebrates/how-to-look-after-freshwater-shrimp-and-snails/
    > It is recommended that an aquarium of at least 10 litres is used for a group of small freshwater shrimp or snails. Larger species, such as apple snails or Amano shrimp, will require a slightly larger aquarium of approximately 20 litres. This will need to be larger if keeping freshwater shrimp or sna…
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-invertebrates/how-to-look-after-freshwater-shrimp-and-snails/
    > This will need to be larger if keeping freshwater shrimp or snails with any fish species.

### [all (shrimp·nano_fish·small_fish)] gap_trap_wall (구조물-유리 틈)

- 조사 제안값: passable_min 이상 띄우기 권장. safe_max 이하(맞붙임)는 허용하되 청소 사각지대 경고. 그 사이 크기는 금지 (임시)
- 출처 대조 검증: 확인
- 내용: 장식과 수조 유리 사이 틈에도 물고기가 낀다. 밤사이 돌과 유리 사이에 엔젤피시가 끼어 있던 사례가 있고, '끼일 수 없을 만큼 띄우라'는 조언이 나왔다. 유리에 바짝 붙이면 물이 돌지 않는 사각지대가 생기고 청소도 못 하므로 경고를 붙인다. 수치는 gap_trap 값을 따르므로 [임시]다.
- 한계: 근거 약함: 끼임은 포럼 사례 1건이고 사각지대는 해수 리프 안내다. 다른 갈래가 낸 청소 여유 20mm(min_glass_clearance_mm)는 수치 출처가 없고 passable_min(≥ 15~45)과 겹쳐 뺐다.
- 출처:
  - https://www.fishforums.net/threads/rock-and-a-hard-place.469683
    > So I woke up and found one of my Angels between a rock and my tank glass.
  - https://www.fishforums.net/threads/rock-and-a-hard-place.469683
    > Best to have enough space that getting trapped is impossible. The time fish are most likely to dive for cover is during a water change
  - https://reefbuilders.com/2015/07/20/avoid-these-5-live-rock-aquascaping-pitfalls
    > If at all practicable, try to avoid building a rockwork stack right against the back glass or other panes. Doing so creates undesirable circulation “dead zones” (where copious amounts of detritus can accumulate) and will prevent access to those areas for cleaning/maintenance .
  - https://reefbuilders.com/2015/07/20/avoid-these-5-live-rock-aquascaping-pitfalls
    > Doing so creates undesirable circulation “dead zones” (where copious amounts of detritus can accumulate) and will prevent access to those areas for cleaning/maintenance .

### [all (shrimp·nano_fish·small_fish)] edge_min_radius_mm / entrance_rim_min_radius_mm (신규)

- 조사 제안값: 모든 바깥 모서리 ≥ 1.0. 입구·환기구 테두리: shrimp 1.0, nano_fish 1.5, small_fish 2.0 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 값은 [임시]로 유지(바깥 모서리 ≥ 1.0, 테두리 1.0/1.5/2.0). '노즐로 낼 수 있는 최소 둥글기'라는 근거는 뺀다
- 내용: 날카롭거나 거친 모서리가 없어야 한다는 원칙은 근거가 강하다. OATA, Smith 2023(공공 수족관 복지 리뷰), 유럽평의회 양식어 권고, 바이에른 LfL, 스위스 동물보호령 제7조, RSPCA 호주가 모두 같은 말을 한다. 지느러미 침식의 원인으로 거친 면과의 마찰이 꼽힌다. 반경 mm 값은 출처가 없는 [임시] 값이다. 0.4mm 노즐로도 1mm보다 작은 둥글기는 출력할 수 있으므로, 1mm는 출력 한계가 아니라 고른 값이다.
- 한계: OATA·LfL·유럽평의회 자료는 각각 판매용 관상어, 전시용 토종어, 양식어를 대상으로 한다. 스위스 법령은 2013년 통합본으로 확인했다. Latremouille 2003은 초록만 봤다. FDM 출력면 거칠기와 지느러미 손상의 관계를 다룬 연구는 없다. 반경 값은 전문가 검수 우선 항목이다.
- 출처:
  - https://ornamentalfish.org/wp-content/uploads/Bettas-Siamese-Fighting-Fish-Sept-2022.pdf
    > To avoid injuries to their long fins, ornaments or artificial plants with sharp or very rough edges should not be selected.
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC10451808/
    > The interior of the system should be free of sharp edges, abrasive surfaces, and hard to access spaces for aquarium personnel.
  - https://umwelt-online.de/recht/natursch/tier/z_fisch.htm
    > die Gefahr von Verletzungen und Stress auf ein Mindestmaß reduzieren; keine scharfen Kanten, Unebenheiten und Materialien aufweisen, welche die Fische verletzen könnten
  - https://lfl.bayern.de/mam/cms07/publikationen/daten/merkblaetter/heimische-fische-schauaquarien_lfl-merkblatt.pdf
    > Verwendete Steine sollten nicht scharfkantig, sondern abgerundet sein.
  - https://www.lexfind.ch/tolv/138683/de
    > Unterkünfte und Gehege müssen so gebaut und eingerichtet sein, dass: a. die Verletzungsgefahr für die Tiere gering ist;
  - https://kb.rspca.org.au/knowledge-base/how-should-i-care-for-my-siamese-fighting-fish/
    > To ensure fins are not torn, gravel should be smooth and decorations such as silk or live plants should not have rough edges. Male fish with long fins are particularly prone to fin tears. Sharp edges and points on some decor and driftwood can be sanded gently to make it safe.
  - https://doi.org/10.1080/10641260390255745
    > Fin erosion occurs when the fins of afflicted fish become degraded from a variety of sources, which can include abrasion with rough surfaces, fin damage from aggressive encounters between fish, nutritional deficiencies, and bacterial infection.

### [all (shrimp·nano_fish·small_fish)] require_vent_at_every_ceiling_high_point (신규, 환기구 0개 금지)

- 조사 제안값: true (근거)
- 출처 대조 검증: 확인
- 내용: 천장이 있는 구조물은 천장의 가장 높은 곳마다 환기구나 위로 열린 통로가 있어야 한다. 지금 hideout 기본값(140×110×90mm, 벽 3mm, 입구 60mm)에 환기구가 없으면, 입구 꼭대기 위에 공기 약 376cm³가 갇혀 약 375gf의 힘으로 뜬다. 반면 출력물의 물속 무게는 PLA 약 40gf, PETG 약 45gf뿐이다. 출력물이 뜨는 힘은 모두 갇힌 공기에서 나온다. 따라서 어항용에서는 vent_count=0을 막는다.
- 한계: 물리 계산(데이터시트 밀도와 템플릿 기본 치수로 직접 계산한 값)이며 실측하지 않았다. 템플릿은 지금 vent_count=0을 허용한다.
- 출처:
  - (저장소) backend/app/templates/hideout.py
    > 형상: 바닥이 열린 상자. 앞면(-Y)에 바닥에서 시작하는 아치형 출입구, 지붕에 수직 환기구.
  - https://qidi3d.com/blogs/print-lab/3d-printed-fishing-lures
    > Every FDM plastic is denser than water when printed solid, which means all of the float in a printed lure comes from trapped air.
  - https://www.fishforums.net/threads/weight-down-an-ornament.448540
    > when i put the rock in it now keeps floating as it is hollow.
  - https://www.fishforums.net/threads/weight-down-an-ornament.448540
    > perhaps make a few discrete holes so that air can get out and the hollow parts of fake rock gets filled with water therefore will stay submerged perhaps.
  - https://spectrumfilaments.com/wp-content/uploads/2025/11/en_tds_spectrum_pp.pdf
    > Extremely low density – 0.9 g/cm³
  - (저장소) backend/app/templates/hideout.py
    > vent_count: int = Field(6, ge=0, le=30, description="지붕 환기구 개수")

### [all (shrimp·nano_fish·small_fish)] vent_max_diameter_mm (환기구 지름)

- 조사 제안값: = gap_trap.safe_max: nano_fish 2.0, small_fish 3.0. shrimp는 끼임 판정이 경고뿐이라 4.0까지 허용 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: nano_fish 2.0, small_fish 3.0(= safe_max). shrimp는 4.0 예외를 없애고, 천장 꼭대기에 passable_min(15mm) 이상의 위로 열린 통로를 둔다. 작은 구멍을 쓰더라도 1.0mm 초과 4mm 미만 둥근 구멍은 금지
- 내용: 환기구는 safe_max 이하여야 한다. 구멍 가장자리에 걸린 기포를 밀어내려면 최대 4σ/d의 압력이 필요하다. 그래서 평평한 천장 밑에는 최대 약 4σ/(ρgd)에서 지붕 두께를 뺀 높이만큼 공기가 남을 수 있다. 4σ/(ρg)는 약 29.4mm²이므로 d=2mm면 약 14.7mm에서 지붕 두께를 뺀 값이다. 물의 모세관 길이는 약 2.7mm이고, PLA·PETG의 접촉각은 약 72~73°다. 어류는 safe_max를 지키고 경사 천장으로 공기를 뺀다. 새우도 작은 구멍 예외를 두지 않는다. 2.4mm 구멍에 새우가 끼어 죽은 사례가 있으므로, 위로 열린 15mm 이상 통로로 공기를 뺀다.
- 한계: 남는 공기 계산은 교과서의 영-라플라스 식으로 낸 추정이고, 생물막이 끼면 달라진다. 출력 시편을 양동이에 넣어 확인해야 한다. 새우 4mm 예외는 갓 부화한 새우(1~2mm)가 지붕 구멍을 드나들 수 있다는 점을 받아들인 것이다.
- 출처:
  - https://en.wikipedia.org/wiki/Capillary_length
    > resulting in a capillary length of ∼ 3 mm for water and air at room temperature on earth.
  - https://acikerisim.uludag.edu.tr/entities/publication/156a16d1-9f8e-4975-aa10-41e7e3da9875/full
    > The mean +/- standard deviation (SS) of contact angle for SS was 78.29 +/- 0.18, for PETG was 72.09 +/- 0.94, for PLA was 73.03 +/- 1.17.
  - https://www.wafishbox.com/forums/threads/shrimp-climbing-into-spray-bar-holes.15535/
    > noticed four shrimp with their tails sticking out of the spray bar holes! All but one was still alive and I was able to gently get them to back out of the holes
  - https://www.wafishbox.com/forums/threads/shrimp-climbing-into-spray-bar-holes.15535/
    > I had drilled them to 3/32.

### [all (shrimp·nano_fish·small_fish)] ceiling_min_slope_deg (환기구 쪽으로 오르는 안쪽 천장 경사, 신규)

- 조사 제안값: nano_fish 45, small_fish·shrimp 30 (임시)
- 출처 대조 검증: 확인
- 내용: 안쪽 천장은 환기구 쪽으로 올라가게 기울인다. 조사 계산으로는 30° 이상이고 환기구가 3~5mm이면 남는 공기가 0.1~1.9cm³다. 평평한 천장에서는 17~61cm³가 남는다. 같은 식으로 다시 계산하면 nano의 2mm 환기구(지붕 2mm)는 30°에서 약 6.4cm³가 남는다. 80×80×60mm 나노 은신처의 물속 무게(PLA 약 12gf)와 견주면 비율이 0.5를 넘고, 45°에서는 약 2.1cm³로 줄어든다. 은신처는 지붕을 베드에 대고 뒤집어 출력하므로 기울어진 안쪽 천장은 위를 향하고 서포트가 필요 없다.
- 한계: 모두 이론 계산이며 실측이 없다. 80×80×60mm 나노 은신처 예시와 45° 값은 이번 정리에서 다시 계산한 것이다. printing.yaml의 max_overhang_deg 45와 맞는지는 출력 방향에 따라 확인해야 한다.
- 출처:
  - https://en.wikipedia.org/wiki/Capillary_length
    > resulting in a capillary length of ∼ 3 mm for water and air at room temperature on earth.
  - https://www.printables.com/model/96362-aquarium-decoration-textured-rock-cave-medium
    > Designed with 2mm walls and meant to be printed with 100% infill and no supports; thin walls in design make it unsuitable for significant re-sizing.
  - https://www.printables.com/model/96362-aquarium-decoration-textured-rock-cave-medium
    > This model may have a bit of filament sag due to the somewhat flat roof, but it will print successfully without supports.

### [all (shrimp·nano_fish·small_fish)] max_trapped_air_lift_ratio (신규)

- 조사 제안값: 0.5 (남는 공기 부력 ÷ 물속 무게) (임시)
- 출처 대조 검증: 확인
- 내용: 계산상 남는 공기의 부력이 출력물 물속 무게의 절반을 넘지 않아야 한다(안전율 2). 물속 무게는 고체 부피 × (소재 밀도 − 물 밀도)이고, PLA·PETG는 꽉 채워 뽑으면 물보다 무겁다.
- 한계: 안전율 2에는 출처가 없다. 물살과 생물막의 영향은 반영하지 않았다.
- 출처:
  - https://qidi3d.com/blogs/print-lab/3d-printed-fishing-lures
    > Every FDM plastic is denser than water when printed solid, which means all of the float in a printed lure comes from trapped air.
  - https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/c34f5f47-tds_prusament-petg_n_de.pdf
    > Dichte [g/cm3] 1.27 ISO 1183

### [all (shrimp·nano_fish·small_fish)] material_density_g_cm3 (신규)

- 조사 제안값: PLA 1.24, PETG 1.27. 부력·물속 무게 판정에는 보수적으로 둘 다 1.24 (근거)
- 출처 대조 검증: 확인
- 내용: PLA와 PETG의 밀도는 데이터시트 값이다. 물속에 남는 무게는 마른 무게의 약 20%뿐이다(PLA 19.6%, PETG 21.5%). PETG 데이터시트에는 1.24도 있으므로 판정은 낮은 값으로 한다.
- 한계: 무착색 순수 필라멘트 값이고, 착색제·첨가제가 들어가면 달라진다. 100% 채움이어도 실제 고체 비율은 1보다 조금 낮다.
- 출처:
  - https://datasheet.sic-components.com/TechnicalDataSheet_4043D_3D-monofilament_pdf.pdf%3Fla%3Den
    > Specific Gravity, g/cc 1.24 D792
  - https://cdn.shopify.com/s/files/1/0380/5149/files/Bambu_PLA_Basic_Technical_Data_Sheet.pdf
    > Density ISO 1183 1.24 g/cm³
  - https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/c34f5f47-tds_prusament-petg_n_de.pdf
    > Dichte [g/cm3] 1.27 ISO 1183
  - https://cdn.shopify.com/s/files/1/0965/1648/files/PETG_Filament_v2.1.pdf
    > Density g/cc ISO 1183 1.24

### [all (shrimp·nano_fish·small_fish)] water_density_g_cm3 (신규)

- 조사 제안값: 0.997 (담수 25°C). 이번 제안은 담수만 다룸 (근거)
- 출처 대조 검증: 확인
- 내용: 부력 계산에 쓰는 물 밀도는 25°C 담수 기준 0.997g/cm³다. 해수(리프)는 이번 크기 구분에 없으므로 1.024 값은 나중에 해수를 지원할 때 쓴다.
- 한계: 수온에 따라 조금 달라진다. 해수를 지원하면 PETG만 허용하고 1.024로 계산해야 한다.
- 출처:
  - https://en.wikipedia.org/wiki/Properties_of_water
    > 0.997 047 02 (83) g/mL at 25 °C
  - https://en.wikipedia.org/wiki/Seawater
    > At a temperature of 25 °C, the salinity of 35 g/kg and 1 atm pressure, the density of seawater is 1023.6 kg/m 3 .

### [all (shrimp·nano_fish·small_fish)] print_infill_percent (3MF 설정·출력 안내)

- 조사 제안값: 100 (근거)
- 출처 대조 검증: 확인
- 내용: 채움은 100%로 한다. 공기가 갇힌 닫힌 빈칸이 있으면 고체 비율이 PLA 약 80%, PETG 약 78.5% 이하일 때 출력물이 뜬다. 두꺼운 벽을 채움 15~20%로 뽑으면 고체 비율이 40~50%라 뜰 수 있다. 어항 장식 설계자와 업체 모두 100% 채움을 가라앉히는 조건으로 들고, PETG는 채움 100%에서 물 흡수가 가장 적었다.
- 한계: 설계자·업체 글은 경험담이다. Bedi 2026은 초록만 확인했고, 시험 조건은 포화 소금물이다. 임계값은 밀도 비로 다시 계산해도 같다.
- 출처:
  - https://qidi3d.com/blogs/print-lab/3d-printed-fishing-lures
    > Material Density (g/cm³) Printed solid, in fresh water Max solid fraction to float Max solid fraction to float in salt PLA ~1.24 Sinks ~80% ~82% PETG ~1.27 Sinks ~78% ~81%
  - https://www.printables.com/model/96362-aquarium-decoration-textured-rock-cave-medium
    > PLA and PETG are both denser than freshwater so 100% infill will naturally sink to the bottom of the tank.
  - https://doi.org/10.1108/rpj-08-2025-0386
    > Results indicate that 100% infill density consistently exhibited the lowest water absorption due to reduced porosity and stronger layer adhesion, whereas 50% infill density showed the highest due to increased voids and weaker bonding.
  - https://doi.org/10.1108/rpj-08-2025-0386
    > The composites were immersed in distilled water, saturated salt and saturated sugar solutions to evaluate their water absorption behavior.

### [all (shrimp·nano_fish·small_fish)] print_min_perimeters (+ 채움 없이 꽉 차는 벽 두께 3.6mm 권고)

- 조사 제안값: 4 (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 4. 채움 없이 둘레선만으로 꽉 차는 벽 두께는 약 3.3mm(0.45mm 선폭, 0.2mm 층 기준)
- 내용: 벽 하나에 둘레선은 4줄 이상이다. Prusa의 수밀 출력 권장(3~4줄)에서 위쪽 값을 골랐다. Prusa는 채움이 필요할 만큼 두꺼운 벽은 안쪽·바깥 벽 사이 빈 공간으로 물이 새어 '온갖 것이 자라는 곳'이 될 수 있다고 경고한다. 슬라이서는 이웃한 선을 겹쳐 깔기 때문에 선 간격이 선폭보다 좁다. 간격은 선폭 − 층높이×(1−π/4)이고, 0.45mm 선폭·0.2mm 층이면 약 0.41mm다. 따라서 바깥과 안쪽에 4줄씩 넣으면 약 3.3mm까지 둘레선만으로 꽉 찬다. 그보다 두꺼운 벽에는 채움이나 틈 메움 선이 들어간다.
- 한계: Bambu Lab의 공식 수밀 안내는 찾지 못했다. 3.6mm는 슬라이서 기본 선폭으로 계산한 값이고, 선폭 설정이 바뀌면 달라진다.
- 출처:
  - https://help.prusa3d.com/article/watertight-prints_112324
    > You want to go with at least 3-4 perimeters for a single wall.
  - https://help.prusa3d.com/article/watertight-prints_112324
    > Thick walls which require infill is often waste in this case. It can cause irregularities and may leak into the void between the inner and outer walls, creating a place where all kinds of nasty stuff can grow.
  - https://help.prusa3d.com/article/creating-profiles-for-different-nozzles_127540
    > Enter the Default extrusion width manually (e.g. 0.45 mm) If you enter 0 PrusaSlicer will derive the extrusion width from the nozzle diameter 1.125 × nozzle diameter will be used
  - https://manual.slic3r.org/advanced/flow-math
    > spacing = extrusion_width - layer_height * (1 - PI/4)

### [shrimp, nano_fish] min_wall_thickness_mm

- 조사 제안값: 2.0 (근거)
- 출처 대조 검증: 확인
- 내용: 새우와 나노 어종 구조물의 최소 벽 두께는 2.0mm다. 둘레선 4줄 × 0.45mm = 1.8mm를 올림한 값이다. 어항 동굴을 공개한 설계자들도 2mm 벽을 쓴다. printing.yaml의 min_wall_mm 1.2보다 크므로 이 값이 적용된다.
- 한계: 물속에서 긁고 청소할 때 벽이 얼마나 버티는지 잰 자료는 없다. 2.0은 1.8을 올림한 값이다.
- 출처:
  - https://help.prusa3d.com/article/watertight-prints_112324
    > You want to go with at least 3-4 perimeters for a single wall.
  - https://www.printables.com/model/96362-aquarium-decoration-textured-rock-cave-medium
    > Designed with 2mm walls and meant to be printed with 100% infill and no supports; thin walls in design make it unsuitable for significant re-sizing.
  - https://www.printables.com/model/1506162-aquarium-cave-shelter
    > Wall thickness: 2mm & 3mm
  - https://manual.slic3r.org/advanced/flow-math
    > spacing = extrusion_width - layer_height * (1 - PI/4)

### [small_fish] min_wall_thickness_mm

- 조사 제안값: 2.4 (임시)
- 출처 대조 검증: 확인
- 내용: small_fish 구조물의 최소 벽 두께는 2.4mm다. 바닥을 파거나 표면을 뒤지는 종(코리도라스·아피스토)과 손질·청소를 위해 여유를 더 둔 값이다. 근거 수치는 없고, 공개 설계에는 3mm 변형도 있다.
- 한계: 물고기가 PLA·PETG 표면을 긁어 깎는지에 대한 자료가 없다(표면을 긁는 안시는 이번 구분에서 뺐다).
- 출처:
  - https://www.printables.com/model/1506162-aquarium-cave-shelter
    > Wall thickness: 2mm & 3mm

### [all (shrimp·nano_fish·small_fish)] forbid_closed_voids (신규)

- 조사 제안값: true: 모든 개구부가 passable_min보다 작은 내부 공간 금지. 단단한 벽(채움 100%)이거나 물이 드나드는 열린 모양만 허용. 무게를 늘리려고 속에 모래·돌을 채우는 것도 금지 (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: true. 원칙(물이 돌지 않는 반쯤 닫힌 속 빈 공간 금지, 속에 돌·모래 채우기 금지)은 [근거·약함]. '모든 개구부가 passable_min보다 작으면 금지'라는 경계값은 [임시]
- 내용: 속 빈 공간에 작은 구멍만 나 있으면 물이 돌지 않아 산소가 없는 곳이 될 수 있다. 커뮤니티 글 10도 같은 결론을 냈다. 근거는 포럼 사례 두 건이다. 하나는 돌로 무게를 채운 속 빈 장식에서 냄새가 나다가 빼자 나아진 경우이고, 다른 하나는 물이 스며든 속 빈 그루터기 장식이다. 구멍을 잔뜩 뚫어도 같은 일이 생겼다는 증언이 있어 환기구로 보완하는 방식은 허용하지 않는다. 경계값을 passable_min으로 둔 것은 물고기가 들어가 안 보이는 곳에서 죽는 일을 막으려는 설계 선택이며, 수질 근거에서 나온 값은 아니다.
- 한계: 근거 약함: 포럼 사례 2건뿐이고 황화수소를 잰 기록도 없으며 3D 출력물 사례가 아니다. 예방 차원에서 커뮤니티 글 10과 같은 결론을 따랐다.
- 출처:
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 작은 틈만 난 속 빈 공간 금지
  - https://www.monsterfishkeepers.com/forums/threads/be-carefull-sealing-up-aquarium-decorations.181229/
    > What I think happened was that water seeped into the hollow cavity of the stump. With no real circulation there was perfect conditions for anarobic bacteria to start creating hydrogen sulfide gas.
  - https://fishprofiles.com/forums/General_Freshwater/Ornaments_Are_Bad_News/28572
    > There's nothing wrong with NON-hollow fake ornaments, but anything that makes any sort of anoxic pocket like that is bad, even sand or gravel that's too deep.
  - https://fishprofiles.com/forums/General_Freshwater/Ornaments_Are_Bad_News/28572
    > I started out the same way and tried several plastic rocks and stuff and they all did that even when I drilled them full of holes.
  - https://fishprofiles.com/forums/General_Freshwater/Ornaments_Are_Bad_News/28572
    > It was hollow so I stuck rocks in it to weigh it down and it was great until this week. I noticed that there was green floating stuff on the surface and a BAD smell.
  - https://help.prusa3d.com/article/watertight-prints_112324
    > Thick walls which require infill is often waste in this case. It can cause irregularities and may leak into the void between the inner and outer walls, creating a place where all kinds of nasty stuff can grow.

### [shrimp] allowed_materials

- 조사 제안값: 무착색 PETG만 (스테인리스·티타늄 노즐) (근거)
- 출처 대조 검증: 확인
- 내용: 새우 수조용 출력물은 무착색 PETG만 쓴다. 이미 게시한 커뮤니티 글 10의 조건과 같고, 무척추동물이 구리에 민감하다는 점을 고려한 예방 차원이다.
- 한계: 관상 새우를 출력물에 노출한 시험은 없다. PETG가 어항에서 안전하다고 증명된 것도 아니다.
- 출처:
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 새우·달팽이: 무착색 PETG + 스테인리스·티타늄 노즐만
  - https://help.prusa3d.com/article/food-safe-fdm-printing_112313
    > Natural/pure PETG-filament without any color, would be your best bet, but it's hard to say exactly what is in it.

### [nano_fish, small_fish] allowed_materials

- 조사 제안값: 무착색 PETG(1순위). 무착색 PLA는 담수이고 수온 26°C 이하일 때만 (근거)
- 출처 대조 검증: 확인
- 내용: 어류 수조용은 무착색 PETG를 1순위로 하고, 무착색 PLA는 담수에서 조건부로 허용한다. 커뮤니티 글 10의 결론과 같다. PLA는 25°C 물에서 1년 동안 거의 분해되지 않았지만 30°C에서는 6개월 뒤 열화가 나타났다. 오래 둘 물건은 PETG로 하라는 설계자 권고도 있다.
- 한계: 어항 수질에 안전하다고 증명된 소재는 없다. 수온 상한(26°C)은 [임시]다(다음 항목). NestForge는 수온과 담수·해수 여부를 입력받지 않으므로, 입력이 없으면 PETG만 권한다.
- 출처:
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 담수 25°C 안팎이면 무착색 PLA도 | 우린 물이 배아·윤충·물벼룩류에 무해했다(Zhu 2015). 직접 접촉 7일(Pérez-Davila 2022). 25°C에서 1년(Bagheri 2017). 30°C 이상에서는 열화가 빨라진다(Deroine 2014)
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > I recommend printing in PETG long term
  - https://help.prusa3d.com/article/food-safe-fdm-printing_112313
    > Natural/pure PETG-filament without any color, would be your best bet, but it's hard to say exactly what is in it.
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 담수 25°C 안팎이면 무착색 PLA도
  - https://www.printables.com/model/96362-aquarium-decoration-textured-rock-cave-medium
    > I recommend printing in PETG long term since PLA is biodegradable and the presence of heat and water will cause it to break down (though from all accounts I've read, it will still last for over a year).

### [nano_fish, small_fish] pla_max_water_temp_c (신규)

- 조사 제안값: 26 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 26 [임시] (25°C까지만 시험됨. 26은 경계가 아니라 고른 값)
- 내용: PLA는 수온 26°C 이하에서만 허용한다[임시]. Bagheri는 25°C 담수·해수에 1년 두어도 PLA 필름(두께 320µm)의 질량이 거의 줄지 않았다. Deroine(증류수)에서는 6개월 뒤 수평균 분자량이 25°C에서 10%, 30°C에서 15% 줄어 차이가 작았다. 다만 30°C에서는 말린 시편의 파단 연신율이 6개월 뒤 42% 줄었고, 큰 열화는 40°C부터 나타났다. 25~30°C 사이에 뚜렷한 경계가 있다는 자료는 없다. 26은 열대어 권장 수온(Aqua One 25~26°C)의 위쪽 값으로 고른 것이다. 구피처럼 28°C까지 견디는 종을 더 따뜻하게 키우면 PETG만 쓴다.
- 한계: Bagheri는 두께 320µm 필름, Deroine은 증류수 시험이다. 26°C는 시험한 온도 사이에서 고른 값이다. 지금은 수온을 입력받지 않는다.
- 출처:
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC6607129/
    > All other so‐called (bio)degradable polymers (PCL and PLA) did not show any significant degradability under tested conditions. Degradation rates of polymers were relatively same in FW and SW (Figure 1).
  - https://archimer.ifremer.fr/doc/00173/28376/26689.pdf
    > at 30°C, the increase in failure strain is significant after 1 month of immersion (+47%) but drops after 6 months (-42%). After 6 months at 40°C, the stress and the strain at break were greatly reduced, -85 and -92% respectively
  - https://cdn.shopify.com/s/files/1/0603/1969/5022/files/Aqua_One_Instructions.pdf
    > Tropicals 25 - 26 °C
  - https://www.rspca.org.uk/adviceandwelfare/pets/fish/environment
    > For example, guppies can tolerate 22–28ºC, while loaches need to be kept at 18–26ºC.
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC6607129/
    > The degradation studies were carried out in SW and FW under controlled conditions in a thermostatic chamber at 25 °C and under fluorescence light (16 h light and 8 h dark) for 1 year.
  - https://archimer.ifremer.fr/doc/00173/28376/26689.pdf
    > No change is observed at 25 and 30°C.
  - https://archimer.ifremer.fr/doc/00173/28376/26689.pdf
    > shows the mechanical behaviour of PLA samples after 6 months in distilled water at 25, 30

### [all (shrimp·nano_fish·small_fish)] forbidden_materials

- 조사 제안값: 레진(광경화), 나일론, 우드·금속·카본·실크·반짝이·야광·형광 혼합 필라멘트. ABS·ASA는 기본 추천에서 제외 (근거)
- 출처 대조 검증: 확인
- 내용: 레진 출력물은 넣지 않는다. 레진 출력물을 우린 물(추출액)에 노출된 제브라피시 배아는 24시간 안에 대부분 죽었다(Zhu 2015). (나머지는 원문과 같음)
- 한계: 혼합 필라멘트는 자료가 없어 예방 차원에서 뺀 것이다(근거 약함).
- 출처:
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC4691254/
    > By 24 h, the embryo survival rate was ca. 10% for VisiJet Crystal and 0% for the remaining SLA polymers
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 나일론·우드 빼기 | 3절(Banjo 2022, Islam 2026) | 강함(물성)
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 금속·카본·실크·반짝이·야광·형광 빼기 | 물속 자료가 거의 없다(7절).
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > ABS는 근거가 엇갈린다. 우린 물은 무해했지만(Zhu 2015) 직접 닿으면 독성이 있었다(Oskui 2016).
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC4691254/
    > Our data show that leachates from photopolymers substrata appear to be very toxic to vertebrates and several invertebrate indicator organisms.

### [all (shrimp·nano_fish·small_fish)] nozzle_material (출력 안내)

- 조사 제안값: 스테인리스 또는 티타늄 (황동 노즐 금지) (근거)
- 출처 대조 검증: 확인
- 내용: 노즐은 스테인리스나 티타늄으로 한다. 황동 노즐로 뽑은 기기는 스틸 노즐로 뽑은 것보다 납 농도가 7~12배 높았다.
- 한계: Rindelaub 2019는 50°C 의료기기 추출 조건이고, 양은 아주 적다. 출력물에서 어항 물로 녹아 나오는 금속을 잰 자료는 없다.
- 출처:
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC6530847/
    > The devices printed using the brass nozzle had 7–12 times greater concentrations of Pb compared to those printed using a steel nozzle.
  - https://help.prusa3d.com/article/food-safe-fdm-printing_112313
    > You would need a stainless-steel or a titanium nozzle if you are even considering printing with food in mind.
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC6530847/
    > placed in an incubator shaker for >72 hours at 50°C, as recommended by ISO 10993–12

### [all (shrimp·nano_fish·small_fish)] adhesives (출력 안내)

- 조사 제안값: 어항용 표시가 있는 실리콘·순간접착제 젤만. 식초 냄새가 난다고 어항용은 아님 (근거)
- 출처 대조 검증: 확인
- 내용: 부품을 붙일 때는 어항용 표시가 있는 접착제만 쓴다. 건축·가정용 실리콘에는 곰팡이 방지제가 들었을 수 있고, 아세트산을 내며 굳는다고 어항용인 것은 아니다.
- 한계: 접착제 자체의 수생 독성 시험은 없다. 가능하면 한 덩어리로 출력해 접착이 필요 없게 한다.
- 출처:
  - https://www.sera.de/en/service/faq/faq-detail/gluing-rocks-and-decoration-with-silicone
    > Construction or household silicone may contain fungicides that can lead to terrible consequences in an aquarium
  - https://www.sera.de/en/service/faq/faq-detail/gluing-rocks-and-decoration-with-silicone
    > silicones that cure by releasing acetic acid are automatically suitable for aquariums. This is simply wrong

### [all (shrimp·nano_fish·small_fish)] heater_contact_forbidden (배치 규칙, 신규)

- 조사 제안값: true (근거)
- 출처 대조 검증: 확인
- 내용: 구조물이 히터에 닿으면 안 된다. 여러 히터 설명서가 돌·장식물·자갈이 히터에 닿지 않게 하라고 한다. 닿으면 유리관이 고르지 않게 가열되어 약해지거나 갈라질 수 있기 때문이다. PLA는 열변형 온도가 57°C(0.45MPa)라 히터 유리에 닿은 부분이 변형될 수 있다.
- 한계: 배치기가 이 규칙을 적용하려면 히터 위치를 입력받아야 한다. 히터 유리 표면 온도를 잰 자료는 없다.
- 출처:
  - https://fluvalaquatics.com/ca/manuals/14880-4_T-Heater_Manual_NA_May7_21_AP_WEB.pdf
    > Be sure there are no rocks, decorations or gravel obstructions touching the heater to create uneven heat in the glass tube and weaken it.
  - https://cdn.shopify.com/s/files/1/0603/1969/5022/files/Aqua_One_Instructions.pdf
    > The heater should not come in contact with the gravel or substrate. This may cause a hot spot on the glass and cause the heater to crack.
  - https://cdn.shopify.com/s/files/1/0380/5149/files/Bambu_PLA_Basic_Technical_Data_Sheet.pdf
    > Heat Deflection Temperature ISO 75 0.45 MPa 57 °C
  - https://www.allpondsolutions.co.uk/cdn/shop/files/AH-instruction-manual-full_range.pdf
    > Ensure the location of the heater is unobstructed by rocks, decorations or gravel and there is free movement of water to ensure even heat dispersal.
  - https://www.furrycritter.com/pages/articles/fish/heater_placement.htm
    > Heater elements running directly against surfaces create hot spots that can crack glass, melt plastic decorations, burn wood, and injure fish.

### [all (shrimp·nano_fish·small_fish)] heater_clearance_mm (경고만, 신규)

- 조사 제안값: 50 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 50 [임시] (제조사가 아닌 사육 안내의 '1~2인치(25~50mm)' 권고 중 위쪽 값)
- 내용: 히터와 구조물 사이를 50mm 이상 띄우라고 경고한다. 제조사 설명서는 거리 수치 없이 닿지 않게, 물이 잘 흐르게 하라고만 한다. 제조사가 아닌 사육 안내 중에는 히터 둘레에 1~2인치(약 25~50mm) 여유를 두라는 글이 있다. 50은 그 위쪽 값이며, PLA 열변형 온도를 고려한 보수적인 [임시] 값이다.
- 한계: 근거 약함: Fluval·Aqua One·All Pond Solutions·Juwel·Eheim·Dennerle·Hydor 설명서 어디에도 cm 수치가 없다. 검색 요약의 '2인치'는 원문에서 확인되지 않아 쓰지 않았다. 히터 위치 입력이 필요하다.
- 출처:
  - https://www.allpondsolutions.co.uk/cdn/shop/files/AH-instruction-manual-full_range.pdf
    > Ensure the location of the heater is unobstructed by rocks, decorations or gravel and there is free movement of water to ensure even heat dispersal.
  - (저장소) content/community-drafts/10-aquarium-evidence.md
    > 히터에 닿지 않게 | Fluval 설명서와 PLA의 온도 의존 열화(3절)
  - https://www.furrycritter.com/pages/articles/fish/heater_placement.htm
    > Heater elements running directly against surfaces create hot spots that can crack glass, melt plastic decorations, burn wood, and injure fish. One to two inches of clearance on all sides of the heating element provides adequate safety margin.

### [all (shrimp·nano_fish·small_fish)] max_cleaning_water_temp_c + 세척 방법 (사용자 안내)

- 조사 제안값: 40°C 이하. 환수 때 뺀 어항 물과 부드러운 솔만 쓴다. 세제·소독제·끓는 물·뜨거운 수돗물은 쓰지 않는다 (임시)
- 출처 대조 검증: 확인
- 내용: 어항용 출력물은 햄스터 용품과 달리 물로만 씻는다. 판매사 안내는 환수 때 뺀 물로 헹구고 세제·소독제를 쓰지 말라고 한다. Prusa는 층 사이 홈이 잔여물을 붙잡는다고 한다. 흔히 권하는 끓는 물 소독은 PLA(열변형 54~57°C)와 PETG(68°C)를 변형시킬 수 있다. 방법은 출처가 있지만 40°C라는 수치는 근거가 없어 이 항목은 [임시]다.
- 한계: 솔질로 출력물이 얼마나 닳는지 시험한 자료는 없다. Charterhouse는 묽은 락스도 소개하지만, 커뮤니티 글 10에 맞춰 물로만 씻도록 했다.
- 출처:
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-clean-and-maintain-aquarium-ornaments-without-harming-your-tank
    > Whenever possible, rinse ornaments using water removed during a routine water change. This helps preserve beneficial bacteria while removing loose debris. Avoid using hot tap water for routine cleaning.
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-clean-and-maintain-aquarium-ornaments-without-harming-your-tank
    > Never use: Household cleaners Washing-up liquid Soap Detergents Glass cleaners Disinfectants Even tiny residues can be harmful to fish, shrimp, and invertebrates.
  - https://help.prusa3d.com/article/food-safe-fdm-printing_112313
    > The grooves in between those layers are a seedbed for bacteria as they are almost impossible to clean properly, and will hold residue.
  - https://cdn.shopify.com/s/files/1/0380/5149/files/Bambu_PLA_Basic_Technical_Data_Sheet.pdf
    > Heat Deflection Temperature ISO 75 1.8 MPa 54 °C
  - https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/c34f5f47-tds_prusament-petg_n_de.pdf
    > Wärmeformbeständigkeit (0,45 MPa) [°C] 68 ISO 75
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-clean-and-maintain-aquarium-ornaments-without-harming-your-tank
    > Avoid using hot tap water for routine cleaning.
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-clean-and-maintain-aquarium-ornaments-without-harming-your-tank
    > Soak in a very diluted bleach solution.

### [all (shrimp·nano_fish·small_fish)] max_height_to_base_ratio (넘어짐, 신규)

- 조사 제안값: 1.5 (임시)
- 출처 대조 검증: 확인
- 내용: 구조물 높이는 바닥 짧은 변의 1.5배 이하로 한다. PETG 출력물의 물속 무게는 마른 무게의 약 21%(PLA 약 19%)라서 땅 파는 물고기나 물살에 쉽게 밀리고 기운다. 균일한 블록이면 높이/밑변 1.5에서 넘어지는 기울기가 약 34°다. 판매사도 흔들리는 장식은 물고기를 넣기 전에 바로잡으라고 하고, 무너진 구조물 밑에 물고기가 갇힐 수 있다고 경고한다.
- 한계: 기준 비율·각도에는 출처가 없다. 물살 속도 자료가 없어 미끄러짐은 계산하지 않았다.
- 출처:
  - https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/c34f5f47-tds_prusament-petg_n_de.pdf
    > Dichte [g/cm3] 1.27 ISO 1183
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-secure-aquarium-ornaments-safely-and-effectively
    > Ensure the ornament sits flat on the substrate. Avoid Wobbling Any rocking or movement should be corrected before fish are introduced.
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-secure-aquarium-ornaments-safely-and-effectively
    > Fish can become trapped beneath unstable structures or injured by shifting ornaments.


## C. 수조 크기·수심·바닥재·마릿수

### [shrimp] enclosure_min_volume_l (신규)

- 조사 제안값: 10 (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 10 (경고, OATA 하한). PFK의 '15L 미만은 부적합'을 보조 권장 경고(15L)로 함께 표시. 아마노 등 큰 종은 20L
- 내용: 새우 수조 최소 부피 경고값은 10L다. OATA는 소형 새우 무리에 10L 이상, 아마노 같은 큰 종에 약 20L를 권하고, 물고기와 함께 키우면 더 커야 한다고 한다. 영국 잡지 Practical Fishkeeping은 15L 미만은 적합하지 않다고 해 더 엄격하다. 법적 수치 기준은 없다. 스위스 동물보호령은 진새우류(Caridea)를 갑각류(Panzerkrebse) 정의에서 뺀다. 오스트리아 동물보호법 §3(2)는 사육 규정(2. Hauptstück)을 십각류(새우 포함)에도 적용하지만, 수치를 정한 2. 동물사육령은 척추동물만 다룬다.
- 한계: 업계 단체 안내 하나뿐이고 법적 기준은 없다. 판매점 자료(2~5갤런)는 기준이 엇갈린다. Neocaridina 사육 밀도 연구는 찾지 못했다.
- 출처:
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-invertebrates/how-to-look-after-freshwater-shrimp-and-snails/
    > It is recommended that an aquarium of at least 10 litres is used for a group of small freshwater shrimp or snails. Larger species, such as apple snails or Amano shrimp, will require a slightly larger aquarium of approximately 20 litres. This will need to be larger if keeping freshwater shrimp or sna…
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Diese Verordnung gilt für die Haltung von Wirbeltieren, die nicht unter die 1. Tierhaltungsverordnung, BGBl. II Nr. 485/2004, fallen.
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Panzerkrebse: Krebstiere der Unterordnung Pleocyemata, ausgenommen der Teilordnungen Stenopodidea und Caridea.
  - https://www.chewy.com/education/fish/general/cherry-shrimp-care-sheet
    > Minimum tank size : 2–5 gallons (guidance varies)
  - https://www.practicalfishkeeping.co.uk/features/frequently-asked-questions-on-neocaridina-shrimps/
    > they can still be kept in very small tanks if well planted and with adequate filtration, so are popular in nano and pico aquariums as small as 15 l/3.3 gal. Anything less is not really suitable, as six neocaridina can quickly become 100 in a short time!
  - https://www.jusline.at/gesetz/tschg/paragraf/3
    > Dieses Bundesgesetz gilt für alle Tiere. (2) Absatz 2 Die §§ 7 bis 11 und das 2. Hauptstück, mit Ausnahme des § 32 , gelten nur für Wirbeltiere, Kopffüßer und Zehnfußkrebse.
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Panzerkrebse: Krebstiere der Unterordnung Pleocyemata , ausgenommen der Teilordnungen Stenopodidea und Caridea .

### [nano_fish] enclosure_min_volume_l (신규)

- 조사 제안값: 54 (입력 치수로 계산한 총부피 L×W×H) (근거)
- 출처 대조 검증: 확인
- 내용: 나노 어종 수조 최소 부피는 54L다. 오스트리아 법은 작은 종도 54L 미만 수조에서 계속 키우는 것을 금지한다. 독일 BMEL 감정서는 54L를 최소, 60L를 권장으로 본다. 스위스 BLV는 3.5~4cm 소형 테트라에게도 54L 이상을 요구한다. 영국 OATA는 45L로 더 느슨하다.
- 한계: 독일 감정서에는 '특히 작은 종'에게 다른 크기를 허용하는 예외가 있고, 2025년부터 개정 중이다. BLV는 난태생어(엔들러 포함) 10마리에 100L를 권해 이 값보다 엄격하다. 54L는 외형 치수로 계산한 총부피로 정의되어 있다.
- 출처:
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Eine dauerhafte Haltung auch kleiner Arten in Aquarien unter 54 Liter ist verboten.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische.html
    > Je größer das Wasservolumen eines Aquariums ist, desto stabiler ist die Wasserqualität, daher sollte das Aquarienvolumen für die dauerhafte Haltung 60 Liter nicht unterschreiten. 54 Liter Aquariumvolumen sind als Mindestmaß für die dauerhafte Haltung anzusehen.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Eine Mindestlänge von 80 bis 100 cm ist zu empfehlen. Für die Haltung von sehr kleinen Fischen wie zum Beispiel Zwergsalmlern (3,5 bis 4 cm) sollte das Aquarium mindestens ein Volumen von 54 Litern aufweisen, was 60L × 30B × 30H cm entspricht.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-tetras-and-pencilfish/
    > It is recommended that an aquarium of at least 45 litres for a small shoal of a smaller species and at least an 80 litre aquarium for the larger species (5cm+).
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische.html
    > 54 Liter Aquariumvolumen sind als Mindestmaß für die dauerhafte Haltung anzusehen.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Ein Mindestvolumen von 54 Litern (60L × 30B × 30H cm / Länge × Breite × Höhe) sollte nicht unterschritten werden.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Je nach Art sollten die Salmler in mittleren (ab 15 Individuen, z. B. Phantomsalmler) oder grösseren Gruppen (z. B. ab 30 bei Neonsalmlern) gehalten werden. Daher ist auch bei kleinen Salmlern in einem Artaquarium ein Mindestvolumen von 100 Litern (Masse ca. 80L × 35B × 40H cm) empfehlenswert.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Daher sollten sie in einem eher langgestreckten Aquarium ab mindestens 150 Litern (ca. 100L × 40B × 40H cm) gehalten werden.

### [small_fish] enclosure_min_volume_l (신규)

- 조사 제안값: 54 (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 54 (법적 절대 하한) + 종별 상향 경고: 코리도라스 80L(OATA), 아피스토 한 쌍 60L(OATA)·100L(BLV), 구피 무리 10마리 100L(BLV), 작은 코리 외 160L(BLV), 래버린스 합사 150L(BLV)
- 내용: 소형 어종 수조의 절대 하한은 54L다(오스트리아 법은 54L 미만에서 계속 키우는 것을 금지한다. BLV는 베타에게도 54L 이상을 권하고 30L 미니 수조를 피하라고 한다). 그러나 이 구분의 대표 종 대부분에는 54L보다 큰 권장치가 있다. OATA는 코리 무리에 80L, 아피스토 한 쌍에 60L를 권한다. BLV는 아피스토 한 쌍에 100L, 난태생어 10마리에 100L, 작은 코리 외의 코리에 160L를 권한다. 54L는 '미만이면 경고'로만 쓰고, 종별 권장치를 따로 안내해야 한다.
- 한계: BLV는 작은 코리 외의 코리도라스 종에게 160L를 권해 더 엄격하다. 베타를 이 구분에 넣으면 영미권 기준(20L)보다 엄격해진다. 어느 기준을 따를지는 정책 결정이 필요하다.
- 출처:
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Eine dauerhafte Haltung auch kleiner Arten in Aquarien unter 54 Liter ist verboten.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Kampffische sind zwar nicht überaus schwimmfreudig, trotzdem sollte das Aquarium mindestens 54 Liter haben. Auf eine Haltung in den üblicherweise angebotenen Mini-Aquarien (30 Liter) sollte verzichtet werden.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Eine Gruppe der kleinen Arten braucht ein Aquarium mit mindestens 54 Liter, was einer Grösse von 60L × 30B × 30H cm entspricht. Alle anderen Arten sollte man in Aquarien ab 160 Liter (100L × 40B × 40H cm) halten.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-freshwater-catfish/
    > It is recommended that an aquarium of at least 80 litres is used for a shoal of the smaller species, such as Corydoras or for the smaller pleco species.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-siamese-fighting-fish-bettas/
    > It is recommended that an aquarium of at least 20 litres for a single male and at least a 60 litre aquarium for a group of females.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Für ein Paar braucht es ein Aquarium mit einem Mindestvolumen von 100 Litern (ca. 80L × 35B × 40H cm).
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Das Mindestvolumen liegt bei 100 Litern (ca. 80L × 35B × 40H cm) für eine Gruppe von 10 Tieren.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-dwarf-cichlids/
    > If just a pair is being kept, it is recommended that they are kept in an aquarium of at least 60 litres.

### [shrimp] enclosure_min_floor_mm

- 조사 제안값: 검사하지 않음 (부피 10L만 검사) (임시)
- 출처 대조 검증: 확인
- 내용: 새우 수조는 바닥 면적 기준을 두지 않는다. 바닥 면적을 준 출처가 없어 OATA 부피 기준만 쓴다.
- 한계: 다른 갈래가 낸 [250, 200](10L를 수심 200mm로 역산)은 출처가 없는 값이라 뺐다. 스키마에서 이 필드를 선택값으로 바꿔야 한다.
- 출처:
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-invertebrates/how-to-look-after-freshwater-shrimp-and-snails/
    > It is recommended that an aquarium of at least 10 litres is used for a group of small freshwater shrimp or snails. Larger species, such as apple snails or Amano shrimp, will require a slightly larger aquarium of approximately 20 litres. This will need to be larger if keeping freshwater shrimp or sna…

### [nano_fish] enclosure_min_floor_mm

- 조사 제안값: [600, 300] (근거)
- 출처 대조 검증: 확인
- 내용: 나노 어종 수조 최소 바닥은 600×300mm다. 오스트리아 법과 독일 BMEL 표는 네온 등에 '60cm' 등급을 주고, 오스트리아 법은 이를 60×30×30cm(54L)로 정의한다. Seriously Fish도 네온에 바닥 60×30cm 이상을 권한다.
- 한계: SF는 엠버·보라라스에 45×30cm를 권해 더 느슨하다. BLV는 길이 80~100cm를 권한다. 높이(30cm)는 비교하지 않는다.
- 출처:
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > 60 cm = 60 cm x 30 cm x 30 cm (54 Liter (l))
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische-tabelle.html
    > P. innesi (Neonsalmler) | X | _ | 20 - 28 | X | X) | _ | _ | Gesellig | 60 |
  - https://www.seriouslyfish.com/species/paracheirodon-innesi/
    > An aquarium with base dimensions of 60 ∗ 30 cm 24 ∗ 12 in or larger is recommended.
  - https://www.seriouslyfish.com/species/boraras-brigittae/
    > Though small it still needs space to swim and dominant males will form temporary territories when spawning so a group is best kept in an aquarium with base dimensions of at least 45 ∗ 30 cm 18 ∗ 12 in .
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische.html
    > 60 cm = 60 x 30 x 30 cm (54 l) oder 60 cm = 60 x 30 x 35 cm (63 l)

### [small_fish] enclosure_min_floor_mm

- 조사 제안값: [600, 300] (근거)
- 출처 대조 검증: 확인
- 내용: 소형 어종 수조 최소 바닥도 600×300mm다. 독일 BMEL 표와 오스트리아 법은 코리도라스 아에네우스와 베타에 모두 '60cm' 등급을 준다. SF는 베타 수컷 한 마리나 한 쌍에 45×30cm면 된다고 하지만, 코리 아에네우스에는 80×30cm를 권한다.
- 한계: 브리슬노즈(안시스트루스)는 80cm 등급(80×35×40, 112L)이라 이 구분에서 뺐다. BLV는 작은 코리 외의 코리 종에게 100×40cm를 권한다.
- 출처:
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische-tabelle.html
    > Corydoras aeneus (Metallpanzerwels) | X | X) | 20 - 30 | X | X) | _ | _ | Gesellig | 60 |
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische-tabelle.html
    > Betta splendens (Schleierkampffisch) | X | _ | 24 - 30 | _ | X | _ | Artspezi- fische Aggressi- vität3) | Harem | 60 |
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > 60 cm = 60 cm x 30 cm x 30 cm (54 Liter (l))
  - https://www.seriouslyfish.com/species/corydoras-aeneus/
    > Base dimensions of 80 ∗ 30 cm 31 ∗ 12 in or equivalent are recommended for long-term care.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische-tabelle.html
    > Apistogramma agassizii (Agassiz´Zwergbuntbarsch) | X | _ | 22 - 30 | X | X) | _ | _ | Harem | 60
  - https://www.seriouslyfish.com/species/betta-splendens/
    > An aquarium with base measurements of 45 ∗ 30 cm 18 ∗ 12 in or equivalent is large enough for a single male or pair.

### [nano_fish] liters_per_cm_body + ref_body_length_mm (마릿수 비례 부피, 신규)

- 조사 제안값: 0.5 L/cm × 30mm = 마리당 1.5 L → 필요 부피 = max(54, 마리 수 × 1.5) (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 0.5 L/cm × 30mm = 마리당 1.5 L → max(54, n × 1.5) (계산은 맞음). 출처 URL만 고침: BLV 소책자 PDF 8쪽, 또는 fedlex 부속서 2 표 8
- 내용: 스위스 동물보호령 부속서 2 표 8은 수조 최소 부피를 '등급별 실제 몸길이(cm) × L/cm × 마리 수'의 합으로 계산하고, 몸길이 5cm 이하는 0.5L/cm다. nano_fish의 기준 몸길이를 SL 30mm로 잡으면 마리당 1.5L가 된다. 이 값은 스위스에서만 효력이 있다. 독일 BMEL 감정서와 오스트리아 법은 구속력 있는 사육 밀도 수치를 두지 않는다고 명시한다.
- 한계: 스위스 법은 실제 몸길이로 계산하는데, 여기서는 구분 상한을 써서 보수적으로 잡았다. 이 식이 54L를 넘으려면 37마리 이상이어야 하므로 실제로는 54L 기준이 정한다.
- 출처:
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Zur Berechnung der Mindestvolumina für Aquarien und Teiche ist für jede Grössenklasse die aktuelle Körperlänge der Fische mit der entsprechenden Literzahl und mit der Fischanzahl zu multiplizieren. Das Mindestvolumen in Litern ergibt sich aus der Summe der Produkte für die einzelnen Grössenklassen. …
  - https://www.blv.admin.ch/aquarienfisch
    > Grössenklasse Körperlänge (cm) Anzahl Liter pro cm Fisch 1 bis 5 0,5 2 bis 10 0,75
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Grössenklasse KL (in cm) Anzahl Liter pro cm Fisch KL (in cm) Anzahl Liter pro cm Fisch 1 bis 5 0,5 bis 10 2 2 bis 10 0,75
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > 6 Malawi-Buntbarsche mit einer Körperlänge von 15 cm (Grössenklasse 3) benötigen 15 Liter pro Fisch und mindestens ein 90-Liter-Aquarium.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische.html
    > Verbindliche Angaben zur Besatzdichte sind nicht sinnvoll, da sie von zu vielen Variablen abhängen und deshalb zu stark vereinfacht werden müssten.
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Verbindliche Angaben zur Besatzdichte sind aufgrund vieler Variablen nicht möglich.
  - https://eheim.com/media/pdf/ae/bb/b7/7991210_Ratgeber_EHEIM_Aquarien_2019.pdf
    > Faustregel: 1 cm Fisch braucht 2 l Wasser

### [small_fish] liters_per_cm_body + ref_body_length_mm (마릿수 비례 부피, 신규)

- 조사 제안값: 0.75 L/cm × 75mm = 마리당 약 5.6 L → 필요 부피 = max(54, 마리 수 × 5.6) (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 0.75 L/cm × 75mm = 마리당 5.625 L → max(54, n × 5.625) (계산은 맞음). 출처 URL만 고침: BLV 소책자 PDF 8쪽, 또는 fedlex 표 8
- 내용: 스위스 동물보호령 표 8의 크기 등급 2(몸길이 10cm 이하)는 0.75L/cm다. small_fish의 기준 몸길이를 SL 75mm로 잡으면 마리당 약 5.6L가 되고, 10마리부터 54L를 넘는다. 몸길이 5cm 이하인 종(판다 코리, 구피 수컷 등)은 실제로 등급 1(0.5L/cm)이므로 과하게 잡힌다. 스위스에서만 효력이 있는 규정이고, 독일·오스트리아는 사육 밀도 수치를 거부한다.
- 한계: 구분 상한으로 계산해 판다 코리(SL 50mm) 같은 작은 종에게는 과하게 잡힌다. 다른 갈래는 등급 상한 100mm(마리당 7.5L)를 썼다.
- 출처:
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Zur Berechnung der Mindestvolumina für Aquarien und Teiche ist für jede Grössenklasse die aktuelle Körperlänge der Fische mit der entsprechenden Literzahl und mit der Fischanzahl zu multiplizieren. Das Mindestvolumen in Litern ergibt sich aus der Summe der Produkte für die einzelnen Grössenklassen. …
  - https://www.blv.admin.ch/aquarienfisch
    > Grössenklasse Körperlänge (cm) Anzahl Liter pro cm Fisch 1 bis 5 0,5 2 bis 10 0,75
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Das Beispiel beschreibt das gesetzlich geforderte Minimum. Es wird angeregt, die Aquarienmasse zu berücksichtigen, die in dieser Broschüre empfohlen werden.
  - https://www.seriouslyfish.com/species/corydoras-aeneus/
    > Standard length 75 mm SL
  - https://eheim.com/media/pdf/ae/bb/b7/7991210_Ratgeber_EHEIM_Aquarien_2019.pdf
    > Faustregel: 1 cm Fisch braucht 2 l Wasser

### [nano_fish] min_water_depth_mm (신규)

- 조사 제안값: 30 (근거)
- 출처 대조 검증: 확인
- 내용: 스위스 동물보호령은 수심이 가장 큰 물고기 몸길이의 1배 이상이어야 한다고 정한다(길이 3배, 폭 2배와 함께). nano_fish에서 가장 큰 네온의 SL 30mm를 넣으면 최소 수심은 30mm다. 길이 90mm·폭 60mm 조건은 60×30cm 바닥 기준이 이미 넘는다.
- 한계: 보통 수조에서는 늘 만족하는 값이다. 수심은 수조 높이에서 공기층을 뺀 값으로 계산한다(입력 정의를 확인해야 함). 다른 갈래는 등급 상한 50mm를 썼다.
- 출처:
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Beckenlänge: mind. 3× Körperlänge grösster FischBeckenbreite: mind. 2× Körperlänge grösster FischWassertiefe: mind. 1× Körperlänge grösster Fisch
  - https://www.seriouslyfish.com/species/paracheirodon-innesi/
    > Standard length 30 mm SL
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Beckenlänge: mind. 3× Körperlänge grösster Fisch Beckenbreite: mind. 2× Körperlänge grösster Fisch Wassertiefe: mind. 1× Körperlänge grösster Fisch

### [small_fish] min_water_depth_mm (신규)

- 조사 제안값: 75 (근거)
- 출처 대조 검증: 확인
- 내용: 같은 스위스 조항으로, small_fish에서 가장 긴 종의 SL 75mm(코리 아에네우스·아피스토 수컷)를 넣으면 최소 수심은 75mm다.
- 한계: 스위스에서만 효력이 있는 법이다. 다른 갈래는 등급 상한 100mm를 썼다.
- 출처:
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Beckenlänge: mind. 3× Körperlänge grösster FischBeckenbreite: mind. 2× Körperlänge grösster FischWassertiefe: mind. 1× Körperlänge grösster Fisch
  - https://www.seriouslyfish.com/species/corydoras-aeneus/
    > Standard length 75 mm SL
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Wassertiefe: mind. 1× Körperlänge grösster Fisch
  - https://www.seriouslyfish.com/species/apistogramma-agassizii/
    > Standard length ♂ 75 · ♀ 50 mm SL

### [shrimp] liters_per_cm_body / min_water_depth_mm

- 조사 제안값: 적용하지 않음 (임시)
- 출처 대조 검증: 확인
- 내용: 스위스 몸길이 비례 부피와 최소 수심 규정은 물고기용이고, 갑각류 규정도 진새우류(Caridea)를 뺀다. 새우에 대한 수치 출처가 없어 이 두 검사는 하지 않는다.
- 한계: 새우 사육 밀도 연구를 찾지 못했다.
- 출처:
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Panzerkrebse: Krebstiere der Unterordnung Pleocyemata, ausgenommen der Teilordnungen Stenopodidea und Caridea.
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Tabelle 8 Mindestanforderungen für das Halten von Fischen zu Zierzwecken

### [nano_fish, small_fish] substrate_depth_assumed_mm (신규)

- 조사 제안값: 50 (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 50은 [임시]로 낮추고 '수초 수조 기본값'으로만 쓴다. 모래 바닥(코리도라스 등) 프리셋은 15mm 정도로 두고, 사용자 입력을 우선한다
- 내용: 어류 수조 바닥재 두께 50mm는 수초 수조 기준이다. Dennerle 설명서(영양토 1.5~3cm + 자갈 3.5~6cm)와 EHEIM 안내서(앞쪽 5cm에서 뒤로 높여 총 5~8cm)의 하한이다. 코리도라스 전문가 Ian Fuller는 고운 모래나 자갈을 최대 15mm까지만 깔라고 권하고, 법·감정서에는 두께 수치가 없다. 그래서 수조 전체의 기본값으로는 [임시]이고, 사용자 입력으로 받아야 한다. 바닥재를 뒤로 높이 쌓으면 뒤쪽은 80mm까지 될 수 있다.
- 한계: 특정 제품의 설명서 값이다. Tropica·Fluval 값은 원문을 확인하지 못했다. 수초가 없는 베타 수조 등은 더 얇게 깐다. 사용자 입력으로 받는 편이 낫다.
- 출처:
  - https://dennerle.com/en/products/substrate/nutrient-substrate/deponit-mix-professional-10in1/
    > 1. Spread nutrient soil 1.5 – 3 cm high on the aquarium floor. 2. Cover with aquarium gravel 3.5 – 6 cm high.
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > 3. Bodengrund ( Sand, Kies, Steine)
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Als Bodengrund sollte feiner Sand oder feiner Rundkies verwendet werden, damit sich die Panzerwelse beim Durchwühlen des Bodens nicht die Barteln verletzen.
  - https://ornamentalfish.org/wp-content/uploads/Catfish-Sept-2022.pdf
    > All catfish have sensitive barbels on their head, so aquarium sand or fine gravel should be placed on the bottom of the aquarium to prevent injury to them.
  - https://eheim.com/media/pdf/ae/bb/b7/7991210_Ratgeber_EHEIM_Aquarien_2019.pdf
    > Drei Schichten: 1. Depotdünger, 2. KiesBodengrunddünger-Mischung (2 cm), 3. Kiesschicht (3 – 4 cm); Kies mittlerer Körnung (2 – 3 mm), nicht zu hell; Boden nach hinten leicht ansteigend (5 – 8 cm Gesamthöhe).
  - https://www.corydorasworld.com/articles/ian-fuller/starting-with-corydoras
    > My recommendation is the use of fine smooth gravel or a course grained smooth sand, to a maximum depth of 15 millimeters this allows the catfishes to reach through to the base glass of the tank and find all the particles of food that have penetrated deep into the substrate.

### [shrimp] substrate_depth_assumed_mm (신규)

- 조사 제안값: 30 (임시)
- 출처 대조 검증: 확인
- 내용: 새우 수조의 바닥재 두께 기본값은 30mm다. 새우 수조에서 바닥재 두께를 다룬 수치를 찾지 못했다.
- 한계: 출처가 없다. OATA는 '모래나 고운 자갈'만 말한다. 사용자 입력으로 받는 편이 낫다.
- 출처:
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-invertebrates/how-to-look-after-freshwater-shrimp-and-snails/
    > Sand or fine gravel is important for some species as they need to be able to move through it to find food.

### [all (shrimp·nano_fish·small_fish)] air_gap_mm (수면~수조 윗가장자리, 신규)

- 조사 제안값: 30 (임시)
- 출처 대조 검증: 일부 수정 — 고친 값: 30 — 태그를 [근거]로 올릴 수 있다(EHEIM 설명서 '약 3cm(2~3cm) 아래까지'). 모델마다 달라 사용자 입력을 우선한다
- 내용: 수면은 수조 윗가장자리보다 30mm 아래에 있다고 본다. EHEIM 안내서는 수조 윗가장자리에서 약 3cm(2~3cm) 아래까지 물을 채우라고 한다. Juwel 설명서는 표시된 수위선까지 채우라고만 한다. 54L 같은 표준 부피는 외형 치수로 계산한 총부피다. 베타 같은 공기 호흡어는 수면과 뚜껑 사이에 공기층이 있어야 한다.
- 한계: Eheim 안내서의 '약 3cm 아래까지'는 검색 요약에서만 봤고 원문을 열지 못했다. 사용자 입력으로 받는 편이 낫다.
- 출처:
  - https://www.juwel-aquarium.de/website/Anleitungen/Aquarien/Rio_Line/GB_Instruction_Manual_Rio_Line_LED.pdf
    > Slowly ﬁll the aquarium with water through the ﬁlter up to the water level line.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische.html
    > 60 cm = 60 x 30 x 30 cm (54 l) oder 60 cm = 60 x 30 x 35 cm (63 l)
  - https://ornamentalfish.org/wp-content/uploads/Bettas-Siamese-Fighting-Fish-Sept-2022.pdf
    > It is recommended to leave at least a small gap between the water surface and any cover glasses (glass panels used to prevent evaporation in some aquariums), to allow these species to access air if they wish.
  - https://eheim.com/media/pdf/ae/bb/b7/7991210_Ratgeber_EHEIM_Aquarien_2019.pdf
    > Handwarmes Leitungswasser bis ca. 3 cm zum Beckenrand
  - https://eheim.com/media/pdf/ae/bb/b7/7991210_Ratgeber_EHEIM_Aquarien_2019.pdf
    > bis knapp (ca. 2-3 cm) zum oberen Beckenrand
  - https://www.zooplus.co.uk/pictures/product/Eheim%20Aquarium%20Guide%20-%20Tips%20for%20Beginners.pdf
    > Lukewarm tap water up to approx. 3 cm below aquarium top.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Es muss darauf geachtet werden, dass zwischen Wasseroberfläche und Abdeckung Luft vorhanden ist.

### [all (shrimp·nano_fish·small_fish)] structure_top_clearance_mm (구조물 꼭대기~수면, 햄스터 gap_trap_ceiling 대체, 신규)

- 조사 제안값: shrimp 30, nano_fish 30, small_fish 75 (= max(passable_min, 구분 최대 몸길이)) (임시)
- 출처 대조 검증: 확인
- 내용: 구조물 꼭대기는 수면보다 위의 값만큼 아래에 있어야 한다. 스위스 '수심 ≥ 가장 큰 물고기 몸길이 1배'를 구조물 위 물 깊이에도 적용한 해석이다. 그러면 물고기가 구조물 위로 지나갈 수 있고, 베타·구라미·코리도라스가 수면에서 공기를 마실 수 있다. 바닥 유리에 놓는다면 최대 구조물 높이 = 수조 높이 − air_gap − 이 값이다(예: 300mm 수조에서 nano 240, small 195).
- 한계: 법 조문이 직접 요구하는 것이 아니라 유추한 해석이다. 구조물 높이 상한을 직접 정한 출처는 없다. 다른 갈래는 passable_min(nano 20, small 45)이나 등급 상한(nano 50, small 100)을 제안했다. 수조 높이 입력이 유리 높이인지 수위인지 확인해야 한다.
- 출처:
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Beckenlänge: mind. 3× Körperlänge grösster FischBeckenbreite: mind. 2× Körperlänge grösster FischWassertiefe: mind. 1× Körperlänge grösster Fisch
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Der Zugang zur Oberfläche muss stellenweise frei sein. Abgedeckte Aquarien müssen oberhalb genügend Raum aufweisen, damit die Fische Luft schöpfen können (Luftatmung).
  - https://kb.rspca.org.au/knowledge-base/how-should-i-care-for-my-siamese-fighting-fish/
    > Siamese fighting fish require occasional surface air, even if water oxygen is plentiful, so there must be some space between the water and the tank lid in which to take in air.
  - https://www.seriouslyfish.com/species/betta-splendens/
    > Keep the aquarium well-covered and do not fill it to the top since like all Betta spp. it requires occasional access to the layer of humid air that will form above the water surface, and is an excellent jumper.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Es kann vorkommen, dass sie an die Oberfläche schwimmen, um Luft zu schlucken.

### [shrimp] min_recommended_count (신규)

- 조사 제안값: 5 (미만이면 경고) (근거)
- 출처 대조 검증: 확인
- 내용: 새우는 무리 지어 사는 동물이라 5마리 이상 함께 키우기를 권한다. OATA 안내의 값이다.
- 한계: 출처는 OATA 한 곳이다. 번식 군체로 10~15마리를 권하는 자료는 판매점·블로그뿐이다.
- 출처:
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-invertebrates/how-to-look-after-freshwater-shrimp-and-snails/
    > Whilst snails are not social creatures, shrimp species usually are and should be kept in groups of at least five in the home aquarium.
  - https://www.practicalfishkeeping.co.uk/features/frequently-asked-questions-on-neocaridina-shrimps/
    > I prefer to keep them in groups of at least six, as in smaller numbers they can become shy.

### [nano_fish] min_recommended_count (신규)

- 조사 제안값: 권장 10 (미만이면 경고), 5 미만이면 강한 경고 (근거)
- 출처 대조 검증: 확인
- 내용: 나노 어종은 10마리 이상 무리를 권하고, 5마리 미만이면 강하게 경고한다. BLV는 카디널·제브라다니오에 최소 10마리를 요구하고, SF는 8~10마리를 권한다. 동료심사 연구에서도 네온은 10마리 무리일 때 공격 행동이 가장 적고 무리 짓기가 가장 많았다. 오스트리아 법과 독일 감정서는 'Gesellig' 종을 최소 5마리로 정하고, OATA도 5마리 이상을 권한다.
- 한계: Saxby 2010은 10L 실험 수조에서 했고, 원문 대신 PFK 요약으로 확인했다. 5마리와 10마리 사이는 시험하지 않았다. 엔들러는 수컷보다 암컷이 많아야 한다는 성비 안내가 따로 필요하다.
- 출처:
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Er sollte möglichst in Gruppen ab 30 Individuen, mindestens jedoch ab 10 Individuen gehalten werden.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Die Gruppengrösse im Aquarium sollte mindestens 10 Individuen betragen.
  - https://www.seriouslyfish.com/species/paracheirodon-innesi/
    > Try to buy a mixed-sex group of at least 8-10 specimens, include other schooling fishes to provide security, and you'll be rewarded with a more natural-looking spectacle.
  - https://www.practicalfishkeeping.co.uk/fishkeeping-news/study-shows-that-schooling-fish-do-best-in-larger-numbers/
    > After statistically analysing their data, the authors found that Neon tetras and White cloud mountain minnows displayed the lowest levels of aggression and darting in the larger group sizes. Groups of 10 had the greatest tendency to shoal
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Gesellig: Fische, die auch von anderen Fischen begleitet werden sollen um ihr arttypisches Verhalten zu zeigen. Neben anderen Fischen sind mindesten fünf Tiere dieser Art zusammen zu halten.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-tetras-and-pencilfish/
    > Tetras and pencilfish are shoaling fish and should be kept in groups of at least five in the home aquarium, but more is better.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Eine Gruppe von 15 Tieren der sehr kleinen Arten braucht ein Aquarium mit mindestens 54 Liter, was einer Grösse von 60L × 30B × 30H cm entspricht.
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > 1. Schwarm: Fische die sich in einer größeren Gemeinschaft von Artgenossen in ihrem Lebensraum bewegen. Daraus ergibt sich eine Mindestzahl von 10 Tieren dieser Art.
  - https://www.practicalfishkeeping.co.uk/fishkeeping-news/study-shows-that-schooling-fish-do-best-in-larger-numbers/
    > For Neon tetras and White Cloud Mountain minnows, group sizes of one, two, five and 10 fish per tank (equating to 0.1, 0.2, 0.5 and 1.0 fish per litre) were used.

### [small_fish] min_recommended_count (무리형: 코리도라스·할리퀸·구피, 신규)

- 조사 제안값: 6 (5 미만이면 강한 경고) (근거)
- 출처 대조 검증: 일부 수정 — 고친 값: 코리도라스 6 (BLV), 할리퀸 5 (오스트리아·OATA), 구피는 수컷 1 + 암컷 여럿 또는 암수 섞인 무리(BLV; 오스트리아 Gesellig 5). 5 미만이면 강한 경고
- 내용: small_fish의 무리형 종에는 5마리 미만이면 강하게 경고한다. 6마리는 BLV가 코리도라스에 준 값이다(마블 코리는 6~7마리). 할리퀸 라스보라는 오스트리아('Gesellig')와 OATA 모두 5마리 이상이다. 구피는 BLV가 '수컷 1 + 암컷 여럿' 또는 암수가 섞인 큰 무리를 권하므로, 마릿수와 함께 성비를 안내해야 한다.
- 한계: 이 값은 무리형에만 맞는다. small_fish에는 사회성이 서로 다른 종이 섞여 있다(베타 수컷은 단독, 아피스토는 쌍·하렘, 허니 구라미는 쌍). 그래서 크기 구분과 별도로 사회성 프로필 필드가 필요하다. BLV는 구피 같은 난태생어 10마리에 100L를 권한다.
- 출처:
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Sie sollten in Gruppen von mindestens 6 Individuen gehalten werden.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-freshwater-catfish/
    > Some species, such as Corydoras, are shoaling fish and should be kept in groups of at least five.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische.html
    > Gesellig: Fische, die Artgenossen benötigen, um ihr arttypisches Verhalten zeigen zu können. Im allgemeinen sollen mindestens fünf Fische dieser Art gepflegt werden.
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-rasboras/
    > Rasboras are shoaling fish and should be kept in groups of at least five in the home aquarium, but more is better.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Diese kann aus einem Männchen und mehreren Weibchen oder, in grösseren Gruppen, aus mehreren Individuen beider Geschlechter bestehen.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische-tabelle.html
    > Rasbora heteromorpha (Keilfleckbarbe) | X | _ | 24 - 30 | X | _ | _ | _ | Gesellig | 60

### [small_fish] max_recommended_count (단독형: 베타 수컷)

- 조사 제안값: 1 (근거)
- 출처 대조 검증: 확인
- 내용: 베타 수컷은 한 수조에 1마리만 둔다. 수컷 둘을 합사하면 죽을 때까지 싸운다는 데 OATA·영국 아나반토이드협회(AAGB)·Seriously Fish가 일치한다. 독일·오스트리아 표는 베타를 'Harem'(수컷 1 + 암컷 여럿)으로 분류한다.
- 한계: 암컷 무리(OATA 4마리 이상, 60L)와 하렘 사육은 따로 다뤄야 한다. 아피스토(쌍·하렘)와 드워프 구라미(쌍)의 마릿수 규칙은 이번에 수치로 정하지 않았다.
- 출처:
  - https://ornamentalfish.org/what-we-do/advice-information/care-sheets/caresheets-tropical-freshwater-fish/how-to-look-after-siamese-fighting-fish-bettas/
    > Males are highly aggressive and two should not be mixed or they will fight until one is severely injured, or more likely, killed. Females are much calmer and can be kept in groups of at least 4, but more is better.
  - https://www.practicalfishkeeping.co.uk/fishkeeping-news/guidelines-released-for-keeping-fighters/
    > Never keep two or more adult male Bettas together as they will fight, often to the death.
  - https://www.seriouslyfish.com/species/betta-splendens/
    > Usual practice is also to maintain males and females separately unless breeding.
  - https://www.bmleh.de/DE/themen/tiere/tierschutz/haltung-zierfische-tabelle.html
    > Betta splendens (Schleierkampffisch) | X | _ | 24 - 30 | _ | X | _ | Artspezi- fische Aggressi- vität3) | Harem | 60 |
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > 3. Harem: Ein Männchen darf nur mit mehreren Weibchen gehalten werden.
  - https://res.cloudinary.com/adminch/image/private/s--EUIgCgea--/v1720527470/Bundespublikationen/341-419-d.pdf
    > Daher werden sie in der Regel alleine in sehr kleinen Aquarien gehalten, was aber nicht artgerecht ist.

### [nano_fish, small_fish] hideout_min_count (은신처 개수, 신규, 경고만)

- 조사 제안값: 숨을 곳 수 ≥ 그것을 쓰는 개체 수 + 1. 시클리드(아피스토)는 밀린 개체와 짝 몫을 더 둔다 (근거)
- 출처 대조 검증: 확인
- 내용: 독일 동물보호연맹은 숨을 곳과 쉴 곳을 그것이 필요한 물고기 수보다 많이 두라고 한다. 오스트리아 법은 시클리드에게 밀린 개체와 짝을 위한 은신처가 있는 잘 나뉜 수조를 요구한다. 스위스 법도 수조 일부에 시선 차단과 피난처를 둘 것을 요구한다. '보다 많이'를 '+1'로 옮긴 직접 유도값이다.
- 한계: '은신처가 필요한 물고기 수'는 종마다 다르다. 테트라처럼 동굴을 쓰지 않는 무리 어종은 수초 등으로 대신한다. NestForge는 출력물 수만 알 수 있으므로 경고로만 쓴다. 구조물이 지키는 자원이 되어 다툼을 부를 수도 있다(Sloman 2011).
- 출처:
  - https://www.tierschutzbund.de/fileadmin/Seiten/tierschutzbund.de/Downloads/Broschueren/Broschuere_Aquarienfische_Haltung.pdf
    > Versteck- und Rückzugsmöglichkeiten müssen unbedingt in ausreichender Anzahl vorhanden sein (mehr als die Anzahl der Fische, die sie benötigen).
  - https://www.vetmeduni.ac.at/fileadmin/v/vetrecht/2._Tierhaltungsverordnung.pdf
    > Ihnen ist ein gut gegliedertes Becken mit Versteckmöglichkeiten für unterlegene Fische und auch für den Partner einzurichten.
  - https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2008/416/20260201/de/html/fedlex-data-admin-ch-eli-cc-2008-416-20260201-de-html.html
    > Ein Aquarium darf nicht allseitig direkt einsehbar sein. Es ist den Bedürfnissen der Tiere entsprechend einzurichten. Zumindest müssen in Teilen des Aquariums Sichtschutz und Rückzugsmöglichkeiten für die Fische vorhanden sein.
  - https://research-portal.uws.ac.uk/en/publications/the-effects-of-mixed-species-assemblage-on-the-behaviour-and-welf/
    > Interestingly, the present study highlighted the problems in predicting the effects of environmental enrichment with both species and group size altering the way enrichment was used (e.g. as shelter from competitors or as a resource worth aggressively defending).

### [all (small_fish는 필수 안내, shrimp·nano_fish는 권장)] placement_on_base_glass (배치 안내, 신규)

- 조사 제안값: 바닥재를 깔기 전에 바닥 유리에 바로 놓는다. 출력물끼리 결합 장치 없이 쌓거나 출력물 위에 돌을 얹지 않는다 (근거)
- 출처 대조 검증: 확인
- 내용: 판매사와 리프 수조 안내는 큰 돌·동굴을 바닥재를 깔기 전에 바닥 유리에 놓으라고 한다. 바닥재 위에 놓으면 땅 파는 물고기가 밑을 파서 무너뜨릴 수 있고, 무너진 구조물 밑에 물고기가 갇힐 수 있다. 3D 출력물은 물속 무게가 마른 무게의 약 20%라 같은 크기의 돌보다 훨씬 쉽게 밀린다. 코리도라스·아피스토처럼 바닥을 파는 종이 있는 small_fish에서는 필수로 안내한다.
- 한계: 무거운 돌에 대한 안내를 가벼운 출력물에 옮긴 것이고 실험 자료가 아니다. 붕괴로 물고기가 죽었다는 체계적 자료는 없다. 바닥 유리에 놓으면 바닥에서 시작하는 아치 입구가 바닥재에 묻히므로 입구 아래턱을 올려야 한다(설계 메모).
- 출처:
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-secure-aquarium-ornaments-safely-and-effectively
    > Where possible, position larger rocks on the tank base before adding substrate. This prevents digging fish from undermining the structure.
  - https://www.zoo-roco.ch/en/faq/Stone-structures-what-needs-to-be-considered
    > With stone structures, especially with burrowing fish, the stones should be glued to the glass and to each other. The stones must also not be placed on top of the gravel, but should be placed before the substrate is added. Otherwise, there is a risk that the fish will dig in the gravel and the whole…
  - https://reefbuilders.com/2015/07/20/avoid-these-5-live-rock-aquascaping-pitfalls
    > If placed directly on top of a deeper substrate, the rockwork can be easily undermined by burrowing/digging/tail-fanning fish or inverts, potentially resulting in a catastrophic rockslide.
  - https://www.ratemyfishtank.com/blog/stacking-rocks-in-your-aquarium
    > Species like Convict Cichlids, Bristlenose Plecos, Geophagus species, and various freshwater gobies will relentlessly excavate substrate from underneath your structures, causing unsupported rock piles to shift, collapse, and potentially crash against the glass walls or bottom panel.
  - https://www.zoo-roco.ch/en/faq/Stone-structures-what-needs-to-be-considered
    > The stones must also not be placed on top of the gravel, but should be placed before the substrate is added. Otherwise, there is a risk that the fish will dig in the gravel and the whole structure will collapse.

### [small_fish] base_flange_width_mm (바닥재로 덮는 바닥 테두리, 선택, 신규)

- 조사 제안값: 10 (임시)
- 출처 대조 검증: 확인
- 내용: small_fish용 구조물에는 바닥재로 덮는 10mm 바닥 테두리를 선택으로 둔다. 60×60mm 바닥 둘레에 10mm 테두리를 두고 모래 20mm를 덮으면 약 55gf가 누른다. 출력물의 물속 무게(수~수십 gf)와 비슷한 크기의 힘이다. 바닥재만으로 무거운 구조물을 받치지 말라는 안내는 있지만, 테두리 폭에는 출처가 없다.
- 한계: 물속 모래를 약 1g/cm³(비중 2.65, 공극률 0.4)로 가정한 계산이다. 파는 물고기가 테두리 위 모래를 치울 수 있다.
- 출처:
  - https://charterhouse-aquatics.com/blogs/help-guides/how-to-secure-aquarium-ornaments-safely-and-effectively
    > Substrate can shift over time and should not be the sole support for heavy structures.
