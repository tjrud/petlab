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

## 규칙 파일 교체 (전문가 검수 반영)

`rules/species.yaml`과 `rules/printing.yaml`의 수치는 모두 **임시 기본값**입니다.
검수를 마친 값으로 파일을 교체하고 서버를 재시작하면 반영됩니다.

- 파일 형식이 잘못되면 서버가 기동하지 않고 오류 위치를 알려줍니다. 키 오타, 누락, `safe_max ≥ passable_min` 같은 범위 오류가 이에 해당합니다.
- 검수가 끝나면 `reviewed: true`로 바꿔 주세요. `/health` 응답에도 이 값이 표시됩니다.
- 새 종을 추가할 때는 `species:` 아래에 같은 형식의 항목을 추가합니다.
