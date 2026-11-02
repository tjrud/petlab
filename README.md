# NestForge (petlab)

소형 반려동물(MVP: 햄스터) 맞춤 케이지 구조물 설계 웹서비스.

사육 환경과 요구사항을 입력하면 AI가 구조물(은신처·터널·램프·모래목욕통)을 맞춤 설계합니다.
설계 결과는 3D 뷰어로 확인하고 3D 프린팅 파일(STL, 3MF)로 내려받을 수 있습니다.

브랜드 에셋(로고·파비콘·공유 미리보기 이미지·색상 규칙)은 [`brand/`](brand/README.md)에 있습니다.
사이트에서 쓰는 파일은 `frontend/public/`(파비콘·로고)과 `frontend/src/app/opengraph-image.png`에 복사해 두었습니다.

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
| `ADMIN_USERNAME` | `.env` | 관리자 아이디 (32자 이하) | `admin` |
| `ADMIN_PASSWORD` | `.env` | 관리자 비밀번호(16자 이상, 긴 무작위 문자열 권장). 설정하면 관리자 인증이 켜집니다(아래 참고). | (없음 = 인증 꺼짐) |
| `SESSION_SECRET` | `.env` | 세션 쿠키 서명 키. `ADMIN_PASSWORD`를 쓰면 **필수**(32바이트 이상 무작위 문자열) | (없음) |
| `SESSION_TTL_HOURS` | `.env` | 로그인 유지 시간 | `24` |
| `AUTH_REQUIRED` | `.env` | `1`이면 `ADMIN_PASSWORD`가 없어도 인증을 끄지 않고 API를 막습니다(503). 컨테이너 이미지 기본값 `1` | `0` |
| `COOKIE_SECURE` | `.env` | 세션 쿠키 Secure 속성 강제(`1`/`0`). 비우면 요청이 HTTPS인지로 판단. 컨테이너 이미지 기본값 `1` | (자동) |
| `SIGNUP_ENABLED` | `.env` | 회원가입 허용 여부 | `1` |
| `SIGNUP_PER_IP_PER_HOUR` | `.env` | 같은 IP(IPv6 는 /56)에서 1시간에 시도할 수 있는 회원가입 횟수. `0` 이면 IP 별 제한 없음 | `5` |
| `DESIGN_DAILY_LIMIT` | `.env` | 회원 1명이 최근 24시간 동안 요청할 수 있는 설계·수정 횟수 (LLM 비용 상한, 관리자 제외, 실패한 요청 포함) | `20` |
| `DESIGN_IP_DAILY_LIMIT` | `.env` | 같은 IP(IPv6 는 /56)의 최근 24시간 설계·수정 횟수 (계정 여러 개로 우회 방지). `CLIENT_IP_HEADER` 가 있을 때만 적용, `0` 이면 끔 | `40` |
| `DESIGN_GLOBAL_DAILY_LIMIT` | `.env` | 서비스 전체의 최근 24시간 설계·수정 횟수 상한 (관리자 제외) | `300` |
| `POST_DAILY_LIMIT` / `COMMENT_DAILY_LIMIT` | `.env` | 회원 1명이 최근 24시간 동안 쓸 수 있는 글 / 댓글 수 (지운 글·댓글도 셈) | `20` / `100` |
| `EMAIL_PROVIDER` | `.env` | 이메일 인증 메일 발송 방식: `smtp`·`resend`·`file`(로컬: 파일로 저장). 비우면 이메일 인증을 쓰지 않음 | (없음) |
| `EMAIL_FROM` | `.env` | 보내는 사람. 예: `NestForge <no-reply@example.com>` | |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_SECURITY` | `.env` | SMTP 발송 설정 (`SMTP_SECURITY`: `starttls`·`ssl`·`none`) | `587`, `starttls` |
| `RESEND_API_KEY` | `.env` | Resend 발송 키 | |
| `APP_BASE_URL` | `.env` | 메일 속 인증 링크의 사이트 주소. 예: `https://petlab-sage.vercel.app` | (없음 = `CORS_ORIGINS` 첫 값) |
| `EMAIL_DAILY_LIMIT` | `.env` | 서비스 전체 최근 24시간 인증 메일 수 (메일 서비스 한도 보호) | `300` |
| `EMAIL_TOKEN_TTL_HOURS` | `.env` | 인증 링크 유효 시간 | `24` |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | `.env` | Cloudflare Turnstile 키. 둘 다 있으면 회원가입에 CAPTCHA 를 요구 | (없음) |
| `CLIENT_IP_HEADER` | `.env` | 로그인·가입 시도 제한, IP 별 설계 상한에 쓸 클라이언트 IP 헤더. 플랫폼이 덮어써 위조할 수 없는 헤더만 지정. 컨테이너 이미지 기본값 `x-vercel-forwarded-for` | (없음 = 접속 주소) |
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
# 회원 기능 테스트를 PostgreSQL 에서 실행 (테스트마다 새 DB 를 만든다)
cd backend && TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:5432 uv run pytest tests/test_members.py
cd frontend && npm run build             # 프론트엔드 타입 검사 + 빌드
cd frontend && npm run lint
```

E2E 스모크 테스트(Playwright)는 모의 해석기 모드의 백엔드와 프론트엔드 프로덕션 빌드를 자동으로 띄워 전체 흐름을 확인합니다.
흐름은 사육 환경 등록 → 요구사항 → 3D 뷰어 → 다운로드 → 제작 신청, 그리고 회원가입 → 반려동물 등록 → 설계 → 내 설계 내역 → 커뮤니티 공유·댓글입니다.

```bash
cd frontend
npx playwright install chromium   # 최초 1회
npm run test:e2e
```

## 회원·관리자 인증

사이트(화면)는 누구나 열 수 있습니다. **설계 만들기·내 설계 내역·내 정보·글쓰기는 회원 로그인 후에** 쓸 수 있고, 커뮤니티 읽기와 커뮤니티에 공유된 설계 보기는 누구나 할 수 있습니다.

- **회원**: 회원가입(아이디·닉네임·비밀번호)으로 만듭니다. 비밀번호는 scrypt 로 해시해 저장합니다.
  - 아이디는 영문 소문자·숫자·밑줄 4~20자, 비밀번호는 8자 이상이고 아이디와 달라야 합니다.
  - 닉네임은 2~20자, 한글·영문·숫자·공백과 `_ - .` 만 씁니다. 전각 문자 등은 정규화(NFKC)해 저장합니다.
    대소문자·공백·구분 기호만 다른 닉네임은 같은 닉네임으로 봅니다(`users.nickname_key`). 보이지 않는 문자나 다른 문자 체계의 닮은 글자로 다른 회원을 흉내 낼 수 없습니다.
  - 운영자를 사칭할 수 있는 아이디(admin, root 등)·닉네임(관리자, 운영자, 운영팀, NestForge 등, `NestF0rge` 같은 숫자 닮은꼴 포함)은 쓸 수 없습니다.
  - 같은 IP(IPv6 는 /56)에서 1시간에 `SIGNUP_PER_IP_PER_HOUR`번까지 가입을 시도할 수 있습니다. `SIGNUP_ENABLED=0`이면 가입을 받지 않습니다.
  - 로그인은 같은 IP 에서 15분에 10번까지 틀릴 수 있습니다(로그인에 성공해도 기록은 지우지 않음). 비밀번호 변경 시 현재 비밀번호는 회원별 15분에 5번까지 틀릴 수 있습니다.
    확인 중인 시도도 미리 세고 같은 키의 동시 시도는 3개까지라, 요청을 한꺼번에 보내도 이 횟수를 넘겨 맞혀 볼 수 없습니다.
- **관리자**: 환경변수 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 로 로그인합니다. 운영을 위해 모든 설계(모든 버전)를 볼 수 있고, 커뮤니티 글·댓글을 지울 수 있으며, 사용량 상한을 받지 않습니다.
  회원의 설계를 대신 수정하거나 커뮤니티에 공유할 수는 없습니다.
- **사용량 상한** (최근 24시간, `429`, 관리자 제외): 설계 생성·수정은 LLM 을 호출하므로 회원별(`DESIGN_DAILY_LIMIT`)·IP 별(`DESIGN_IP_DAILY_LIMIT`)·서비스 전체(`DESIGN_GLOBAL_DAILY_LIMIT`) 횟수를 제한합니다.
  - LLM 을 부르기 전에 한 번을 기록하므로(`usage_events` 테이블, 확인과 기록을 잠금 안에서 함께) 동시에 여러 번 요청해도 상한을 넘지 못하고, 해석에 실패한 요청도 비용이 들므로 횟수에 들어갑니다.
  - 글·댓글(`POST_DAILY_LIMIT`·`COMMENT_DAILY_LIMIT`), 사육 환경 등록(100회), 제작·배송 대기 신청(10회, 같은 이메일·설계는 한 번만)도 같은 방식으로 셉니다. 지워도 횟수는 그대로입니다. 글 보기에는 최근 댓글 200개를 보여 줍니다(전체 수는 함께 표시).
  - 계정을 대량으로 만들어 상한을 피하는 일은 아래 이메일 인증·CAPTCHA 로 막습니다 (설정했을 때).
- **이메일 인증** (`EMAIL_PROVIDER` 를 설정하면 켜짐): 가입할 때 이메일이 필수이고, 받은 메일의 링크를 눌러 인증하기 전에는
  설계 만들기·수정, 글·댓글 쓰기, 제작·배송 대기 신청을 할 수 없습니다(`403 email_unverified`). 로그인·내 정보·반려동물·읽기는 됩니다.
  - 링크는 무작위 토큰(DB 에는 SHA-256 해시만 저장)이고 한 번만, `EMAIL_TOKEN_TTL_HOURS`(기본 24시간) 동안 쓸 수 있습니다. 링크를 보낸 뒤 주소를 바꾸면 그 링크로는 인증되지 않습니다.
  - 같은 주소는 한 계정만 인증할 수 있습니다. 대소문자, 주소 뒤 `+태그`, Gmail 의 점(.)은 무시하고 비교합니다(`users.email_key`).
    인증 전 주소는 겹쳐도 되므로, 남의 주소를 먼저 적어 두는 것으로 그 사람의 가입을 막을 수 없습니다.
  - 인증 메일은 회원마다 1분에 1통, 24시간에 5통, 서비스 전체 24시간 `EMAIL_DAILY_LIMIT` 통까지 보냅니다. 내 정보에서 이메일을 바꾸면(현재 비밀번호 필요) 새 주소로 다시 인증합니다.
  - 이메일 기능 전에 가입한 회원은 내 정보에서 이메일을 등록하고 인증하면 됩니다. 관리자는 인증이 필요 없습니다.
  - 메일 설정이 잘못되면(예: `SMTP_HOST` 없음) 신규 가입을 막고(`503 email_unavailable`) 서버 로그와 `/api/health` 의 `email_verification: "misconfigured"` 로 알립니다. 기존 회원은 막지 않습니다.
- **CAPTCHA** (`TURNSTILE_SITE_KEY`·`TURNSTILE_SECRET_KEY` 를 설정하면 켜짐): 회원가입에 Cloudflare Turnstile 확인을 요구합니다. 서버가 Cloudflare 에 토큰을 확인하며(접속 IP 포함),
  아이디·닉네임 중복 확인보다 먼저 해서 가입 가능 여부를 자동으로 캐 볼 수 없게 합니다. 키가 하나만 있으면 가입을 막고(`503 captcha_unavailable`) 로그로 알립니다.
- **권한**: 사육 환경·설계·반려동물은 만든 회원의 것입니다. 남의 것은 존재 여부도 알리지 않고 `404` 를 반환합니다.
  - 커뮤니티 글에 내 설계를 첨부하면 **첨부한 버전만** 누구나 볼 수 있습니다(읽기 전용, 수정·재공유 불가). 첨부하지 않은 이전 버전과 공유한 뒤에 만든 버전은 계속 나만 봅니다. 글을 지우면 그 버전은 다시 비공개가 됩니다.
  - 이전 버전에서 만든(소유자가 없는) 설계는 관리자만 볼 수 있습니다.
- **세션**: HMAC-SHA256 으로 서명한 쿠키(HttpOnly, Secure(배포), SameSite=Lax, 기본 24시간)에 회원 id 와 세션 버전을 담습니다.
  - 회원이 비밀번호를 바꾸면 그 회원의 다른 기기 로그인이 풀립니다.
  - 서명 키는 `SESSION_SECRET`과 관리자 비밀번호로 만듭니다. 둘 중 하나를 바꾸면 **모든 회원의 로그인이 풀립니다.**
  - 로그아웃은 그 브라우저의 쿠키만 지웁니다. 로그아웃 API는 JSON 요청이고 교차 사이트 요청이 아닐 때만 처리합니다(강제 로그아웃 방지). 로그인 후 돌아갈 경로는 같은 사이트 안의 경로만 허용합니다.
- 설정이 불완전하면 인증을 끄지 않고 API를 `503 auth_unavailable`로 막습니다(fail closed). 서버 로그와 `/api/health`의 `auth_ready: false`로 알 수 있습니다.
  - `ADMIN_PASSWORD`가 16자 미만이거나 앞뒤에 공백·줄바꿈이 있는 경우, `SESSION_SECRET`이 없거나 32바이트 미만인 경우
  - (`ADMIN_USERNAME`의 앞뒤 공백은 자동으로 지웁니다)
  - `AUTH_REQUIRED=1`(컨테이너 이미지 기본값)인데 `ADMIN_PASSWORD`가 없는 경우
- 같은 IP(IPv6는 /64)에서 15분 안에 로그인을 10번 틀리면 잠시 막습니다. 인스턴스 메모리 기준입니다.
- API 응답은 `Cache-Control: no-store`(뷰어 메시는 `private`)라 CDN·공유 캐시에 남지 않습니다.
- 인증이 켜지면 Swagger UI(`/api/docs`)는 꺼집니다. 스키마 JSON(`/api/openapi.json`)은 공개입니다.
- 입력 검증 오류(422) 응답에는 입력값을 담지 않습니다. 커뮤니티 글·댓글·닉네임은 화면에 글자 그대로(HTML 해석 없이) 표시합니다.
- 로컬에서 `ADMIN_PASSWORD`를 비워 두면 인증이 꺼지고 모든 요청이 로컬 개발용 관리자(`local`)로 처리됩니다(`AUTH_REQUIRED` 미설정 시). 개발과 테스트용이며, 이때는 회원가입·로그인을 쓰지 않습니다.

### DB 마이그레이션

서버가 시작할 때 새 테이블(`users`, `pets`, `posts`, `comments`, `usage_events`, `cage_layouts`)을 만들고, 기존 테이블에 빠진 열(소유자 등)과 인덱스를 추가합니다.
추가만 하고 지우거나 바꾸지 않으므로 이전 버전 코드가 같은 DB 를 써도 동작합니다. Postgres 에서는 advisory lock 으로 여러 인스턴스의 동시 실행을 직렬화합니다.
이미 반영된 DB 에서는 DDL 을 보내지 않아(테이블 잠금 없음) 새 인스턴스가 떠도 쓰기 요청을 막지 않습니다.

### DB 연결

API 함수가 끝나면 응답을 보내기 전에 트랜잭션을 끝내 연결을 풀에 바로 돌려줍니다(`app/api/deps.py` 의 `make_router`).
FastAPI 는 의존성·API 함수·응답 직렬화를 서로 다른 스레드 작업으로 실행하므로, 연결을 쥔 채 다음 스레드를 기다리면 동시 요청이 몰릴 때 풀과 스레드가 서로를 기다리며 멈출 수 있기 때문입니다.
새 라우터는 `APIRouter` 대신 `make_router` 로 만드세요. LLM 호출·비밀번호 해시 동안에도 연결을 쥐지 않습니다.

## 구조물 템플릿

LLM은 아래 템플릿 중에서 고르고 파라미터 값만 정합니다. 각 템플릿은 `backend/app/templates/` 아래 한 모듈에 다음을 모아 둡니다.
- 파라미터 스키마와 허용 범위
- 종 규칙 기반 동적 제약
- 형상 생성 함수, 출력 자세
- 검증용 특징

단위 테스트는 `backend/tests/test_template_*.py`에 있습니다.

| 템플릿 | 파라미터 | 서포트 없는 출력 전략 |
|---|---|---|
| 은신처 `hideout` | 가로·세로·높이, 출입구 폭·개수(1~2), 환기구 개수·지름, 벽 두께 | 바닥이 열린 상자를 뒤집어 출력합니다. 아치 출입구는 바닥에서 시작하고, 환기구는 지붕에 수직으로 뚫습니다. 출입구가 2개면 뒷면에 같은 아치를 마주 보게 냅니다(역시 서포트 없이 출력). |
| 터널 `tunnel` | 길이, 내경, 휨 각도(0=직선), 벽 두께 | 바닥이 열린 아치 단면입니다. 꼭대기는 40° 티어드롭으로 처리하고, 곡률은 수평면에서 줍니다. |
| 램프/계단 `ramp` | 높이, 폭, 경사각, 단 수(0=경사로) | 속이 찬 단면을 압출하고 꼭대기에 발판을 둡니다. 경사로에는 미끄럼 방지 턱과 4mm 앞끝 두께를 둡니다. |
| 모래목욕통 `sand_bath` | 가로·세로, 안쪽 깊이, 턱 높이, 벽 두께 | 위가 열린 상자입니다. 앞면 출입 홈은 위에서 파냅니다. |

새 템플릿을 추가하는 순서는 다음과 같습니다.
1. `Template`을 구현합니다(`templates/base.py` 참고).
2. `templates/registry.py`에 등록합니다. LLM 스키마·프롬프트 카탈로그·검증에는 자동으로 반영됩니다.
3. 프론트엔드 `src/lib/templates.ts`에 색상과 파라미터 이름을 추가합니다.

## 가상 케이지 공간 설계 (`/cage`)

케이지 치수를 정하고 기본 에셋을 게임처럼 놓아 보는 화면입니다. 로그인하지 않아도 쓸 수 있고, 작업은 브라우저에 임시로 남습니다. 로그인하면 배치안을 계정에 저장합니다(`/layouts`).

- **케이지 크기**: 처음 크기는 종 규칙의 사육장 최소 기준(100×50×50cm). 프리셋(45×30×30 ~ 120×60×50cm), 직접 입력(서버 `CageIn` 과 같은 범위), 내 반려동물에 등록한 케이지. 줄였을 때 밖으로 나간 구조물을 안쪽으로 모을 수 있습니다.
- **기본 에셋** 17종 (`frontend/src/lib/cageAssets.ts`): 은신처 4·쳇바퀴 2·터널·땅굴 상자·플랫폼·경사로·다리·디딤돌·밥그릇·급수기·모래목욕통·화장실·쿨링 대리석. 치수는 흔한 제품 기준 근사치이고, 모양은 단순 도형으로 그립니다(`components/cage/AssetModel.tsx`).
  서버는 에셋 키만 저장하므로 키를 바꾸거나 지우지 말고 새 키를 추가하세요.
- **조작**: 끌어서 옮기기(1cm 격자, 벽·옆 구조물에 붙기), 회전(R 90°, Q/E 15°), 방향키 이동, 복제·삭제, 되돌리기/다시 하기, 3D·위·정면 시점, 위치·각도 직접 입력.
- **배치 검토** (`frontend/src/lib/cageLayout.ts`): 케이지 밖·케이지보다 높음·겹침은 오류, 끼임 틈(벽·구조물 사이, 플랫폼 위 천장)·출입구 앞 공간 막힘·출입구/터널 폭·오르는 높이·턱 높이·은신처 출입구 개수·모래목욕통 안쪽 크기·케이지 바닥이 최소 기준보다 작음은 경고입니다.
  수치는 `/species` 의 `layout_rules`(= `species.yaml`)를 따르며, 넘어갈 수 있는 낮은 물건(턱 높이 이하)은 틈·통로 판정에서 뺍니다.
- 새 에셋은 벽·모서리부터, 끼임 틈·출입구 막힘이 생기지 않는 자리를 골라 놓습니다.

## API

백엔드 실행 후 http://localhost:8000/docs 에서 전체 스키마를 볼 수 있습니다(인증이 꺼진 로컬 개발 환경). 인증이 켜져 있으면 `/openapi.json`만 제공합니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/auth/signup` | 회원가입 (가입 후 바로 로그인. 켜져 있으면 `email`·`captcha_token` 필요) |
| POST | `/auth/verify-email` | 이메일 인증 (메일 속 링크의 토큰, 로그인 없이) |
| POST | `/auth/verify-email/resend` | 인증 메일 다시 보내기 |
| PATCH | `/me/email` | 이메일 변경 (현재 비밀번호 필요, 새 주소로 인증 메일) |
| POST | `/auth/login` · `/auth/logout` | 로그인 · 로그아웃 |
| GET | `/auth/me` | 로그인 상태 |
| GET · PATCH | `/me` | 내 정보(통계·설계 사용량) · 닉네임 변경 |
| POST | `/me/password` | 비밀번호 변경 |
| GET · POST | `/me/pets` | 내 반려동물 목록 · 등록 |
| GET · PUT · DELETE | `/me/pets/{id}` | 반려동물 조회 · 수정 · 삭제 |
| GET · POST | `/layouts` | 가상 케이지 배치안 목록(최근 수정순) · 저장 (회원당 30개, 구조물 80개까지) |
| GET · PUT · DELETE | `/layouts/{id}` | 배치안 불러오기 · 덮어쓰기 · 삭제 (내 것만) |
| GET | `/designs?page=&page_size=` | 내 설계 내역 (최근 수정순) |
| GET · POST | `/community/posts` | 글 목록(누구나) · 글쓰기(설계 첨부 가능) |
| GET · PATCH · DELETE | `/community/posts/{id}` | 글 보기(누구나) · 수정(작성자) · 삭제(작성자·관리자) |
| POST | `/community/posts/{id}/comments` | 댓글 쓰기 |
| DELETE | `/community/comments/{id}` | 댓글 삭제(작성자·관리자) |
| POST | `/habitats` | 사육 환경 등록 (종, 크기, 마릿수, 케이지 내부 치수 mm, 선택: 내 반려동물) |
| GET | `/habitats/{id}` | 사육 환경 조회 (내 것만) |
| POST | `/designs` | 프롬프트로 설계 생성 → 버전 1 |
| POST | `/designs/{id}/revise` | 추가 프롬프트로 수정 → 새 버전 (이전 버전 유지, `base_version` 지정 가능) |
| GET | `/designs/{id}?version=` | 설계 조회 (버전 목록, 항목·배치, 검증 보고서) |
| GET | `/designs/{id}/export?format=stl\|3mf&version=` | 3D 프린팅 파일. STL은 파트가 여럿이면 zip입니다. 검증 오류가 있으면 409를 반환합니다. |
| GET | `/designs/{id}/versions/{v}/parts/{i}.stl` | 뷰어용 메시 (케이지 좌표계, mm, Z-up) |
| GET | `/species` | 등록 가능한 종·크기와 배치 검토 규칙 값(`layout_rules`) (규칙 파일 기준, 누구나) |
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
   - 개구부 크기, 은신처 출입구 개수(여러 마리일 때), 벽 두께(설계값 + 메시 측정), 오버행(서포트 필요), 출력 공간, watertight
   - 경고만 하는 항목: 마릿수, 사육장 바닥 최소 기준

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
| `ADMIN_USERNAME` | (직접 입력) | 관리자 아이디(32자 이하, 넘으면 API 가 503 으로 막힘). 기본값 `admin`보다 추측하기 어려운 값을 권장 |
| `ADMIN_PASSWORD` | (직접 입력, 16자 이상) | **Sensitive**. 관리자 로그인 비밀번호. 없으면 API가 503으로 막힙니다 |
| `SESSION_SECRET` | (32바이트 이상 무작위 문자열) | **Sensitive**. 세션 쿠키 서명 키. 없으면 API가 503으로 막힙니다 |
| `EMAIL_PROVIDER` 등 | 아래 "이메일 인증·CAPTCHA 켜기" 참고 | 비밀값(`SMTP_PASSWORD`·`RESEND_API_KEY`·`TURNSTILE_SECRET_KEY`)은 **Sensitive** |
| `DATABASE_URL` | Neon 연결 시 자동 주입 | 없으면 `/tmp` SQLite입니다. 데이터가 유지되지 않고, 인스턴스마다 데이터가 달라 설계를 못 찾는(404) 일이 생길 수 있습니다. `/api/health`의 `database.persistent`와 화면 안내로 표시됩니다. |

환경변수는 Production과 Preview에 모두 설정하세요.

### 이메일 인증·CAPTCHA 켜기

**CAPTCHA (Cloudflare Turnstile, 무료)**
1. Cloudflare 대시보드 → Turnstile → 사이트 추가. 도메인에 `petlab-sage.vercel.app`(실제 서비스 주소)을 넣고, 위젯 모드는 Managed 를 고릅니다.
2. 발급된 Site Key 를 `TURNSTILE_SITE_KEY`, Secret Key 를 `TURNSTILE_SECRET_KEY`(Sensitive)로 등록하고 재배포합니다.
   사이트 키는 서버가 `/api/auth/me` 로 화면에 알려 주므로 프론트엔드 설정은 따로 없습니다.

**이메일 (둘 중 하나)**
- Gmail SMTP (도메인 없이 바로 가능, 하루 약 500통): Google 계정에 2단계 인증을 켜고 앱 비밀번호를 만든 뒤
  `EMAIL_PROVIDER=smtp`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USERNAME=<gmail 주소>`, `SMTP_PASSWORD=<앱 비밀번호>`(Sensitive),
  `EMAIL_FROM=NestForge <같은 gmail 주소>` 로 등록합니다.
- Resend (보내는 도메인을 인증해야 다른 사람에게 보낼 수 있음): `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`(Sensitive), `EMAIL_FROM=NestForge <no-reply@인증한-도메인>`.

두 경우 모두 `APP_BASE_URL=https://petlab-sage.vercel.app` 을 함께 등록하고 재배포합니다. 적용 여부는 `/api/health` 의 `email_verification`·`captcha` 가 `enabled` 인지로 확인합니다.

### 공개 범위 (Deployment Protection)

Vercel 보호는 **완전히 끄지 마세요.** Vercel은 예전 배포를 각자의 주소로 계속 열어 두고, 각 배포는 만들 당시의 코드로 동작합니다.
보호를 끄면 관리자 인증이 들어가기 전에 만든 배포의 API가 로그인 없이 열립니다.

- 권장 설정: Settings → Deployment Protection → Vercel Authentication → **Standard Protection**
  (API 값 `prod_deployment_urls_and_all_previews`). production 대표 주소(예: `petlab-sage.vercel.app`)만 공개되고,
  배포마다 생기는 주소와 프리뷰는 Vercel 로그인이 필요합니다.
- 보호 범위를 줄이기 전에 production 대표 주소에서 로그인 없이 `GET /api/species`가 `401`인지 먼저 확인하세요.

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

`backend/rules/species.yaml`과 `backend/rules/printing.yaml`은 아직 전문가 검수 전입니다.
검수를 마친 값으로 파일을 교체하고 서버를 재시작하면 반영됩니다.

`species.yaml`에는 값마다 근거가 주석으로 달려 있습니다.

- `[근거]`: 공개 문서에 수치가 있는 값입니다. 출처는 독일 수의사 동물보호협회(TVT)의 햄스터 안내서와 독일 동물보호연맹(DTSchB)의 소동물 용품 입장문입니다.
  - 출입구·터널 최소 폭: 드워프 5cm, 골든 7cm
  - 모래목욕통 최소 20×20cm
  - 여러 마리를 함께 키울 때 은신처 출입구 2개 이상. DTSchB가 든 이유("서로 피하고 서열 다툼 때 막다른 곳이 없도록")가 함께 지낼 때의 이야기라서, 혼자 키울 때는 1개도 됩니다.
  - 사육장 바닥 최소 100×50cm (작으면 경고만 함)
  - 단독 사육
- `[임시]`: 근거 수치를 찾지 못한 값입니다. 검수 때 먼저 확인해야 합니다. 램프 경사, 오르는 높이, 턱 높이, 끼임 안전 틈, 갉음 벽 두께, 모래목욕통 깊이, 혼자 키울 때 은신처 출입구 개수(1)가 여기에 해당합니다.

- 파일 형식이 잘못되면 서버가 기동하지 않고 오류 위치를 알려줍니다. 키 오타, 누락, `safe_max ≥ passable_min` 같은 범위 오류가 이에 해당합니다.
- 검수가 끝나면 `reviewed: true`로 바꿔 주세요. `/health` 응답에도 이 값이 표시됩니다.
- 새 종을 추가할 때는 `species:` 아래에 같은 형식의 항목을 추가합니다.
