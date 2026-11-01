# 꼬물공방 백엔드 컨테이너 이미지 (FastAPI + build123d/OCP)
#
# Vercel Services 에서 runtime "container" 로 빌드된다 (빌드 컨텍스트 = backend/).
# 로컬 실행:
#   docker build -t kkomul-backend backend/
#   docker run -p 8000:8000 -e PORT=8000 kkomul-backend
#
# 의존성(OCP 형상 커널 등)이 약 1 GB 라 Vercel 의 일반 Python 함수(500 MB)에는 들어가지 않아 컨테이너로 배포한다.
ARG PYTHON_IMAGE=python:3.13-slim

# ---- 1) 잠금 파일(uv.lock) 기준 Python 의존성 (dev 그룹 제외) ----------------
FROM ${PYTHON_IMAGE} AS deps
ENV UV_COMPILE_BYTECODE=1 \
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

# 파일 시스템은 /tmp 만 쓰기 가능하고 인스턴스마다 휘발된다.
# - 메시 캐시는 /tmp 에 두고, 없으면 저장된 파라미터로 다시 만든다 (결정적).
# - DATABASE_URL 은 배포 환경변수(Neon Postgres)가 덮어쓴다. 기본값 SQLite(/tmp)는 데이터가 유지되지 않는다.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    RULES_DIR=/app/rules \
    MESH_CACHE_DIR=/tmp/meshes \
    DATABASE_URL=sqlite:////tmp/kkomul.db

# Vercel 은 PORT 환경변수(없으면 80)로 요청을 보낸다. 80 포트 바인딩을 위해 root 로 실행한다
# (컨테이너는 Vercel 샌드박스 안에서 격리되어 실행된다).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-80} --proxy-headers --forwarded-allow-ips='*'"]
