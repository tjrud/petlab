# 꼬물공방 백엔드 컨테이너 이미지 (FastAPI + build123d/OCP)
#
# Vercel Services 에서 runtime "container" 로 빌드된다 (빌드 컨텍스트 = backend/).
# 로컬 실행:
#   docker build -t kkomul-backend backend/
#   docker run -p 8000:8000 -e PORT=8000 kkomul-backend        # → http://localhost:8000/api/health
#   (접두사 없이 쓰려면 -e API_PREFIX= 를 추가)
#
# 의존성(OCP 형상 커널 등)이 약 1 GB 라 Vercel 의 일반 Python 함수(500 MB)에는 들어가지 않아 컨테이너로 배포한다.
ARG PYTHON_IMAGE=python:3.13-slim

# ---- 1) 잠금 파일(uv.lock) 기준 Python 의존성 (dev 그룹 제외) ----------------
FROM ${PYTHON_IMAGE} AS deps
# 바이트코드는 최종 단계에서 한 번에 컴파일한다 (unchecked-hash: 이미지 변환으로 mtime 이 바뀌어도 유효)
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /build
COPY pyproject.toml uv.lock ./
# tool.uv.package = false 이므로 프로젝트 자체는 설치하지 않고 의존성만 설치한다
RUN uv sync --frozen --no-dev --no-cache

# ---- 2) libGL.so.1 / libGLX.so.0 만 추출 (mesa + LLVM ~200 MB 제외) -----------
# OCP 는 libGL·libX11·libexpat 에 링크되어 있어 slim 이미지에서는 import 가 실패한다.
# 렌더링은 하지 않으므로 GL 디스패치 라이브러리가 로드만 되면 된다.
FROM ${PYTHON_IMAGE} AS glvnd
RUN apt-get update \
 && cd /tmp && apt-get download libgl1 libglx0 \
 && mkdir -p /out && for d in /tmp/*.deb; do dpkg-deb -x "$d" /out; done \
 && rm -rf /var/lib/apt/lists/* /out/usr/share

# ---- 3) 런타임 -----------------------------------------------------------------
FROM ${PYTHON_IMAGE}
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglvnd0 libx11-6 libexpat1 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=glvnd /out/usr/lib/ /usr/lib/
RUN ldconfig

COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
COPY app ./app
COPY rules ./rules
# 루트 파일 시스템이 읽기 전용이라 실행 중에는 .pyc 를 쓸 수 없다 → 미리 컴파일해 콜드 스타트를 줄인다
# (일부 패키지의 의도적 문법 오류 예제 파일 때문에 실패해도 빌드는 계속한다 — 컴파일은 최적화일 뿐)
RUN python -m compileall -q -j0 --invalidation-mode unchecked-hash \
      /usr/local/lib/python3.13 /opt/venv/lib/python3.13/site-packages /app/app >/dev/null 2>&1 || true \
 && python -c "import app.main" 2>/dev/null || true

# 파일 시스템은 /tmp 만 쓰기 가능하고 인스턴스마다 휘발된다.
# - 메시 캐시는 /tmp 에 두고, 없으면 저장된 파라미터로 다시 만든다 (결정적).
# - DATABASE_URL 은 배포 환경변수(Neon Postgres)가 덮어쓴다. 기본값 SQLite(/tmp)는 데이터가 유지되지 않으며,
#   이 경우 /api/health 의 database.persistent=false 와 화면 안내로 표시된다.
# API_PREFIX=/api: 이 이미지는 Vercel rewrite(/api/* → backend, 경로 유지) 뒤에서만 실행된다
# AUTH_REQUIRED=1: ADMIN_PASSWORD·SESSION_SECRET 이 빠지면 인증을 끄지 않고 API 를 503 으로 막는다
# COOKIE_SECURE=1: 세션 쿠키는 항상 Secure (HTTPS 전용)
# CLIENT_IP_HEADER: 로그인 시도 제한에 쓰는 클라이언트 IP (Vercel 이 설정하는 헤더)
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_PREFIX=/api \
    AUTH_REQUIRED=1 \
    COOKIE_SECURE=1 \
    CLIENT_IP_HEADER=x-vercel-forwarded-for \
    EPHEMERAL_FILESYSTEM=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    RULES_DIR=/app/rules \
    MESH_CACHE_DIR=/tmp/meshes \
    DATABASE_URL=sqlite:////tmp/kkomul.db

# Vercel 은 PORT 환경변수(없으면 80)로 요청을 보낸다. 80 포트 바인딩을 위해 root 로 실행한다
# (컨테이너는 Vercel 샌드박스 안에서 격리되어 실행된다).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-80} --proxy-headers --forwarded-allow-ips='*'"]
