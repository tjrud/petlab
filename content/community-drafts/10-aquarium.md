<!-- 상태: 게시 완료 (조사 6갈래 + 출처 대조 검증 3갈래 + 4관점 검수 + 재검수 반영). 커뮤니티 글 id: 4f64bf7ac33d43e89d5d034a93ca2760. 근거자료: 10-aquarium-evidence.md -->
# [가이드] 어항에 3D 출력물, 수질 면에서 써도 될까요

■ 한눈에 보기
어항 수질에 안전하다고 증명된 3D 출력 소재는 없지만, 연구 결과는 소재마다 갈려요. 레진(광경화) 출력물은 넣지 마세요. 물을 덜 먹고 덜 상하는 무착색 PETG가 가장 낫고, 담수라면 무착색 PLA도 조건부로 쓸 수 있어요. FDM 출력물 때문에 생물이 죽었다고 확인된 사례도(포럼 글 일부는 원문을 못 열었어요), 오래 넣어 두고 무해함을 측정한 사례도 찾지 못했어요. "안전하다"가 아니라 "이 조건이면 위험이 낮아 보인다"는 정도예요.

■ 연구로 알게 된 것
- 레진: 레진 출력물을 우린 물에서 물벼룩은 72시간 안에 모두 죽었고, 물고기 배아의 24시간 생존율은 0~10%였어요(Zhu 2015). UV 후경화로 독성이 크게 줄었지만 다 없어지진 않았고(Oskui 2016), 에탄올로 씻어도 배아가 모두 죽은 레진이 있었어요(Macdonald 2016).
- PLA·ABS: 우린 물에서 물고기 배아는 72시간, 윤충·물벼룩류는 24시간 시험에서 괜찮았어요(Zhu 2015). 투명 PLA 그릇에 배아를 직접 넣어도 7일 생존율이 대조군과 같았어요(Pérez-Davila 2022). 하지만 같은 우린 물이 민물 미세조류 성장을 50% 가까이 억제했고(Zhu 2015), 산업용 ABS 출력물에 배아가 직접 닿자 심장 부종이 늘었어요(Oskui 2016).
- 해수: PETG와 비슷한 코폴리에스터, PLA/PHA, 스테인리스 가루 PLA로 출력해 해수에 1주 길들인 타일에서 산호 유생이 정착해 12주 동안 소재 간 차이 없이 자랐지만 다른 연구의 석회암 타일보다 절반 넘게 느렸고, 크로미스 행동도 그대로였어요(Ruhl·Dixson 2019). 수질은 재지 않았고 산호는 출력물끼리만 비교했어요.
- 한계: 대부분 물에 비해 출력물이 아주 많은 진한 조건의 며칠~12주 시험이에요. PETG 자체, 관상 새우, 1년 넘는 어항 시험은 없어요. 사람 세포 시험에선 PETG 1종이 세포 대사를 크게 떨어뜨렸어요(Dejmek 2026).

■ 물속에서 소재는
- PLA는 25°C 물에서 1년 동안 거의 분해되지 않았어요(Bagheri 2017). "몇 달이면 녹는다"는 근거가 약하고, 쉽게 없어지지도 않아요. 약점은 온도라, 30°C 증류수 6개월에 연신율이 42%, 40°C에선 강도가 85% 줄었어요(Deroine 2014). 양식용 순환여과 장치에선 일부러 넣은 PLA를 세균이 먹이로 썼어요(Zhao 2024).
- 출력한 PETG는 8~9주 담가도 무게가 약 0.3% 늘었고 PLA는 2.5% 늘었어요(Moreno Nieto 2021). 나일론·우드 PLA는 물을 많이 먹고 크게 약해졌어요(Banjo 2022, Islam 2026).
- PLA 미세입자는 실험에서 물고기 장을 다치게 하고 물벼룩 생존을 떨어뜨렸어요. 하얗게 뜨거나 부서진 출력물을 바꿔야 하는 이유예요.
- "해수의 알칼리성이 PLA를 빨리 녹인다"는 근거가 약해요. 40°C 시험에선 해수 쪽이 오히려 느렸어요(Deroine 2014). 칼크바서 같은 강알칼리 용액에 닿는 부품엔 PLA를 피하는 게 안전해요.

■ 금속: 새우·산호는 특히
- 구리는 아주 적어도 문제예요. 미국 EPA의 해수 구리 만성 기준은 3.1 µg/L이고, 물달팽이 새끼는 1.8 µg/L에서 성장이 20% 줄었어요(Brix 2011).
- 필라멘트 속 금속량은 색·브랜드마다 달랐고, 투명 필라멘트도 압출 뒤엔 구리가 들어 있었어요(Beard 2026). 무착색은 정체 모를 안료·첨가제를 줄이는 예방책이지 구리가 없다는 보증은 아니에요.
- 황동 노즐 출력물을 50°C 물에 우리면 강철 노즐보다 납이 7~12배 나왔지만, 1 g당 1~1.5 ng으로 아주 적었고 구리는 검출되지 않았어요(Rindelaub 2019).

■ 실제로 쓰는 곳
- 해외 리프 용품 업체는 대체로 PETG로 출력해요. PLA도 괜찮다는 업체도 있어요. "reef-safe"는 시험 자료를 공개하지 않은 판매자 주장이에요.
- 담수 어항에 PLA 은신처를 1년쯤 넣었는데 처음처럼 튼튼하다는 경험담이 있어요(MakerBot 모임). 수질 측정은 없어요.

■ 조건: 이렇게 쓰면 위험을 낮출 수 있어요
- 소재: 무착색 PETG가 1순위예요. 담수이고 수온이 25°C 안팎이면 무착색 PLA도 돼요. 오래 둘 물건·여과기 속 부품은 PETG로 해요. 레진, 나일론, 우드·금속·카본·실크·반짝이·야광·형광 필라멘트는 빼고 ABS·ASA도 기본 추천에서 빼요.
- 노즐: 스테인리스나 티타늄이요. 새우·산호 수조라면 꼭 바꾸세요.
- 출력: 외벽 3~4줄 이상(Prusa), 채움 100%로 속을 꽉 채우거나, 물이 자유롭게 드나드는 열린 모양으로 해요. 작은 틈만 난 속 빈 공간은 안 돼요. 모래를 넣고 막았지만 틈이 남은 속 빈 시판 장식에서 썩는 냄새가 나고, 빼자 물고기가 나아진 사례가 있어요.
- 넣기 전: 세제가 층 사이 홈에 스몄다 나올 수 있어(Prusa), 햄스터 용품과 달리 세제·소독제 없이 물로만 씻어요. 생물 없는 물에 며칠 담갔다가 그 물은 버려요. 며칠이면 충분한지는 검증된 적이 없어요.
- 넣은 뒤: 하나씩 넣고 생물과 수질을 지켜봐요(리프는 넣기 전후 ICP 검사 비교). 히터에 닿지 않게 두고, 하얗게 뜨거나 갈라지거나 물러지면 바꿔요.
- 접착·코팅: 어항용이라고 적힌 제품만 써요. 욕실·건축용 실리콘엔 곰팡이 방지제가 들었을 수 있고, 굳을 때 식초 냄새가 난다고 어항용은 아니에요(sera). 산호 연구에선 순간접착제 젤로 산호를 붙여 키웠어요(Forsman 2015). 코팅한 출력물을 생물로 시험한 자료는 없어요.
- 레진 프린터를 쓴다면: 액상 레진·세척한 IPA는 어항 근처에 두거나 하수구에 버리지 마세요. 액상 레진은 종류에 따라 2.6~33 mg/L에서 이틀 안에 물벼룩류 절반이 죽었어요(Ballentine 2023).

■ 수조별로
- 새우·달팽이: 무착색 PETG와 스테인리스·티타늄 노즐만 쓰세요. 관상 새우 시험이 없어 예방 차원이에요.
- 해수·리프: 무착색 PETG만 쓰고 금속 필라멘트·황동 노즐은 피해요. 해수가 PLA를 더 상하게 한다는 근거는 약하지만 업체 관행을 따른 예방이에요.

■ 더 알아보기
기본 출력 수칙은 「3D 프린팅 소재와 출력 안전」 글에 있어요.

■ 출처
- Zhu 2015: https://pmc.ncbi.nlm.nih.gov/articles/PMC4691254/
- Oskui 2016: https://doi.org/10.1021/acs.estlett.5b00249
- Macdonald 2016: https://pmc.ncbi.nlm.nih.gov/articles/PMC4758231/
- Pérez-Davila 2022: https://pmc.ncbi.nlm.nih.gov/articles/PMC9572917/
- Ruhl·Dixson 2019: https://doi.org/10.1371/journal.pone.0221157
- Bagheri 2017: https://pmc.ncbi.nlm.nih.gov/articles/PMC6607129/
- Deroine 2014: https://archimer.ifremer.fr/doc/00173/28376/26689.pdf
- Zhao 2024: https://pubmed.ncbi.nlm.nih.gov/39245379/
- Moreno Nieto 2021: https://pmc.ncbi.nlm.nih.gov/articles/PMC8036839/
- Banjo 2022: https://doi.org/10.1016/j.jcomc.2022.100243
- Islam 2026: https://doi.org/10.36922/MSAM026190041
- PLA 미세입자: https://pubmed.ncbi.nlm.nih.gov/35114456/ · https://pubmed.ncbi.nlm.nih.gov/32871484/
- EPA: https://www.epa.gov/wqc/national-recommended-water-quality-criteria-aquatic-life-criteria-table
- Brix 2011: https://pubmed.ncbi.nlm.nih.gov/21723419/
- Beard 2026: https://pmc.ncbi.nlm.nih.gov/articles/PMC13488613/
- Dejmek 2026: https://pubmed.ncbi.nlm.nih.gov/42324277/
- Rindelaub 2019: https://pmc.ncbi.nlm.nih.gov/articles/PMC6530847/
- 업체: https://reefbuilders.com/2023/10/24/charterhouse-aquatics-provides-3d-printed-product-solutions · https://reefbuilders.com/2023/02/10/faqs-on-3d-printing/
- MakerBot 모임: https://groups.google.com/g/makerbot-users/c/sY9javWl7iA
- Prusa: https://help.prusa3d.com/article/watertight-prints_112324 · https://help.prusa3d.com/article/_112313
- 속 빈 장식: https://www.monsterfishkeepers.com/forums/threads/be-carefull-sealing-up-aquarium-decorations.181229/
- sera: https://www.sera.de/en/service/faq/faq-detail/gluing-rocks-and-decoration-with-silicone
- Forsman 2015: https://pmc.ncbi.nlm.nih.gov/articles/PMC4614846/
- Ballentine 2023: https://pubmed.ncbi.nlm.nih.gov/36792856/

※ 일반적인 참고 정보예요. 이상이 보이면 출력물을 빼고 물을 갈아 주세요. 아픈 생물은 수생동물 수의사와 상담해 주세요.
