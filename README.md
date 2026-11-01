# 꼬물공방 (petlab)

소형 반려동물(MVP: 햄스터) 맞춤 케이지 구조물 설계 웹서비스.

사육 환경과 요구사항을 입력하면 AI가 구조물(은신처·터널·램프·모래목욕통)을 맞춤 설계합니다.
설계 결과는 3D 뷰어로 확인하고 3D 프린팅 파일(STL, 3MF)로 내려받을 수 있습니다.

## 설계 원칙

- **LLM은 형상을 만들지 않습니다.** 요구사항 해석, 템플릿 선택, 파라미터 값 결정, 설명 생성만 맡습니다.
- 형상은 검증된 **파라메트릭 템플릿 코드**(build123d)가 생성합니다.
- 배치 좌표도 결정적 배치기(placer)가 계산합니다.
- LLM 출력은 JSON 스키마(pydantic)로 강제합니다. 스키마를 위반하면 재시도하고, 그래도 실패하면 사용자에게 오류를 안내합니다.
- 종별 치수 기준은 `rules/species.yaml`, 출력 기준은 `rules/printing.yaml`에 있습니다. 코드에 하드코딩하지 않습니다.

## 폴더 구조

```
rules/       종별·출력 규칙 YAML (임시 기본값, 전문가 검수 대상)
backend/     FastAPI + build123d + trimesh (Python 3.11–3.13, uv)
frontend/    Next.js + react-three-fiber + Tailwind
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
| `RULES_DIR` | `.env` | 규칙 YAML 디렉터리 | `rules/` |
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
```

## 규칙 파일 교체 (전문가 검수 반영)

`rules/species.yaml`과 `rules/printing.yaml`의 수치는 모두 **임시 기본값**입니다.
검수를 마친 값으로 파일을 교체하고 서버를 재시작하면 반영됩니다.

- 파일 형식이 잘못되면 서버가 기동하지 않고 오류 위치를 알려줍니다. 키 오타, 누락, `safe_max ≥ passable_min` 같은 범위 오류가 이에 해당합니다.
- 검수가 끝나면 `reviewed: true`로 바꿔 주세요. `/health` 응답에도 이 값이 표시됩니다.
- 새 종을 추가할 때는 `species:` 아래에 같은 형식의 항목을 추가합니다.
