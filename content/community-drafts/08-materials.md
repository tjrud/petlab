<!-- 상태: 검수 반영본 (출처 원문 대조 4갈래 검수 후 수정) -->
# [가이드] 3D 프린팅 소재와 출력 안전

■ 한눈에 보기
햄스터가 3D 출력물을 갉거나 삼켰을 때의 영향을 직접 잰 연구는 찾지 못했어요. 그래서 "완전히 안전하다"고 확인된 소재는 없어요. 기관들이 주로 걱정하는 건 독성보다 갉아서 생긴 조각과 날카로운 모서리예요. 무착색 PLA·PETG를 권장 온도로 출력해 모서리를 다듬고, 씻어 말려 넣고, 자주 살피다 상하면 바로 바꾸는 게 지금의 최선이에요. 이걸로 얼마나 안전해지는지 잰 자료는 없어요.

■ 무엇이 위험한가
- 조각·모서리: TVT(독일 동물보호 수의사회)는 갉힌 플라스틱의 날카로운 조각을 삼킬 수 있다며 자연 소재를 우선 권하고, 독일 동물보호연맹도 플라스틱을 대체로 부적합하다고 봐요. 반면 VCA(미국 동물병원)는 플라스틱 은신처를 허용하고, RSPCA는 플라스틱 케이지가 금속보다 낫다고 해요. 플라스틱 같은 이물이 볼주머니 점막을 다치게 할 수도 있대요(아우름동물병원).
- 위생: 실험실 연구에서 세균막(세균이 뭉쳐 붙은 막)은 대부분 층 사이 홈에서 가장 두꺼웠어요(Hall 2021). 출력물은 씻을 때 물기도 머금어요(AWI). 소변이 스미는지 잰 연구는 없어요.
- 화학 성분·공기: 소재·안료·노즐에서 오고, 출력 중엔 초미세입자와 화학 증기가 나와요(NIOSH).

■ 소재 고르기
- 권장: 무착색(내추럴) PLA·PETG. 동물이 갉는 출력물을 직접 다룬 자료는 미국 동물복지단체 AWI가 연구비를 댄 보고서(Woodman 2021, 동료 심사 없음)가 거의 유일해요. 한 브랜드 흰색 PLA 출력물의 납·비소·바륨은 어린이 점토 장난감 기준보다 낮았고, 필라멘트 4종에서 프탈레이트(가소제)는 안 나왔어요. 식품 안전 인증 PETG 필라멘트에서도 BPA가 아주 조금(1 kg당 0.08 mg) 나왔어요. 연구자는 갉는 용품에 써도 괜찮다고 보면서 식품 접촉 인증·무착색 소재가 더 낫다고 했어요. 시료가 적고 동물에게 먹여 본 시험은 아니에요.
- PLA와 PETG: PLA는 깨질 때 파편이 생기기 쉽고 PETG가 더 질겨요(Prusa). 갉는 개체엔 PETG를 권하는 메이커도 있지만 갉기로 비교한 시험은 없어요.
- 색: 안료가 문제일 수 있어 무착색이 가장 낫대요(Prusa). 같은 브랜드라도 색마다 식품 접촉 적합 여부가 달라요.
- 피하기: ABS·ASA는 스타이렌 계열이라 동물용에서 빼래요(Prusa). 레진(SLA) 출력물은 물고기 배아를 담근 시험에서 독성이 나왔고(Oskui 2016, 2015년 무렵 레진), 동물이 갉았을 때의 자료가 없어요. 실크·반짝이·야광·금속·탄소섬유·우드처럼 첨가물이 든 필라멘트도 섭취 자료가 없어 피하는 게 좋아요.

■ 포장 문구 읽는 법
- "식품 등급": 필라멘트 원료 이야기예요. 출력물은 출력물 자체로 따져야 하고, FDA 식품 안전 '승인'을 받은 3D 프린팅 소재는 없대요(Polymaker). 'FDA 승인'으로 광고된 PLA가 시험 소재 중 녹아 나온 물질·미세입자가 가장 많았던 연구도 있어요(Rindelaub 2019). 광고 문구만으론 알 수 없어요.
- "생분해성": 약 58°C 산업용 퇴비 조건에서 분해된다는 뜻이지, 먹어도 된다는 뜻이 아니에요.
- "무독성": 국내에선 필라멘트용 공인 무독성 인증 제도를 찾지 못했어요.

■ 출력할 때
- 노즐: 황동 노즐로 뽑은 시험용 출력물은 강철 노즐보다 녹아 나온 납이 7~12배였어요. 그래도 1 g당 10억분의 1~1.5 g 수준으로 아주 적어요(Rindelaub 2019). 가능하면 스테인리스 노즐을 쓰세요.
- 온도: 노즐 온도를 권장 범위보다 올리지 마세요. 높은 온도로 출력하자 입자 방출이 81배로 늘었어요(NIOSH). 물이 덜 스미게 온도·압출량을 올리는 '수밀 출력'도 PLA에선 오히려 물을 약 3배 더 머금었어요(AWI).
- 채움: Prusa는 물이 고이지 않게 100% 채움(인필)을 권해요. 채움이 낮으면 갉았을 때 속의 빈 격자가 드러나요.
- 층·서포트: 적층(레이어) 높이가 너무 크면 층이 벗겨져 긴 가닥이 몸에 감기거나 조각을 삼킬 수 있어요(AWI). NestForge 파일은 서포트 없이 출력할 수 있는 자세로 놓여 있어요. 슬라이서가 서포트를 넣었다면 뗀 자리가 날카로울 수 있으니 꼭 다듬으세요.
- 공기: 출력 중엔 케이지를 다른 방에 두고 환기하세요. 갓 뽑은 부품도 환기되는 곳에 두었다가 넣어 주세요(얼마나 둘지는 자료가 없어요). 핫엔드 안 테프론(PTFE) 튜브는 약 250°C를 넘으면 작은 동물, 특히 새에게 해로운 가스를 낼 수 있대요(TH3D). PLA(약 190~220°C)는 이보다 낮지만 PETG(240~270°C, Bambu Lab)는 걸쳐요.
- 접착·코팅: NestForge 구조물은 한 덩어리라 붙일 필요가 없어요. 깨지면 접착제로 붙이지 말고 새로 출력하세요. TVT는 동물이 닿는 핫글루를 위험 요소로 꼽아요. 에폭시 코팅·용제 처리는 갉는 조건에서 시험한 자료가 없어요.

■ 씻고 말리기
- PLA는 약 55~60°C, PETG는 약 65~70°C에서 물러져요(Bambu Lab). 끓는 물·식기세척기는 피하고, 볕 드는 창가·히터 옆에도 두지 마세요. 휘었으면 바꾸세요.
- 미지근한 물과 세제로 씻고, 소독은 락스(차아염소산나트륨)를 제품에 적힌 비율대로 묽혀 쓰세요. 다른 세제·식초와 섞지 말고, 냄새가 안 날 때까지 헹군 뒤 완전히 말려 넣어 주세요. PLA 시험에서 0.85% 락스에 15분 담그면 1시간 묻혀 둔 세균과 소독에 강한 바이러스까지 없어졌지만, 오래 자란 세균막은 시험하지 않았고 락스 성분이 층 틈에 남았어요(Vaňková 2020).

■ 점검·교체
- 갉는 정도는 개체마다 달라요. 넣은 뒤 며칠은 매일, 그 뒤엔 청소할 때마다 살펴보세요(점검 주기를 정한 자료는 없어요).
- 깊은 이빨 자국, 금, 떨어진 조각, 날카로운 모서리, 벌어진 층, 드러난 속, 빠지지 않는 오줌 얼룩이 보이면 바로 바꾸세요(Fable's 참고). 조각이 없어졌는데 평소와 다르면 설치류 진료 병원에 가세요.
- 계속 갉아 부수는 개체라면 약품 처리 안 한 나무·코르크나 도자기 용품으로 바꾸세요.

■ 부품별로
- 은신처·터널: 입구는 골든 7 cm, 드워프 5 cm 이상이 기준이에요(TVT). NestForge는 이 기준을 써요.
- 모래 목욕통: TVT는 모래 목욕통·밥그릇을 플라스틱 말고 도자기로 하래요(이유는 밝히지 않아요). 도자기는 넘어지거나 밑을 파서 무너지지 않게 놓고, 모래는 고운 친칠라 샌드를 쓰세요(TVT). 출력한 통은 갉힌 자국·오줌 얼룩이 보이면 바로 바꾸세요.

■ 아직 모르는 것
- 플라스틱 조각 때문에 햄스터 장이 막힌 증례 보고는 찾지 못했어요. 다만 소화 안 되는 이물은 장을 막을 수 있대요(VCA).
- 갉기에 견디는 벽 두께 기준이 없어요. NestForge의 최소 벽 두께(골든 3 mm, 드워프 2.4 mm)도 근거 수치 없이 정한 임시값이에요.

■ 출처
- AWI(Woodman 2021): https://awionline.org/sites/default/files/uploads/documents/3d-printing-animal-welfare.pdf
- Rindelaub 2019: https://pmc.ncbi.nlm.nih.gov/articles/PMC6530847/
- TVT(골든·드워프): 「공통 안전 수칙」 글 출처 참고
- 독일 동물보호연맹: https://www.tierschutzbund.de/fileadmin/Seiten/tierschutzbund.de/Downloads/Berichte/Positionspapier_DTSchB_Tierschutzwidriges_Zubehoer.pdf
- RSPCA: https://www.rspca.org.uk/adviceandwelfare/pets/rodents/hamsters/environment
- VCA: https://vcahospitals.com/know-your-pet/rodents-housing
- 아우름동물병원: https://blog.naver.com/aurumah/224163876817
- Prusa: https://blog.prusa3d.com/3d-printing-for-pets-and-animals_46054/ · https://help.prusa3d.com/article/pla_2062 · https://help.prusa3d.com/article/food-safe-prints_112313
- Polymaker: https://wiki.polymaker.com/polymaker-wiki/polymaker-wiki-ko/undefined/fun-3d-printing-facts/no-material-is-fda-approved-as-food-safe
- Bambu Lab: https://cdn.shopify.com/s/files/1/0380/5149/files/Bambu_PLA_Basic_Technical_Data_Sheet.pdf · https://cdn.shopify.com/s/files/1/0380/5149/files/Bambu_PETG_Basic_Technical_Data_Sheet.pdf
- NIOSH: https://doi.org/10.1021/acs.chas.1c00041
- Oskui 2016: https://doi.org/10.1021/acs.estlett.5b00249
- Hall 2021: https://doi.org/10.3389/fmicb.2021.646303
- Vaňková 2020: https://pmc.ncbi.nlm.nih.gov/articles/PMC7603793/
- TH3D: https://tickets.th3dstudio.com/products/article/ptfe-safety-precautions-%E2%80%93-all-ptfe-toughtube
- Fable's: https://www.fableshamsters.co.uk/post/pla-and-3d-printed-products-for-hamsters

※ 일반적인 참고 정보예요. 개체마다 다르고, 건강 문제는 설치류를 보는 수의사와 상담해 주세요.
