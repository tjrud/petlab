# 부품 라이브러리 작성 안내 (Part DSL v1)

이 폴더는 코드로 만들지 않은 부품(DSL 부품)을 담는다. 부품 하나는 JSON 파일 하나다. 개발자 에이전트(개발 세션의
Claude Code)가 오프라인으로 초안을 쓰고, 검증기를 통과시킨 뒤 게시한다. 서버는 부품을 만들려고 AI 를 부르지 않는다.
서버가 하는 일은 사용자가 원했지만 없는 부품을 기록하는 것뿐이다 (관리자 화면 "부품 요청").

설계 문서의 §5–§9 가 규범이다. 이 문서는 작업 순서와 자주 걸리는 곳을 정리한다.

## 폴더

| 경로 | 내용 |
|---|---|
| `index.json` | 게시된 부품 목록. 라이브러리에서 유일하게 바뀌는 파일 (상태, sha256, 검증한 종·크기, 골든) |
| `parts/<family>@v<N>.json` | 게시된 부품 파일. 바꾸거나 지우지 않는다. 고칠 일이 있으면 새 버전을 게시한다 |
| `reports/<family>@v<N>.json` | 검증 실행 기록 (덧붙이기만 한다, 마지막이 최신) |
| `part.schema.json` | JSON Schema (`python -m app.library schema` 가 만든다; 손으로 고치지 않는다) |
| `backend/library_drafts/` | 초안 폴더. 내용은 저장소에 넣지 않는다 |
| `app/i18n/en/library.json` | 게시된 부품의 영어 문구 (publish·retire·block 이 다시 만든다) |

## 작업 순서

명령은 모두 `backend/` 에서 `uv run python -m app.library <명령>` 으로 돌린다.

1. **수요 고르기.** 관리자 화면 "부품 요청"에서 "JSON 내보내기"를 받거나, `demand <내보낸 파일>` 로 요약한다.
   사용자 수가 많은 요청부터 본다. 판단을 요청의 상태와 메모에 적는다:
   - DSL 로 만들 수 있다: 축에 맞춘 상자·원기둥·각기둥·통로를 더하고 빼서 만들 수 있고, 서포트 없이 출력된다.
   - 코드로 만들어야 한다: 곡면, 움직이는 부분, 휜 모양 (`app/templates/` 에 새 템플릿).
   - 만들지 않는다: 안전하지 않다, 천·전기 부품이다.
2. **규칙 읽기.** 부품이 쓰는 종별 규칙 값을 `rules/species.yaml` 에서, 출력 규칙을 `rules/printing.yaml` 에서 확인한다.
3. **초안 쓰기.** `new <family> --role host|room_host|accessory|none` 이 `library_drafts/<family>.json` 에 역할별
   뼈대를 쓴다. 뼈대는 바로 `check` 를 통과한다. 고친 뒤 `check <초안>` 이 깨끗해질 때까지 고친다 (1초 안에 끝난다).
4. **보고 고치기.** `preview <초안>` 이 `library_drafts/preview/<family>/sheet.png` 를 만든다. Read 도구로 그림을 열어
   모양, 연결 지점(화살표), 받침면(점선 사각형), 출력 자세를 확인한다. matplotlib 이 없으면
   `uv run --with matplotlib python -m app.library preview <초안>` 으로 돌린다.
   그다음 `verify <초안> --quick` (90초 안). 실패마다 검사 id, 변형, JSON 포인터, 값/한도, 고치는 방법이 나온다.
   `--stl-dir DIR` 은 실패한 변형의 메시를 쓴다.
5. **전체 검증과 게시.** `verify <초안>` (전체, 10분 안) 가 통과하면 `publish <초안> --requests <요청 id,…>`.
   publish 는 검사와 전체 검증을 다시 돌리고(캐시 없음), 부품 파일·보고서·색인·영어 문구 파일을 쓴다.
6. **종에 넣기.** publish 가 출력한 줄대로 `rules/species.yaml` 의 `templates` 에 key 를 더한다. 출력이 "아직 넣지
   말라"고 하면(LLM 스키마 29,000자 한도, R12) 넣지 않는다. 출력된 시험 명령을 돌리고 PR 을 연다. PR 에는 보고서 요약
   (검사 수, 가장 아슬아슬한 값, 시험 조립)을 적는다.
7. **배포 뒤.** 관리자 화면에서 그 요청을 `published` 로 바꾸고 key 를 고른다.

## 명령

| 명령 | 하는 일 |
|---|---|
| `schema` | `part.schema.json` 을 다시 쓴다 |
| `new <family> --role R` | 뼈대 초안 |
| `check <초안>` | 정적 검사 S01–S08, L02–L12 (`--json` 은 기계가 읽는 출력) |
| `preview <초안> [--params JSON] [--species hamster --size dwarf] [--out DIR]` | `use.stl`, `print_<key>.stl`, `sheet.png`, `info.json` |
| `verify <초안> [--quick] [--species S] [--jobs N] [--report OUT] [--stl-dir DIR]` | 검증 (§7). 통과해야 종료 코드 0 |
| `publish <초안> [--requests id,…]` | 게시 |
| `retire <key> --reason-ko … --reason-en … [--superseded-by family@vM]` | 새 설계에 내놓지 않는다 |
| `block <key> --reason-ko … --reason-en …` | 안전 문제: 새 설계에서 빼고 저장된 설계의 내려받기도 막는다 |
| `unretire <key> [--force-unblock]` | 다시 활성 |
| `reverify [<key> \| --all] [--apply]` | 지금 규칙·라이브러리로 다시 검증한다. `--apply`: 실패면 폐기, 통과면 규칙 지문을 고친다 |
| `regolden --library-upgrade` | build123d·OCP·trimesh·numpy 버전이 바뀌었을 때만 골든을 다시 만든다 |
| `audit` | CI 가 보는 것 모두 (`tests/test_library_published.py` 도 같은 검사) |
| `demand <export.json>` | 부품 요청 요약 |
| `list` | 게시된 부품 |

덮어쓰기·지우기 명령은 없다. git 작업도 하지 않는다.

모든 명령은 `--library DIR`(다른 라이브러리 폴더, 시험용)과 `--rules DIR`(다른 규칙 폴더)을 받는다. 저장소의
`rules/species.yaml` 은 게시된 부품 key(예: `tunnel_junction@v1`)를 종의 `templates` 에 적어 두므로, 그 부품이 없는
폴더를 `--library` 로 주면 규칙을 읽지 못해 `check` 부터 "알 수 없는 템플릿 키" 로 멈춘다. 그럴 때는 규칙 폴더를
복사해 `templates` 에서 그 폴더에 없는 key 를 빼고 `--rules` 로 함께 준다 (`tests/conftest.py` 의 `rules_copy` 와 같다).

## 부품 파일 요약

전체 규칙은 `part.schema.json` 과 설계 §5 에 있다.

- **좌표**: mm, 사용 자세. Z 위, 바닥 z=0, X 오른쪽, Y 뒤 (앞은 −Y). host 와 room_host 는 XY 가운데에 둔다.
- **식**: 문자열로 쓰는 작은 파이썬식 언어. 사칙연산, `%`, 비교, `and/or/not`, `a if c else b`, `x in ('A', 'B')`,
  함수 `min max abs floor ceil round sqrt clamp sin cos tan atan atan2 port_height`. 각도는 도(°).
  - 형상 자리(`let`, `body`, `anchors`, `opens`, `envelope`, `face_needs`, `features`)는 파라미터와 앞의 `let` 만 읽는다.
  - 규칙 자리(`constraints`, `checks`, `rule_default`)는 `rule.<종별 규칙 값>` 과 `ctx.<문맥 값>` 도 읽는다.
  - 형상은 파라미터만의 함수다. 그래서 같은 파라미터는 언제나 같은 바이트의 STL 이 된다.
- **파라미터**: `wall_thickness_mm` (숫자, 최솟값 ≥ 1.0, 최댓값 ≤ 8) 가 꼭 있다. 길이는 `_mm`, 각도는 `_deg`, 정수
  개수는 `_count` 로 끝난다. `rule_default` 는 종·크기마다의 기본값이다 (예: `"ctx.default_wall_mm"`).
- **단계(body)**: `box`, `cylinder`, `prism`, `passage` 를 차례로 더하거나(add) 뺀다(cut). `repeat {"i": n}`,
  `when` 으로 반복·조건. 둥근 모서리, 회전, 글자 같은 연산은 v1 에 없다 (필요하면 코드 부품).
- **출력(print)**: 첫 파트 key 는 `body`. 회전은 `upright`(바닥이 판), `inverted`(위가 판), `front_down`, `back_down`,
  `left_down`, `right_down`. 아래를 향하는 면이 45° 를 넘지 않는 자세를 고른다.
- **연결 지점(anchors)**: `origin`, `normal`, `up` (축 이름). 출입구는 `door {when, width, profile}` 와 `side`, `wall`.
  닫힌 면에 다른 부품을 끼우려면 `mount [왼쪽, 오른쪽, 높이]`. `fields` 는 그 면의 크기를 정하는 파라미터 이름.
  출입구 모양은 `round_arch`, `pointed_arch`, `box`, `house` 만 된다 (`tube` 는 출입구가 될 수 없다).
- **역할**: `host`(받침면만, 조립의 뿌리), `room_host`(출입구가 있는 방), `accessory`(다른 부품 옆면에 끼우는 부품,
  `attach_order.slide` 필수), `none`(따로 놓는 부품).
- **door_fields** (room_host): 어느 출입구가 있는지·모양을 바꾸는 파라미터를 모두 적는다 (조립이 고정한다).
- **size_fields**: 케이지에 맞춰 줄이는 필드. 출입구 폭이나 출입구 높이로 아래가 막힌 높이는 넣지 않는다.

## 검사

모든 검사가 합격 조건이다 (DSL 부품은 면제가 없다).

| 묶음 | 내용 |
|---|---|
| S01–S08 | 스키마, 식 컴파일, 참조, 역할·출입구 규칙, 이름, 문구, 한도, 벽 두께 |
| L02–L12 | 정적 검사 (상자 계산): 형상 자리의 rule./ctx., 합치기 겹침(0.2mm 이상), 자르는 면이 바깥 면과 겹치지 않기(0.5mm 이상 더 나가기), 남지 않는 단계, envelope, 연결 지점 종류, 규칙 이름, 이름·단위, key, 출력 파트, 사육 환경 |
| P1–P4 | 기본값이 보정 없이 맞는지, 보정이 수렴하는지, rule_issues, 식 계산 오류 |
| G01–G13 | 만들기, 닫힌 한 덩어리, 부피, 출력 공간, 서포트 없음, 벽 두께(설계·실측·선언), envelope, 틈 끼임(바닥면 포함), 특징 정직성(오르기 높이·경사·통로·환기구), 엔진, 넘어짐 각도 15° 이상, 같은 바이트(새 프로세스 포함), 뚫린 구멍(선언한 것만, 끼임 구간 없음) |
| C01–C08 | 연결 지점 좌표, 표면 위, 받침면이 평평하게 받쳐짐, 출입구 안이 트임, 출입구 단면, 면 필드, opens, attach_order |
| T01–T02 | 시험 조립 (역할별) 과 시간 |
| R01–R04 | LLM 계약(부품 하나 ≤ 2,300자, 종 전체 ≤ 29,000자), 문구 충돌, 규칙 값 범위, 성능 |

자주 걸리는 곳:
- **R02 문구 충돌**: 같은 한국어에 이미 다른 영어가 있다. 기존 카탈로그(`app/i18n/en/labels.json` 등)의 영어를 그대로 쓴다.
  파라미터 설명의 첫 문장(단위 뺀 것)은 메시지 가운데 들어가는 이름이라 소문자로 쓴다:
  `"벽·지붕 두께 mm"` → `"wall/roof thickness mm"`, `"출입구 폭 mm. …"` → `"entrance width mm. …"`,
  `"외형 가로(X) mm"` → `"outer width (X) mm"`, `"둥근 아치"` → `"round arch"`, `"네모"` → `"square"`.
- **L03/L04**: 더하는 상자는 앞 상자와 세 축 모두 겹치게, 자르는 상자는 바깥 면보다 0.5mm 이상 더 나가게 (예: 바닥이
  트인 방은 `"at": [0, 0, -1]`, 높이 `H - t + 1`).
- **G05**: 지붕이 있는 방은 `inverted` 로 출력한다. 출입구 아치는 출력 자세에서 위가 트인 홈이 된다.
- **G08**: 두 면 사이가 `safe_max_mm` 보다 넓고 `passable_min_mm` 보다 좁으면 끼임이다 (바닥과 판 사이도 센다).
- **G09**: 올라설 수 있는 면이 턱 높이보다 높으면 `features.climb_height` 를 적는다.
- **G13**: 뚫은 구멍은 모두 `features.openings` 에 환기구·창으로 적는다 (메시의 구멍 수를 센다; 크기는 자른 단계에서
  구한다). 옆·위에서 들여다보이는 구멍(바닥과 부품 사이 틈 포함)이 끼임 구간 크기면 적었어도 실패한다.
- **S07**: 반복을 펼친 고체 수는 필드 범위 전체에서 512 개 이하 (만들 때도 넘으면 DSL006).
- **P1**: 기본값과 `rule_default` 는 모든 크기 구분에서 제약을 지켜야 한다.
- **S03 door_fields**: 출입구 `when`·`profile` 식이 읽는 파라미터(let 을 거친 것 포함)는 모두 `door_fields` 에.

## 예시 (설계 §6)

초안은 `tests/data/library/` 에 있다.

- **`tunnel_junction` (room_host)**: 터널 여러 개가 만나는 작은 방. `layout` 선택(I·L·T·X)으로 출입구가 생기고,
  닫힌 면은 받침면이 된다. `door_shape` 는 이은 터널에 맞춰진다 (`door_fields: ["layout", "door_shape"]`).
  높이 아래 한도가 `port_height(door_shape, door_width_mm)` 이므로 `size_fields` 에는 `size_mm` 만 넣는다.
  출력은 `inverted`.
- **`deck_platform` (host)**: 양옆 벽 위에 판을 얹은 플랫폼. 받침면은 옆벽 전체 높이라 램프·그릇 받침이 붙는다.
  판 아래 통로는 `features.openings` 의 passage 로 선언하고 검증기가 탐침으로 확인한다. `climb_height` 를 적는다.
  넘어지지 않도록 `depth_mm ≥ 0.5 · height_mm`.
- **`litter_tray` (accessory)**: 낮은 턱의 트레이. 뒷면 `back` 이 슬라이드 연결 지점이다 (뒷면 아래 가운데).
  자르는 상자는 테두리보다 `t` 만큼 더 위로 나간다.

망가뜨린 초안 22개가 `tests/data/library_bad/` 에 있다. 파일마다 걸려야 하는 검사(`_expect`)가 적혀 있어, 각 검사가
무엇을 잡는지 볼 수 있다.

## 폐기와 차단

| | retire | block |
|---|---|---|
| 새 설계에 내놓기 | 안 함 | 안 함 |
| 저장된 설계 다시 만들기·검증 | 됨 | 됨 |
| 저장된 설계 내려받기 | 됨 | 막음 |

부품 파일과 레지스트리 등록은 그대로 둔다. 규칙(`rules/species.yaml`)을 바꿔 부품이 쓰는 값이 달라지면
`tests/test_library_published.py::test_reports_match_current_rules` 가 실패한다. 같은 PR 에서 `reverify --all --apply` 를 돌린다.
