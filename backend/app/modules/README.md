# 부품 라이브러리와 자유 조립

라이브러리는 **부품**이다. 미리 짠 조립 세트는 없다. 요청마다 해석기(LLM·모의 해석기)가 "어느 부품을 어느 부품의
어느 면에 붙이는지"만 적고, 조립 해석기가 연결 표준으로 결합 방식·통로·맞물리는 치수를 정한다.

- 부품은 두 가지다. 어느 쪽이든 같은 `Template` 이고, 조립 해석기·엔진·검증은 둘을 가리지 않는다.
  - **코드 부품** `app/templates/*.py`: 형상을 파이썬으로 직접 만드는 템플릿. 부품마다 `anchors()` 로 연결 지점을 내고,
    연결 표준(`role`·`attach_order`·`face_fields` 등, 아래)을 정한다.
    - 기준 구조물: 은신처(`hideout`, 방), 집(`house`, 방), 모래목욕통(`sand_bath`)
    - 통로: 터널(`tunnel`)
    - 끼우는 부품: 그릇 받침(`bowl_holder`), 물병 거치대(`bottle_stand`), 램프/계단(`ramp`)
    - 물속 동굴(`cave`)은 어항 전용이라 연결 지점이 없다 (`role = "none"`)
  - **라이브러리 부품** `app/library/parts/<family>@v<N>.json`: Part DSL v1 로 적은 데이터 부품. key 에 버전이 붙고
    (`tunnel_junction@v1`), 게시한 파일은 바꾸지 않는다. `app/library/template.py` 의 `DslTemplate` 이 파일 하나를
    `Template` 하나로 만들고, 레지스트리는 코드 부품 다음에 key 순서로 싣는다. 만드는 법은 아래 "라이브러리 부품".
    - 터널 갈림길(`tunnel_junction@v1`, room_host): 터널 여러 개가 만나는 작은 방
    - 발판 플랫폼(`deck_platform@v2`, host; v1 은 폐기): 양옆 벽 위에 발판을 얹은 플랫폼. 옆면에 램프·받침을 끼운다
    - 화장실 트레이(`litter_tray@v1`, accessory): 게시했지만 아직 어느 종에도 허용하지 않았다 (아래 "2단계 현황")
- 종마다 만들 수 있는 부품은 `rules/species.yaml` 의 `templates:` 가 정한다. 조립 항목은 부품마다 이 목록으로 확인한다.
  해석기에는 이 목록에서 폐기·차단한 라이브러리 부품을 뺀 것(`RuleBook.offered_templates`)만 내놓는다. 저장된 설계를
  다시 만들고 검증할 때는 전체 목록(`allowed_templates`)을 쓴다.
- 조립 코드
  - `structure.py`: 해석기 출력(`AssemblyRequest`)과 저장 형태(`ResolvedAssembly`)의 모델, 나무 꼴 검사, 정규 JSON
  - `compose.py`: 조립 해석기 (`resolve`, `derived_constraints`, `composed_template`)
  - `composed.py`: 조립 항목 템플릿 `ComposedTemplate` (key `"assembly"`). 엔진은 이것을 보통 템플릿처럼 쓴다
  - `module_template.py`: 조립 템플릿의 기반 `AssemblyTemplate` (형상·출력 파트·출력 자세·형상 검사)
  - `assembly.py`: 연결 지점끼리 놓기, 통로 뚫기, 슬라이드·끼움 결합 형상, 조립 규칙, 끼임 틈(`slot_gaps`)

예전의 고정 세트 8개(식당 은신처, 쌍둥이 은신처 등)는 제품에서 빠졌다. 같은 구조를 해석기 출력 꼴로 옮긴 것이
`tests/data/compositions/*.json` 에 시험 자료로만 남아 있다 (메뉴나 프리셋이 아니다).

## 연결 표준

### 연결 지점 (`Anchor`)

좌표는 부품 `build()` 좌표계 (바닥 Z=0). 부품을 이으면 자식의 연결 지점이 부모의 연결 지점에 **마주 보게**
(법선이 반대, 위쪽이 같게) 붙는다.

- 바닥에 서는 부품의 옆면 연결 지점은 **그 면의 아래쪽 가운데(Z=0)** 에 둔다. 그래야 이어 붙인 부품의 바닥이 맞는다.
- `normal` 은 면 바깥 방향, `up` 은 면 위의 위쪽. 둘 다 단위 벡터이고 서로 수직.
- 위에 얹는 자리는 `top` (normal +Z, up +Y), 밑면은 `bottom` (normal −Z, up +Y). 1단계에서는 위에 얹지 않는다.
- 연결 지점의 종류는 값으로 정해진다.
  - **출입구**: `port`(통로 폭 mm) + `wall_mm`(벽 두께). 터널만 이을 수 있고, 아무것도 잇지 않은 출입구는 바깥 출입구로 센다.
  - **터널 끝**: `port` 만 (벽 없음). 방(은신처·집)을 잇는다.
  - **벽뿐인 면**: `wall_mm` 만. 터널을 이으려면 `open_port` 로 출입구를 낸다 (은신처 뒷면 → 출입구 2개, 은신처 옆면 →
    옆면 출입구, 집 옆면 → 연결부).
  - **연결판 자리**: `mount = (left, right, height)`. 슬라이드 결합으로 받침·거치대·램프를 끼운다. 면 좌표 (t, u) 는
    t = up × normal (바깥에서 볼 때 오른쪽), u = up, 원점 = origin.
  - `side`: 그 면이 `features().access_sides` 의 출입 면이면 그 이름. 이어 붙이면 출입 면에서 빠진다.
  - `profile`: 출입구·터널 끝의 통로 단면 종류 (`round_arch | pointed_arch | tube | box | house`, `port_profile` 이 만드는
    단면과 같은 종류). 통로로 이을 때 터널 단면을 이 종류로 맞춘다.
- 통로 부품은 `port_cutter()` 로 통로 단면 기둥을 내고, 조립할 때 벽 쪽 부품의 벽을 그 모양으로 뚫는다
  (`app/templates/base.cutter_at`). `port_profile()` 은 그 2D 단면이다 (끼움 결합이 넓혀 쓴다).
- 연결판 자리 (부품별): 은신처는 출입구 없는 옆면 전체. 집은 출입구·연결부·착지판 없는 벽, 높이는 1층 평 지붕이면 외형 높이
  전체, 지붕 뚜껑을 씌우면 처마 − SKIRT_MM, 2층 집은 2층 바닥 높이까지, 창이 있는 면은 창 아래 끝 − MARGIN_MM 까지.
  모래목욕통은 뒤·왼쪽·오른쪽 면 전체(높이 = 안쪽 깊이 + 바닥 두께), 앞면은 가로 전체 × 턱 높이. 앞면 연결판은 늘 경사로
  끝나고 경사 끝이 턱 높이에서 벽에 닿으므로 출입 홈(턱 위로 파인 곳)을 덮지 않는다. 터널 갈림길은 출입구가 아닌 옆면
  전체(벽 두께는 있지만 `wall_mm` 이 없어 출입구를 낼 수 없다). 발판 플랫폼은 왼쪽·오른쪽 옆벽 전체(높이 = 발판 윗면),
  앞·뒤는 트인 통로라 연결 지점이 없다.

### 템플릿의 연결 표준 (`app/templates/base.py`, 기본값은 "잇지 않는다")

| 항목 | 뜻 |
|---|---|
| `role` | `host`(옆면에 받침을 다는 기준 구조물) · `room_host`(드나드는 방) · `connector`(통로) · `accessory`(옆면에 끼우는 부품) · `none` |
| `attach_order` | 자식으로 붙을 때 쓸 연결 지점 후보: `slide`(옆면에 끼우기), `passage`(통로로 잇기) |
| `passes_access` | 부모의 출입 면에 붙어도 출입을 막지 않는다 (램프) |
| `level_field` | 부모 면 높이에 맞추는 높이 파라미터 (램프 `height_mm`) |
| `face_fields(p, anchor)` | 연결 지점 치수를 정하는 파라미터 경로 `FaceFields(width, height, wall, port, profile)` (점 표기) |
| `open_port(p, anchor)` | 벽뿐인 면에 출입구를 낸 파라미터 (낼 수 없으면 None) |
| `envelope(p)` | 사용 자세 외형 크기 (해석적으로 덮어쓰면 해석기가 형상 없이 면 크기를 정한다) |
| `face_needs(p)` | 이 부품을 붙일 부모 면 높이의 (최소, 최대) |
| `joined_constraints(p, ctx, anchor)` | 연결 지점으로 붙었을 때만 더하는 제약 |
| `assembly_constraints(p, ctx)` | 조립 항목의 부품일 때만 더하는 제약 (혼자 쓸 때는 그대로) |
| `door_fields` | 어느 출입구가 있는지·단면 모양을 정하는 필드. 통로로 이으면 해석기가 `fixed` 에 고정한다 (`getattr` 로 읽는 선택 속성: 라이브러리 부품만 둔다. 코드 부품은 `compose.DOOR_STRUCTURE_FIELDS` 의 `entrance_count`·`side_doors`·`doors.sides`·`ports.sides`) |

| 부품 | 역할 | 연결 지점 | `attach_order` | 통로 크기 / 단면 | `open_port` |
|---|---|---|---|---|---|
| 은신처 | room_host | `front` 출입구, `back` 출입구(출입구 2개일 때) 또는 벽·연결판, `left`/`right` 옆면 출입구(`side_doors`) 또는 벽·연결판 | passage: front, back, left, right | `entrance_diameter_mm` / round_arch | back → `entrance_count` = 2, left/right → `side_doors` 에 더하기 (none → 그 면, 다른 쪽 하나 → both) |
| 집 | room_host | 네 면: 출입구(`doors.sides`) · 연결부(`ports.sides`, 플랜지) · 벽·연결판 | passage: front, back, left, right | `doors.width_mm`·`ports.diameter_mm` / pointed_arch | 옆면 → `ports.sides` 에 더하기 (현관 면 제외) |
| 모래목욕통 | host | `front` 턱 높이 연결판(출입 면), `back`/`left`/`right` 연결판 | — | — | 없음 |
| 터널 | connector | `end_a`, `end_b` 터널 끝 | passage: end_b, end_a | `inner_diameter_mm` / `shape` | — |
| 그릇 받침 | accessory | `back`(슬라이드), `bottom` | slide: back | — | — |
| 물병 거치대 | accessory | `back`(슬라이드), `bottom` | slide: back | — | — |
| 램프/계단 | accessory, `passes_access` | `landing`(슬라이드), `entry`(출입 면), `left`/`right`, `bottom` | slide: landing | — | — |
| 터널 갈림길 `tunnel_junction@v1` | room_host | `layout` 이 정한 출입구 (I 앞·뒤, L 앞·왼쪽, T 앞·왼쪽·오른쪽, X 네 면), 나머지 면은 연결판 | passage: front, back, left, right | `door_width_mm` / `door_shape` (이은 터널을 따른다) | 없음 (닫힌 면에 통로를 청하면 빈 출입구로 옮긴다) |
| 발판 플랫폼 `deck_platform@v2` | host | `left`/`right` 연결판 (옆벽 전체 높이), `top`, `bottom` | — | — | 없음 |
| 화장실 트레이 `litter_tray@v1` | accessory | `back`(슬라이드), `bottom` | slide: back | — | — |

부품별로 더하는 것:

- 그릇 받침: 붙일 면 높이 ≥ 그릇 높이 + 15 (`face_needs`), 벽에 붙이면 턱 ≥ 그릇 높이 − 5 (`joined_constraints`: 사서 쓰는
  그릇은 형상에 없어 그릇과 벽 사이 홈을 엔진이 재지 못하니 5mm 깊이로 줄인다)
- 물병 거치대: 붙일 면 높이 ≤ 컵 입구 높이 (`face_needs`: 면이 더 높으면 연결판 위로 물병과 벽 사이에 틈이 남는다)
- 램프: 조립 부품이면 경사 ≥ 0.2461 × 높이 + 5 (`assembly_constraints`: 따로 출력하는 램프가 프린터에 들어가게)
- 은신처 옆면 출입구 (`side_doors`: none · left · right · both, 기본 none): 왼쪽(−X)·오른쪽(+X) 벽 가운데에 앞 출입구와
  같은 아치를 낸다. 뒤집어 출력하면 위가 트인 홈이라 오버행이 없다. 옆면 출입구가 있으면
  - 세로 ≥ 출입구 폭 + 벽 두께 × 4 (옆 출입구 양옆에 벽이 남게), 없으면 지금처럼 + 벽 두께 × 2
  - 출입구 수 = `entrance_count` + 옆면 출입구 수. 여러 마리 최소 출입구 규칙은 옆면 출입구를 뺀 만큼만 `entrance_count` 에 건다
  - 출입 면에 옆면이 들어가고, 문구는 "앞 출입구"·"왼쪽 출입구"·"오른쪽 출입구"
  - `legacy_defaults = {"entrance_count": 1, "side_doors": "none"}`. none 은 저장 형태(`model_dump`)에서 빠진다: 옆면
    출입구가 생기기 전의 파라미터 dict 와 같아야 그 dict 로 정하는 값(장식 무늬 씨앗)이 저장된 설계와 같게 남는다
- 터널 갈림길: 출입구 폭 ≥ 종별 최소 출입구 폭, 가로·세로 ≥ 출입구 폭 + 벽 × 2 + 8, 높이 ≥ 출입구 높이 + 벽 × 2.
  출입구는 모두 `door_width_mm` 하나라 이은 터널 내경이 갈림길을 거쳐 한 값으로 이어진다. 쓰지 않은 출입구는 바깥
  출입구로 센다. 뒤집어 출력한다
- 발판 플랫폼: 발판 높이 ≤ 종별 최대 오르기 높이, 발판 아래 높이·폭 ≥ 종별 통과 폭(끼이지 않게), 세로 ≥ 높이 × 0.5
  (넘어지지 않게). 램프는 옆면 높이(= 발판 윗면)까지 올라간다 (`compose._levels`). 발판이 아래로 가게 뒤집어 출력한다

### 결합 표

해석기의 `at` 을 기준 부품 좌표계에서 부모 연결 지점으로 옮긴 뒤, 위에서부터 처음 맞는 줄을 쓴다
(`compose.py`, 자식 연결 지점은 `attach_order` 순서).

| # | 부모 연결 지점 | 자식 | 결과 |
|---|---|---|---|
| 1 | 위·아래 | 아무것 | 고를 수 없다 (`at` 에 위·아래가 없다. 위에 얹기는 2단계) |
| 2 | 출입구 | 터널 | **끼움**, 통로가 부모 벽을 뚫는다(`into_parent`). 터널 내경은 출입구 폭을 따르고, 터널 단면은 출입구 단면으로 |
| 3 | 터널 끝 (`free_end`·`auto`) | 방 | **끼움**, 통로가 자식 벽을 뚫는다(`into_child`). 방의 출입구 크기는 터널을 거슬러 주인 값을 따른다. 출입구 단면을 고르는 방(갈림길)은 터널 단면을 따른다 (아래 "단면 맞추기") |
| 4 | 출입구 | 방 | 사이에 터널을 넣는다 (`{방}_link`, 가장 짧은 길이, 안내 `tunnel_inserted`) → 2·3 |
| 5 | 터널 끝 | 터널 | `join_unsupported` (터널끼리는 잇지 않는다: 사이에 터널 갈림길을 넣는다) |
| 6 | 벽뿐인 면 | 터널(·방) | `open_port` 로 출입구를 내고(`port_opened`) 2 로 (은신처 왼쪽·오른쪽 → 옆면 출입구). 못 내면 빈 출입구 면으로 옮기고(`join_relocated`), 그것도 없으면 `face_unavailable` |
| 7 | 연결판 자리 (출입구 아님) | 받침·거치대·램프 | **슬라이드**, 통로 아님 |
| 8 | 출입구, 또는 출입 면인데 자식이 출입을 막는 부품 | 받침·거치대 | 오른쪽·왼쪽·뒤·앞 중 첫 빈 연결판 면으로 옮긴다 (`join_relocated`), 없으면 `face_unavailable` |
| 9 | 그 밖 (모래목욕통·집을 자식으로, 받침을 부모로) | — | `join_unsupported` |

- `auto`: 받침류는 오른쪽·왼쪽·뒤·앞, 통로는 앞·뒤·터널 끝 순서로 첫 빈 면.
- **한 덩어리(fused) 결합은 해석기가 고르지 않는다.** 은신처는 뒤집어, 받침류는 바로 세워 출력하고, 통로로 붙인 덩어리는
  출력 공간을 넘기 쉬워서 따로 출력하는 것이 늘 낫다. 엔진(`assembly.py`)은 fused 결합도 다룰 수 있다 (`tests/test_modules.py`).
- 형상 검사(슬라이드·남은 틈·겹침·연결판 틈)가 마지막 관문이다.
- 라이브러리 부품도 역할로 같은 줄을 쓴다 (새 줄이 없다). 발판 플랫폼(host)은 기준 부품으로만 쓴다. 갈림길(room_host)은
  은신처처럼 출입구에 터널을 꽂고, 닫힌 면에 받침을 끼운다.
- 4 에서 넣는 터널은 key `tunnel` 로 찾는다 (`_State.catalog`). 레지스트리에 다른 통로 부품이 먼저 있어도 바뀌지 않는다.

#### 단면 맞추기 (`_adopt_room_profile`, `_match_profile`)

- 출입구 단면이 고정된 방(은신처 둥근 아치, 집 뾰족 아치)은 터널이 방을 따른다 (`passage_shape_matched`).
- 출입구 단면을 필드로 고르는 방(`face_fields(..).profile` 이 있는 출입구, 갈림길의 `door_shape`)은 방이 터널을 따른다
  (`passage_shape_matched`, 방에 안내). 그 필드를 `fixed` 에 적어 다음 통로부터는 `_match_profile` 이 이 단면으로 맞춘다.
  터널 단면이 방이 만들 수 없는 모양(`tube`)이고 아직 고정되지 않았으면 방은 그대로 두고 터널이 방을 따른다. 고정된
  터널 단면을 방이 만들 수 없으면 `join_unsupported`.
- 그래서 갈림길 하나로 이은 망은 첫 방의 단면을 끝까지 쓴다. 집(뾰족 아치)과 은신처(둥근 아치)를 한 갈림길에 이으면
  "양 끝의 출입구 단면 모양이 달라" 로 실패한다 (단면 바꿈 부품 `port_adapter` 는 2c).
- 해석기 출력 검사(`spec._profile_problems`)는 단면을 고르는 방을 건너뛴다: 섞인 망은 조립 해석기가 위 메시지로 막는다.

### 결합 방식 (`mount`)

슬라이드 결합 (`assembly.py` 의 `slide_plan`·`plate_solid`·`slot_cutters`·`tongue_solid`):

- 부모 면에 두께 `PLATE_MM`(4mm) 연결판을 붙인다: 가로 = 자식 외곽 폭, 높이 = min(자식 높이, 붙일 수 있는 높이).
  자식은 연결판 바깥에 놓인다 (연결판에 OVERLAP_MM 묻힘). 연결판 끝이 부모 꼭대기가 아니면 윗면은 벽 쪽으로
  올라가는 50° 경사로 끝난다 (뒤집어 출력해도 오버행이 아니고, 자식 윗모서리와 벽 사이에 홈이 남지 않는다).
- 출력 파트에서만 연결판에 세로 도브테일 홈(위아래가 트임, 안쪽이 넓다)을, 자식 뒷면에 틈새 0.25mm 의 혀를 낸다.
  자식을 위에서 밀어 내리면 끼워지고 옆·바깥으로는 빠지지 않는다. 100mm 마다 하나 (최소 하나).
  혀는 자식 출력 파트 가운데 연결판에 가장 넓게 닿는 파트에 붙는다 (물병 거치대는 받침판이 아니라 물병 컵).
  출력 자세에서 아래를 보는 혀 끝은 경사로 깎는다.
- 한 면에 여럿 붙이면 붙인 순서대로 가운데 맞춘 한 줄로 놓고 사이를 띄운다 (`shift`, 저장 형태에 남는다).
  부모 면 가로는 자식 폭 합 + 사이 틈 + 양쪽 여유 `EDGE_MARGIN_MM`(3mm)까지 늘린다.
- 연결판보다 높은 자식은 연결판 위로 벽과 뒷면 사이에 `PLATE_MM − OVERLAP_MM`(3.7mm) 틈을 남긴다. 이 틈은 상수로 두지 않고
  잰다 (`assembly.plate_gaps`): 연결판 높이 위 자식 뒷면의 격자점마다 벽 쪽으로 광선을 쏘아 자식이 아닌 출력 파트에 닿는
  거리. 경사·둥근 지붕 집의 처마 쪽 면에 처마보다 높은 자식을 붙이면 위로 벌어지는 쐐기 틈이 잡혀 오류가 된다.
- 알려진 한계: 끼운 자리(설계 위치)에서만 잰다. 도브테일은 혀를 바깥으로 0.7mm 쯤 놀게 두므로 모래목욕통 앞 턱 높이 램프의
  발판과 벽 사이 3.7mm 홈은 당기면 4.4mm 쯤이 되어 드워프 안전 틈(4mm, 임시 값)을 넘는다 (골든 5mm 보다는 좁다).

끼움 결합 (`assembly.py` 의 `plug_profiles`·`spigot_solid`·`passage_cutter`·`plug_chamfer`·`plug_problems`):

- 통로 쪽 부품(터널) 끝에 끼움 턱(spigot)을 낸다: 안쪽 단면 = 통로 단면(`PLUG_EPS_MM` 0.05mm 만큼 넓게), 바깥 단면 = 통로
  단면을 `PLUG_SPIGOT_MM`(1.5mm) 넓힌 것, 바닥(y=0) 위만. 길이 = 벽 쪽 벽 두께 − `PLUG_TIP_GAP_MM`(0.3mm).
- 벽 쪽 부품의 벽은 통로 단면을 `PLUG_SPIGOT_MM + PLUG_CLEARANCE_MM`(1.7mm) 넓힌 구멍으로 뚫는다 (틈새 한쪽 0.2mm).
  터널 끝 면은 벽 면에 맞닿게 놓고 끼움 턱 바깥의 터널 벽 고리가 넓힌 구멍을 덮는다.
- 해석기는 벽 두께 하한을 제약으로 낸다: 터널 벽 ≥ 끼움 턱 + 틈새 + 고리 0.5mm (2.2mm), 벽 쪽 벽 ≥ `PLUG_MIN_LENGTH_MM` +
  `PLUG_TIP_GAP_MM` (2.3mm).
- 세워 출력하는 터널의 양 끝을 다 끼우면 한쪽 끼움 턱은 아래를 본다. 그 끝은 끼움 턱 뿌리에서 `SLOPE_RISE` 기울기로 벌어지는
  깔때기로 깎는다 (`plug_chamfer`, 출력 파트에만).
- 끼움 턱·깔때기·도브테일 혀는 설계 벽 두께보다 얇게 만든 모양이라 출력 파트가 그 솔리드를 `PrintPart.thin_ok` 로 함께 내고,
  메시 두께 측정은 그 표면 근처 샘플을 뺀다.
- 알려진 한계: 끼움 턱은 벽 두께 − 0.3mm 만 들어가고 걸림이 없어, 부품을 그만큼 밀어 벌리면 빠진다.

조립 형상(`build()`)은 끼운 자리 그대로 한 덩어리 (홈·혀·틈새·깔때기 없음). 출력 파트(`print_parts()`)는 fused 결합으로
이어진 부품 묶음마다 하나 (기준 묶음 "본체", 나머지는 부품 id, 부품이 따로 출력하는 파트는 `{부품id}_{key}`) — 슬라이드·끼움
결합은 늘 묶음을 나눈다. 같은 템플릿이 여럿이면 이름에 번호를 붙인다 ("은신처 2"). 홈·혀가 있는 묶음은 도브테일이 세로로
서는 사용·뒤집기 자세 중, 그 밖의 묶음은 여섯 방향 중 서포트가 가장 적은 자세로 출력한다.

형상 커널이 세 부품 이상을 한 번에 합칠 때 맞닿은 면 때문에, 또 휜 터널 끝의 안쪽 곡면이 곧은 통로 기둥과 맞닿을 때
닫히지 않은 형상을 내는 경우가 있어, `build_assembly` 는 통로 연결이 있으면 결과 메시가 닫혔는지 보고 아니면 통로 단면을
`PLUG_EPS_MM` 넓혀 뚫어 다시 합친다. 출력 파트 묶음도 같은 방식으로 만든다 (`module_template._group_body`).

## 조립 항목

### 해석기 출력 (`AssemblyRequest`, LLM·모의 해석기 공통, `app/llm/spec.parse_spec` 이 검증)

```json
{"template": "assembly", "name_ko": "급식 은신처와 터널로 이은 은신처",
 "parts": [
   {"id": "hide", "template": "hideout", "params": {"width_mm": 140, "...": "..."}},
   {"id": "bowl", "template": "bowl_holder", "params": {"...": "..."}},
   {"id": "tube", "template": "tunnel", "params": {"...": "..."}},
   {"id": "hide2", "template": "hideout", "params": {"...": "..."}}],
 "connections": [
   {"part": "bowl", "to": "hide", "at": "right"},
   {"part": "tube", "to": "hide", "at": "front"},
   {"part": "hide2", "to": "tube", "at": "free_end"}],
 "placement": {"zone": "auto", "group": null, "rotation": null, "attach_to": null},
 "reason_ko": "…"}
```

- 부품 2~8개 (`MAX_PARTS`), id 는 `^[a-z][a-z0-9_]{0,40}$` 이고 겹치지 않는다. 첫 부품이 기준(뿌리)이고, 나머지는
  `connections` 에 `part` 로 한 번씩 나온다 (나무 꼴, 순환 없음).
- `at`: `front | back | left | right` 는 **기준 부품 좌표계**(케이지에서 돌리기 전)의 면, `free_end` 는 터널의 남은 끝,
  `auto` 는 첫 빈 면.
- 해석기는 결합 방식·자식 연결 지점·위치 이동·맞물리는 치수를 적지 않는다 (적어도 엔진이 덮어쓴다).
- 부품 하나뿐인 구조물은 지금처럼 일반 항목이다 (조립 항목으로 감싸지 않는다).

### 저장 형태 (`ResolvedAssembly`, `DesignVersion.items[i]["assembly"]`)

```json
{"v": 1, "resolver": "compose/1", "root": "hide",
 "parts": [{"id": "hide", "template": "hideout"}, {"id": "bowl", "template": "bowl_holder"}, "…"],
 "joins": [{"parent": "hide.right", "child": "bowl.back", "mount": "slide", "passage": false, "shift": 0.0},
           {"parent": "hide.front", "child": "tube.end_b", "mount": "plug", "passage": "into_parent", "shift": 0.0},
           {"parent": "tube.end_a", "child": "hide2.front", "mount": "plug", "passage": "into_child", "shift": 0.0}],
 "ties": [{"follower": "tube.inner_diameter_mm", "owner": "hide.entrance_diameter_mm"}, "…"],
 "fixed": {"tube.shape": "round_arch", "hide.entrance_count": 2},
 "faces": {"bowl": "right", "tube": "front", "hide2": "free_end"}}
```

- 파라미터는 부품 id 마다 나눠 저장한다: `items[i]["params"] = {"hide": {...}, "bowl": {...}}`.
- 다시 만들 때는 `parts`·`joins`·저장된 파라미터만 쓴다 (`registry.template_for` → `compose.composed_template`).
  **해석기를 다시 돌리지 않는다.** `ties`·`fixed` 는 다시 검증·규칙 안내에만 쓴다.
- 형상 지문: 조립 항목은 `"assembly:" + sha256(parts + joins)` → 조립 코드(`ASSEMBLY_MODULES`)와 쓰는 부품 템플릿의 해시.
  라이브러리 부품의 해시는 부품 파일 sha256 + DSL 해석 코드(`fingerprint.DSL_MODULES`: `app/library/{template,ops,expr,schema}.py`,
  `app/templates/tunnel.py`)다. `compose.py` 는 넣지 않는다 (다시 만들 때 돌지 않는다). 그래서 **결합 형상을 바꾸는 `assembly.py`·`module_template.py`
  수정은 저장된 조립 항목의 지문을 바꾼다**: 파일별 `file_digest` 로 다시 만든 결과가 같은지 확인한다.
- 고친 명세(revision 이 보는 꼴)는 해석기 출력 꼴에 보정한 파라미터와 실제로 붙은 면(`faces`)을 적은 것이다.
  해석기가 넣은 터널도 보통 부품으로 나온다.

## 조립 해석기 (`compose.resolve`)

`resolve(req, params, ctx) → (ResolvedAssembly, 부품 파라미터, 안내) | Issue`. 형상은 만들지 않는다.

1. 부품마다 자기 제약으로 보정한다 (여러 마리일 때 출입구 2개처럼 종 규칙이 정하는 구조 값을 먼저 정한다).
2. 기준 부품에서 너비 우선, `connections` 순서로 결합 표를 적용한다 (`at` → 부모 연결 지점은 지금까지 놓은 부품의 회전으로).
   옮기기·출입구 내기·터널 넣기를 안내(info)로 남긴다.
3. 나갈 출입구: 통로로 출입구를 쓴 방에 빈 출입구가 없으면 반대쪽 벽에, 안 되면 `attach_order` 의 다른 빈 벽에 출입구를
   낸다 (`exit_added`, `fixed` 에 적는다). 은신처는 뒷면이 받침으로 차 있으면 받침을 옮기기 전에 옆면 출입구를 낸다.
   통로를 둘 이상 쓴 방(지나가는 방)은 막다른 방이 아니라 출입구를 더 내지 않는다 (1단계에서 저장한 은신처 사슬을 다시
   해석해도 가운데 은신처에 옆면 출입구가 생기지 않는다).
   통로로 출입구를 쓴 방은 출입구 구조 필드(`DOOR_STRUCTURE_FIELDS` + 부품의 `door_fields`)를 `fixed` 에 적는다.
4. 맞물리는 치수: 통로마다 터널 쪽 크기가 출입구 쪽 크기를 따르게 한다 (`ties`, 주인은 사슬을 끝까지 거슬러 따르지 않는
   첫 값). 터널 단면은 출입구 단면으로 정한다 (`passage_shape_matched`). 단면을 고르는 방(갈림길)이 아직 어느 터널에도
   맞추지 않았으면 (기준 부품이거나 위쪽일 때) 그 방에서 나온 터널 단면은 임시이고, 단면이 정해진 방(은신처·집)을 만나면
   갈림길과 그 터널들이 그 방 단면을 따른다. 잇는 순서와 상관없이 같은 결과다.
5. 한 면에 여럿 붙인 부품을 나란히 놓는다 (`shift`).
6. `ResolvedAssembly` 로 얼린다.

`derived_constraints(resolved, p, ctx)` 는 `ComposedTemplate.constraints()` 로 자동 보정 패스마다 다시 불린다
(`ASSEMBLY_MAX_PASSES` = 12):

- 부품마다 자기 제약 + `assembly_constraints` + 붙은 연결 지점의 `joined_constraints` (필드는 `부품id.경로`). 따르는 값에
  걸린 제약은 주인 값으로 옮긴다 (예: 골든 햄스터 터널 최소 내경 70mm → 은신처 출입구 지름 ≥ 70, 터널·두 번째 은신처가 따른다).
- 따르는 값 = 주인 값, 램프 높이 = 부모 면 연결판 높이 (램프만 움직인다), 해석기가 정한 값(`fixed`).
- 부모 면 가로: 붙인 부품이 들어가게 늘 키우기만 한다 (보정이 수렴한다).
- 부모 면 높이: 붙인 부품의 `face_needs` (그릇 받침은 최소, 물병 거치대는 최대).
- 끼움 결합 벽 두께 하한.

엔진(`services/engine._prepare_assembly`) 순서: 부품 파라미터 검증 → 부품마다 이 종에 허용되는지 → `resolve` → 해석기가 넣은
부품도 허용되는지 → `template_for` → `clamp_params(…, max_passes=12)` → `rule_issues` → (공간이 모자라면) 기준 구조물 크기를
줄여 다시 보정.

## 검증

조립 항목도 일반 구조물과 같은 검증을 받는다 (닫힌 메시, 벽 두께, 오버행, 출력 크기, 케이지 배치, 출입구·통로 크기,
끼임 틈). `ComposedTemplate.rule_issues` 가 더하는 것:

- 부품마다의 규칙, 조립 규칙: 출입구·터널 끝을 다른 부품으로 막으면 오류, 통로 방향이 맞지 않으면 오류
  (`join_problems`), 슬라이드 결합(`slide_problems`), 끼움 결합(`plug_problems`)
- 연결 지점 하나에 둘 이상 이으면 오류 (옆면에 슬라이드로 나란히 끼우는 것만 된다)
- 드나드는 방이 있는 조립은 바깥 출입구 수를 종별 최소 개수와 비교
- 잇지 않은 부품 사이 끼임 틈 (`assembly.slot_gaps`): 상자 사이 거리가 아니라 **서로 마주 보는 면** 사이를 잰다. 부품 겉면에서
  고르게 뽑은 점(`SLOT_SAMPLES`, 씨앗 고정)에서 바깥 법선 방향으로 광선을 쏘아, 처음 닿은 것이 상대 부품이고 거리가 끼임 위험
  구간 안이며 닿은 면이 광선을 마주 보면(내적 < `SLOT_FACING_DOT`) 센다. 양쪽에서 합쳐 `SLOT_MIN_HITS` 이상이면 틈이다.
  은신처 앞 열린 모서리를 사이에 둔 그릇 받침과 터널처럼 마주 보는 면이 없는 자리는 세지 않는다.
- 통로가 출입구를 다 덮는지 (`passage_leftover`): 벽 쪽 개구부 단면 기둥(끼움 결합이면 넓힌 구멍까지) − 통로 쪽 형상 − 통로
  단면 기둥이 1mm³ 보다 크고 가장 넓은 폭(`leftover_width`)이 0.5mm 보다 넓으면 오류 (예: 뾰족 아치 집 출입구에 둥근 아치 터널)
- 따로 출력하는 파트끼리 1mm³ 넘게 겹치면 오류 (예: 경사 지붕 집 벽에 처마 − SKIRT_MM 보다 높은 램프는 지붕 뚜껑과 겹친다)
- 슬라이드 결합: 연결판을 붙일 수 없는 면, 붙일 수 있는 영역보다 넓거나 벗어난 자식, 바닥에 서지 않은 자식, 도브테일을 낼 수
  없을 만큼 좁거나 낮은 뒷면, 연결판 위 끼임 틈
- 창은 끼임 위험 구간 크기면 오류

보정할 수 없는 값(부품 필드 범위 밖이어야 맞는 값)은 `param_conflict` 오류다. 안내(info)는 `details.part` 에 부품 id 를 단다:
`join_relocated`, `port_opened`, `tunnel_inserted`, `passage_shape_matched`, `exit_added`, `param_adjusted`.
경고 `exceeds_build_volume` 은 일반 구조물과 같다.

## 라이브러리 부품 (Part DSL v1)

작성 안내는 `app/library/README.md` (명령, 검사, 예시, 자주 걸리는 곳). 이 절은 조립 쪽에서 알아야 할 것만 적는다.

- **서버는 부품을 만들려고 AI 를 부르지 않는다.** 해석기가 카탈로그에 없다고 한 부품(`DesignSpec.missing_parts`)을
  `part_requests` 에 기록할 뿐이다 (관리자 화면 "부품 요청"). 부품은 개발 세션에서 개발자 에이전트가 CLI
  (`uv run python -m app.library new|check|preview|verify|publish`)로 쓰고 검증해 게시한다.
- 부품 파일은 데이터다: 파라미터(범위·기본값·종별 기본값 식), 제약, 상자·원기둥·각기둥·통로 단계, 출력 파트·자세, 연결 지점,
  특징. 식은 화이트리스트 식 언어(`app/library/expr.py`)이고, 형상 식은 파라미터만 읽어 같은 파라미터는 늘 같은 바이트다.
- `DslTemplate` 이 연결 표준을 이렇게 채운다:
  - 연결 지점의 `door {when, width, profile}` 이 켜지면 출입구(`port`·`profile`·`wall_mm`·`side`), 꺼지면 `mount` 만 있는
    연결판 자리. 출입구 구멍은 `tunnel.inner_profile` 로 그 부품 벽을 뚫는다 (터널 단면과 같은 모양).
  - `face_fields` 는 파일의 `fields`, `open_port` 는 `opens`, `door_fields`·`size_fields`·`height_field`·`level_field`·
    `attach_order` 는 같은 이름의 필드. `features` 의 출입구 수·출입 면·통로 크기는 켜진 출입구에서 나온다.
  - 장식(`decor_zones`)·`joined_constraints`·`assembly_constraints` 는 v1 에 없다.
- 게시한 파일(`parts/<family>@v<N>.json`)은 바꾸거나 지우지 않는다. 형상을 바꾸려면 새 버전(`@v2`)을 게시한다.
  `index.json` 이 sha256·상태(active·retired·blocked)·검증한 종과 크기·골든을 갖고, sha 가 맞지 않거나 스키마가 틀리면
  서버와 시험이 시작하지 않는다.
- 종에 허용: `rules/species.yaml` 의 `templates` 에 key 를 적는다. 규칙을 읽을 때 그 부품이 그 종의 모든 크기 구분에서
  검증됐는지, 쓰는 규칙 값이 모든 크기에 있는지 확인한다. 햄스터 구조화 출력 스키마는 29,000자 이하여야 한다 (R12).
- 폐기(retire)한 부품은 새 설계에 내놓지 않고, 차단(block)한 부품은 저장된 설계의 내려받기도 막는다. 둘 다 레지스트리와
  `allowed_templates` 에 남아 저장된 설계를 다시 만든다.
- 모의 해석기는 라이브러리 부품의 `keywords`·`part_id` 를 읽는다 ("갈림길로 은신처 세 개", "플랫폼 오른쪽에 램프").
  내려받기 파일 이름은 `part{n}_{key 의 @ 를 - 로}`.
- 검사: 게시 전 검증기(`app/library/verify/`)가 기본값·끝값·무작위 변형마다 닫힌 메시, 벽 두께, 서포트, 출력 공간, 끼임
  틈, 연결 지점, 시험 조립(역할별 `compose.resolve` → 보정 → `rule_issues`)을 본다. 같은 검사가 코드 부품의 계약 시험
  (`tests/test_part_contract.py`)이다. 게시 뒤에는 `tests/test_library_published.py` 가 파일·보고서·골든·게이팅·영어
  문구를 매번 다시 확인한다.

## 부품을 더하는 법

축에 맞춘 상자·원기둥·각기둥·통로를 더하고 빼서 만들 수 있고 서포트 없이 출력되는 부품은 **라이브러리 부품**으로 만든다
(아래 "라이브러리 부품"). 곡면, 휜 모양, 움직이는 부분, 부품마다 다른 형상 코드가 필요하면 코드 부품으로 만든다:

1. `app/templates/<부품>.py` 에 `Template` 을 만든다: `Params`(범위·기본값·한국어 설명), `build`, `features`, `constraints`,
   `print_parts`·`print_rotation`, `anchors`. 저장된 설계가 다시 만들어지므로 **공개한 부품의 형상은 바꾸지 않는다**: 새 필드는
   `legacy_defaults` 로 옛 값을 주고, 형상이 바뀌면 새 key(`_v2`)로 만든다.
2. 연결 표준을 채운다: `role`, `attach_order`, 연결 지점의 `port`·`wall_mm`·`mount`·`side`·`profile`, `face_fields`,
   필요하면 `open_port`·`face_needs`·`joined_constraints`·`assembly_constraints`·`passes_access`·`level_field`.
   `envelope` 를 해석적으로 덮어쓰면 해석기가 빨라진다 (경계 상자와 0.5mm 안으로 맞아야 한다).
3. 등록: `app/templates/registry.py`(기본 부품), `app/templates/keys.py` 의 `TEMPLATE_MODULES`(형상 지문),
   `rules/species.yaml` 의 종별 `templates:`.
4. 해석기: `app/llm/prompts.py` 의 카탈로그는 연결 표준에서 "연결" 안내를 만든다. 모의 해석기 낱말은 `app/llm/mock.py` 의
   `TEMPLATE_KEYWORDS`(영어 `TEMPLATE_KEYWORDS_EN`)와 부품 id(`PART_IDS`).
5. 영어: `uv run python -m app.i18n.extract` 가 빠진 한국어 문구를 알려 준다. `app/i18n/en/*.json` 에 더한다.
6. 시험: `tests/test_part_connectors.py`(연결 지점·`face_fields`·`envelope` 일관성), 결합 표의 새 줄은
   `tests/test_compose.py`, 형상·출력은 `tests/test_presets.py` 처럼 해석기 출력 꼴 고정 데이터로.

## 시험

- `tests/test_compose.py`: 결합 표 줄마다, 맞물리는 치수, 고정 데이터(옛 세트 8개 + 라이브러리 부품을 쓴 2개)가 적어 둔
  결합으로 풀리는지, 무작위 조립
- `tests/test_compose_stage2.py`: 은신처 옆면에 터널 → 옆면 출입구, 뒷면이 찼을 때 옆면 나갈 출입구, 터널을 key 로 찾기,
  `side_doors` 고정, 단면 맞추기, 해석기 출력 검사가 단면을 고르는 방을 건너뛰기
- `tests/test_hideout_side_doors.py`: 은신처 옆면 출입구 (형상, 연결 지점, `open_port`, 제약, 옛 파라미터가 같은 결과)
- `tests/test_library_parts.py`: 게시한 라이브러리 부품의 조립 동작, 그 부품을 쓴 설계의 저장 → 같은 바이트로 다시 만들기
- `tests/test_stage2_baseline.py`: 2단계 전 main 에서 잡아 둔 STL·저장 형태 골든 (2단계 작업이 바꾸면 안 된다)
- `tests/test_presets.py`: 고정 데이터로 안전 기준 (햄스터 크기마다 기본값·크기 끝값에서 닫힌 메시, 넓은 케이지에서 오류·경고
  없음, 출력 파트가 기준 프린터 220×220×250mm 안, 그릇 홈 5mm, 램프 발판 = 면 꼭대기, 모래목욕통 턱, 끼움 결합 출력 파트 셋,
  모의 해석기, 영어)
- `tests/test_modules.py`: 조립 엔진 기능 (부품과 결합을 그대로 적은 시험용 조립: fused 통로, 슬라이드, 끼움, 형상 검사)
- `tests/test_slot_gaps.py`, `tests/test_composed.py`, `tests/test_part_connectors.py`, `tests/test_mock_compose.py`

## 2단계 현황 (2026-11)

들어간 것:
- 은신처 옆면 출입구(`side_doors`, 같은 key, 기본 none 은 옛 형상과 같은 바이트)와 조립 해석기 지원 (터널을 key 로 찾기,
  출입구 구조 필드 고정, 단면 맞추기, 옆면 나갈 출입구)
- 부품 수요 기록(`part_requests`)과 관리자 화면, 사용자 안내 "요청을 기록해 두었어요"
- Part DSL v1, 검증기, CLI, 게시·폐기·차단, 영어 문구 파일, 형상 지문
- 게시한 부품: `tunnel_junction@v1`, `deck_platform@v2` (햄스터에 허용; v1 은 좁은 발판 아래 통로가 터널 최대 길이보다
  길어질 수 있어 폐기했다. 저장된 설계를 위해 허용 목록에는 남는다), `litter_tray@v1` (게시만 했다. 넣으면 햄스터
  구조화 출력 스키마가 29,722자로 29,000자 한도를 넘는다. 카탈로그 좁히기 뒤에 허용한다)

알려진 한계:
- 집(뾰족 아치)과 은신처(둥근 아치)를 한 갈림길에 이으면 "양 끝의 출입구 단면 모양이 달라" 로 실패한다 (이음 부품은
  2c). 한 종류의 방만 이으면 갈림길이 기준 부품이어도 그 방 단면을 따른다.
- 발판 플랫폼은 기준 부품으로만 쓴다. 앞·뒤(트인 면)에 청한 받침은 옆면으로 옮긴다 (`join_relocated`).

2c 로 미룬 것 (설계 문서 §2.2, §3.5): 단면 바꿈 부품 `port_adapter`, 위에 얹기(쌓기) 표준, 벽에 거는 물병 거치대, 집 현관
결합, 조립 장식·부품별 색, 카탈로그 좁히기(화장실 트레이를 허용하기 전에 필요), 형상 재시도 탐색.

형상 재시도 탐색을 만들지는 저장된 설계로 정한다. `backend/` 에서

    uv run python scripts/resolve_failures.py --db-url <운영 DB URL> [--since YYYY-MM-DD] [--latest-only] [--json]

이 조립 해석은 됐지만 형상 검사(슬라이드·남은 틈·겹침·끼임 틈)에 걸린 조립 설계의 비율을 종류·부품별로 센다. 5 %를 넘으면
재시도 탐색을 만든다. 같은 출력이 조립 해석 실패를 코드별로 세고, 단면 모양이 달라 실패한 비율이 2 % 이상이면
`port_adapter` 를 앞당긴다.
