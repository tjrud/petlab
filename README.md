# 꼬물공방 (petlab)

소형 반려동물(MVP: 햄스터) 맞춤 케이지 구조물 설계 웹서비스.

사육 환경과 요구사항을 입력하면 AI가 구조물(은신처·터널·램프·모래목욕통)을 맞춤 설계합니다.
설계 결과는 3D 뷰어로 확인하고 3D 프린팅 파일(STL, 3MF)로 내려받을 수 있습니다.

## 설계 원칙

- **LLM은 형상을 만들지 않습니다.** 요구사항 해석, 템플릿 선택, 파라미터 값 결정, 설명 생성만 맡습니다.
- 형상은 검증된 **파라메트릭 템플릿 코드**(build123d)가 생성합니다.
- 배치 좌표도 결정적 배치기(placer)가 계산합니다.
- LLM 출력은 JSON 스키마(pydantic)로 강제합니다. 스키마를 위반하면 재시도하고, 그래도 실패하면 사용자에게 오류를 안내합니다.
- 종별 치수 기준은 `backend/rules/species.yaml`, 출력 기준은 `backend/rules/printing.yaml`에 있습니다. 코드에 하드코딩하지 않습니다.

## 폴더 구조

```
backend/        FastAPI + build123d + trimesh (Python 3.11–3.13, uv)
backend/rules/  종별·출력 규칙 YAML (임시 기본값, 전문가 검수 대상)
frontend/       Next.js + react-three-fiber + Tailwind
vercel.json     Vercel 배포 구성 (Services: 프론트엔드 + 백엔드 컨테이너)
```

## 실행 방법

### 사전 준비
- Python 3.11–3.13, [uv](https://docs.astral.sh/uv/)
- Node.js 20 이상, npm

### 1) 환경변수

```bash
cp .env.example .env                              # 백엔드
cp frontend/.env.example frontend/.env.local      # 프론트엔드
```

| 변수 | 위치 | 설명 | 기본값 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` | Anthropic API 키. 환경변수로만 받으며 코드·저장소에 넣지 않습니다. | (없음) |
| `ANTHROPIC_MODEL` | `.env` | 사용할 Claude 모델 ID. `LLM_PROVIDER`가 anthropic이면 필수입니다. | (없음) |
| `LLM_PROVIDER` | `.env` | `auto`: 키가 있으면 anthropic, 없으면 mock / `anthropic` / `mock` | `auto` |
| `LLM_MAX_RETRIES` | `.env` | 스키마 위반 시 재시도 횟수 | `2` |
| `LLM_TIMEOUT_S` | `.env` | LLM 호출 타임아웃(초) | `60` |
| `DATABASE_URL` | `.env` | SQLite 경로 | `backend/data/kkomul.db` |
| `MESH_CACHE_DIR` | `.env` | 생성된 메시 캐시 경로 | `backend/data/meshes` |
| `RULES_DIR` | `.env` | 규칙 YAML 디렉터리 | `backend/rules/` |
| `API_PREFIX` | `.env` | 백엔드 라우트 접두사 (Vercel 배포 시 `/api`) | (없음) |
| `CORS_ORIGINS` | `.env` | 허용할 프론트엔드 출처(쉼표 구분) | `http://localhost:3000` |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/.env.local` | 백엔드 주소 | `http://localhost:8000` |

> `mock` 해석기는 API 키 없이 개발·테스트하기 위한 **키워드 기반 모의 해석기**입니다.
> 실제 서비스에서는 `ANTHROPIC_API_KEY`와 `ANTHROPIC_MODEL`을 설정하세요.

### 2) 백엔드

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

동작 확인: `curl http://localhost:8000/health`

### 3) 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:3000 을 엽니다.

### 테스트

```bash
cd backend && uv run pytest              # 백엔드 단위·API 테스트 (실제 LLM 호출 없음)
cd backend && uv run pytest -m live      # 실제 Anthropic API 호출 테스트 (키 필요)
cd frontend && npm run build             # 프론트엔드 타입 검사 + 빌드
cd frontend && npm run lint
```

E2E 스모크 테스트(Playwright)는 모의 해석기 모드의 백엔드와 프론트엔드 프로덕션 빌드를 자동으로 띄워 전체 흐름을 확인합니다.
흐름은 사육 환경 등록 → 요구사항 → 3D 뷰어 → 다운로드 → 제작 신청입니다.

```bash
cd frontend
npx playwright install chromium   # 최초 1회
npm run test:e2e
```

## 구조물 템플릿

LLM은 아래 템플릿 중에서 고르고 파라미터 값만 정합니다. 각 템플릿은 `backend/app/templates/` 아래 한 모듈에 다음을 모아 둡니다.
- 파라미터 스키마와 허용 범위
- 종 규칙 기반 동적 제약
- 형상 생성 함수, 출력 자세
- 검증용 특징

단위 테스트는 `backend/tests/test_template_*.py`에 있습니다.

| 템플릿 | 파라미터 | 서포트 없는 출력 전략 |
|---|---|---|
| 은신처 `hideout` | 가로·세로·높이, 출입구 폭, 환기구 개수·지름, 벽 두께 | 바닥이 열린 상자를 뒤집어 출력합니다. 아치 출입구는 바닥에서 시작하고, 환기구는 지붕에 수직으로 뚫습니다. |
| 터널 `tunnel` | 길이, 내경, 휨 각도(0=직선), 벽 두께 | 바닥이 열린 아치 단면입니다. 꼭대기는 40° 티어드롭으로 처리하고, 곡률은 수평면에서 줍니다. |
| 램프/계단 `ramp` | 높이, 폭, 경사각, 단 수(0=경사로) | 속이 찬 단면을 압출하고 꼭대기에 발판을 둡니다. 경사로에는 미끄럼 방지 턱과 4mm 앞끝 두께를 둡니다. |
| 모래목욕통 `sand_bath` | 가로·세로, 안쪽 깊이, 턱 높이, 벽 두께 | 위가 열린 상자입니다. 앞면 출입 홈은 위에서 파냅니다. |

새 템플릿을 추가하는 순서는 다음과 같습니다.
1. `Template`을 구현합니다(`templates/base.py` 참고).
2. `templates/registry.py`에 등록합니다. LLM 스키마·프롬프트 카탈로그·검증에는 자동으로 반영됩니다.
3. 프론트엔드 `src/lib/templates.ts`에 색상과 파라미터 이름을 추가합니다.

## API

백엔드 실행 후 http://localhost:8000/docs 에서 전체 스키마를 볼 수 있습니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/habitats` | 사육 환경 등록 (종, 크기, 마릿수, 케이지 내부 치수 mm) |
| GET | `/habitats/{id}` | 사육 환경 조회 |
| POST | `/designs` | 프롬프트로 설계 생성 → 버전 1 |
| POST | `/designs/{id}/revise` | 추가 프롬프트로 수정 → 새 버전 (이전 버전 유지, `base_version` 지정 가능) |
| GET | `/designs/{id}?version=` | 설계 조회 (버전 목록, 항목·배치, 검증 보고서) |
| GET | `/designs/{id}/export?format=stl\|3mf&version=` | 3D 프린팅 파일. STL은 파트가 여럿이면 zip입니다. 검증 오류가 있으면 409를 반환합니다. |
| GET | `/designs/{id}/versions/{v}/parts/{i}.stl` | 뷰어용 메시 (케이지 좌표계, mm, Z-up) |
| GET | `/species` | 등록 가능한 종·크기 (규칙 파일 기준) |
| POST | `/waitlist` | 제작·배송 신청 대기 등록 (이메일) |
| GET | `/health` | 상태, LLM 공급자, 규칙 파일 버전·검수 여부 |

오류 응답은 `{"detail": {"code": ..., "message_ko": ...}}` 형식이며, `message_ko`는 사용자에게 그대로 보여줄 수 있습니다.

### 설계 파이프라인

1. **LLM 해석**: 구조화 출력(JSON Schema)으로 템플릿, 파라미터, 배치 힌트, 설명을 받습니다.
   - pydantic으로 다시 엄격하게 검증합니다.
   - 위반하면 오류를 알려 최대 `LLM_MAX_RETRIES`회 재시도하고, 그래도 실패하면 사용자에게 안내합니다.
2. **파라미터 자동 보정**: 종 규칙과 템플릿 상호 제약에 맞게 값을 클램프합니다. 보정 내역은 `param_adjusted`로 표시됩니다.
3. **형상 생성**: build123d 파라메트릭 템플릿으로 만들고 trimesh 메시로 변환합니다.
4. **배치**: zone·group 힌트를 바탕으로 결정적 배치기가 좌표를 계산합니다. 공간이 부족하면 크기를 줄입니다(`resized_to_fit`).
5. **자동 검증**: 다음 항목을 검사합니다.
   - 케이지 적합, 겹침, 끼임 틈새(구조물·벽·천장), 출입구 막힘
   - 개구부 크기, 벽 두께(설계값 + 메시 측정), 오버행(서포트 필요), 출력 공간, watertight, 마릿수

검증 `error`가 남은 설계는 내려받을 수 없고, 사유가 사용자에게 표시됩니다. `warning`은 표시만 합니다.

**알려진 한계:** 끼임 틈새는 구조물 사이 최소 거리로 판정합니다. 곡면 구조물과 벽 사이에 생기는 쐐기형 틈(점점 좁아지는 틈)은 정밀하게 판정하지 않습니다.

## 배포 (Vercel)

한 Vercel 프로젝트에 [Services](https://vercel.com/docs/services)로 두 앱을 함께 배포합니다(`vercel.json`).

| 서비스 | 위치 | 런타임 | 경로 |
|---|---|---|---|
| `frontend` | `frontend/` | Next.js | `/*` |
| `backend` | `backend/` | 컨테이너 (`backend/Dockerfile`) | `/api/*` |

- **백엔드는 컨테이너로 배포합니다.** 형상 커널(OCP)을 포함한 의존성이 약 1 GB라 일반 Python 함수 한도(500 MB)를 넘기 때문입니다.
  - 이미지는 약 1.7 GB(압축 시 약 390 MB)이고, 콜드 스타트는 약 7~10초입니다.
- `/api/*` 요청은 경로를 그대로 유지한 채 백엔드로 전달됩니다. 그래서 백엔드는 `API_PREFIX=/api` 아래에서 응답합니다.
  - 프론트엔드는 같은 출처의 `/api`를 호출하므로(`NEXT_PUBLIC_API_BASE_URL=/api`) CORS 설정이 필요 없습니다.
- 컨테이너는 `/tmp`만 쓸 수 있고, 그마저 인스턴스마다 사라집니다.
  - 메시 캐시는 `/tmp`에 두고, 없으면 저장된 파라미터로 다시 만듭니다.
  - 데이터는 **Postgres(Neon)**에 저장합니다.

### 환경변수 (Vercel 프로젝트 설정)

| 변수 | 값 | 비고 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `/api` | 프론트엔드 빌드 시 반영. Vercel 빌드에서는 지정하지 않아도 `/api`가 기본값 |
| `API_PREFIX` | `/api` | 백엔드 라우트 접두사. 컨테이너 이미지 기본값이 `/api` |
| `LLM_DEADLINE_S` | `240` | 설계 1건에서 LLM에 쓰는 전체 시간 상한(초). Hobby 요청 한도 300초보다 작게 |
| `LLM_PROVIDER` | `auto` | 키가 없으면 모의 해석기로 동작 |
| `ANTHROPIC_MODEL` | 사용할 Claude 모델 ID | |
| `ANTHROPIC_API_KEY` | (직접 입력) | **Sensitive**로 등록하세요 |
| `DATABASE_URL` | Neon 연결 시 자동 주입 | 없으면 `/tmp` SQLite입니다. 데이터가 유지되지 않고, 인스턴스마다 데이터가 달라 설계를 못 찾는(404) 일이 생길 수 있습니다. `/api/health`의 `database.persistent`와 화면 안내로 표시됩니다. |

환경변수는 Production과 Preview에 모두 설정하세요.

### 리전

함수(백엔드 컨테이너)는 `vercel.json`의 `"regions": ["sin1"]`(싱가포르)에서 실행합니다.
DB도 같은 리전에 두세요. 설계 요청 하나에 DB 왕복이 여러 번 일어나므로, 함수와 DB가 같은 리전에 있어야 응답이 빠릅니다.
한국 사용자 기준으로는 한국↔싱가포르를 요청당 한 번만 오갑니다.

### Neon Postgres 연결

1. https://vercel.com/marketplace/neon 에서 **Install**을 누르고 팀을 선택합니다.
   - 리전은 **Singapore**, 플랜은 **Free**입니다.
   - **Auth·Realtime은 끕니다.** 이 앱은 로그인·실시간 구독을 쓰지 않습니다.
2. 프로젝트에 연결하고 Production·Preview·Development를 모두 선택합니다. `DATABASE_URL`이 자동으로 주입됩니다.
3. 다시 배포합니다. 테이블은 백엔드가 시작할 때 자동으로 생성됩니다.

백엔드는 `postgres://` URL을 psycopg 드라이버 URL로 자동 변환합니다. 연결 재확인(`pool_pre_ping`)으로 Neon이 유휴 상태에서 연결을 끊어도 다시 연결합니다.

### 제약 (Hobby 플랜)

- 비상업적 용도로만 쓸 수 있습니다. 서비스로 운영하려면 Pro 플랜이 필요합니다.
- 요청당 최대 300초, 2 GB / 1 vCPU입니다. 요청·응답 본문은 각각 4.5 MB까지입니다(현재 STL·3MF는 수백 KB 수준).
- 컨테이너 런타임은 베타입니다.

### 로컬에서 컨테이너 실행

```bash
docker build -t kkomul-backend backend/
docker run -p 8000:8000 -e PORT=8000 kkomul-backend   # http://localhost:8000/api/health
```

이미지는 기본으로 `/api` 접두사를 씁니다. 로컬 프론트엔드(`http://localhost:8000`)와 바로 연결하려면 `-e API_PREFIX=`를 추가하세요.

## 규칙 파일 교체 (전문가 검수 반영)

`backend/rules/species.yaml`과 `backend/rules/printing.yaml`의 수치는 모두 **임시 기본값**입니다.
검수를 마친 값으로 파일을 교체하고 서버를 재시작하면 반영됩니다.

- 파일 형식이 잘못되면 서버가 기동하지 않고 오류 위치를 알려줍니다. 키 오타, 누락, `safe_max ≥ passable_min` 같은 범위 오류가 이에 해당합니다.
- 검수가 끝나면 `reviewed: true`로 바꿔 주세요. `/health` 응답에도 이 값이 표시됩니다.
- 새 종을 추가할 때는 `species:` 아래에 같은 형식의 항목을 추가합니다.
