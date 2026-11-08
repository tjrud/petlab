"""형상 지문: 저장한 설계 버전을 지금 배포된 코드로 똑같이 다시 만들 수 있는지 확인하는 데 쓴다.

메시 캐시(MESH_CACHE_DIR)는 인스턴스마다 사라질 수 있어, 캐시가 없으면 저장된 파라미터로 형상을 다시 만든다.
그 사이 템플릿 build()·테셀레이션 설정·형상 라이브러리가 바뀌면 검증을 통과했던 버전도 다른 형상이 될 수 있다.

- file_digest: 메시 파일(STL 바이트)의 SHA-256. 버전을 저장할 때 파일별로 기록해 두고, 다시 만든 파일과 비교한다.
  같으면 검증했던 형상과 바이트 단위로 같은 파일이다 (진짜 판정 기준).
- geometry_fingerprint: 형상을 만드는 코드·설정·라이브러리 버전의 지문. 버전에 함께 기록해 바뀐 원인을
  로그로 알리고, 뷰어 메시 URL(?g=)에 붙여 배포가 바뀌면 브라우저 캐시가 옛 형상을 섞어 보여주지 않게 한다.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import sys
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from app.rules.loader import PrintingRules

# 모든 템플릿의 형상에 영향을 주는 공용 코드: 템플릿 계약, B-rep → 메시 변환·출력 자세, 형상 생성, 배치 변환
SHARED_MODULES: tuple[str, ...] = ("app.templates.base", "app.geometry.mesh", "app.services.engine", "app.domain")
# 테셀레이션·메시 처리 결과를 바꿀 수 있는 라이브러리 (설치되지 않은 이름은 건너뛴다)
LIBRARIES: tuple[str, ...] = ("build123d", "cadquery-ocp", "cadquery-ocp-novtk", "trimesh", "numpy")


def file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=None)
def _module_digest(name: str) -> str:
    """모듈 소스 파일의 해시 (실행 중에는 바뀌지 않으므로 한 번만 읽는다)."""
    mod = sys.modules.get(name)
    try:
        # 모듈을 불러오지 않고 소스 파일만 읽는다 (설계 조회가 형상 커널을 불러오지 않게)
        origin = mod.__file__ if mod is not None else importlib.util.find_spec(name).origin  # type: ignore[union-attr]
        return file_digest(Path(origin).read_bytes())  # type: ignore[arg-type]
    except (TypeError, OSError, AttributeError, ImportError):
        # 소스를 읽을 수 없는 배포 형태. 지문은 참고용일 뿐이고 판정은 파일 해시로 하므로 기동은 막지 않는다.
        return f"unreadable:{name}"


@lru_cache(maxsize=1)
def _library_versions() -> tuple[tuple[str, str], ...]:
    out = []
    for dist in LIBRARIES:
        try:
            out.append((dist, importlib.metadata.version(dist)))
        except importlib.metadata.PackageNotFoundError:
            continue
    return tuple(out)


def geometry_fingerprint(template_keys: Iterable[str], printing: PrintingRules) -> str:
    """주어진 템플릿들의 형상을 만드는 지금 코드·설정의 지문 (SHA-256 hex)."""
    from app.templates.keys import TEMPLATE_MODULES

    templates: dict[str, str] = {}
    for key in sorted(set(template_keys)):
        module = TEMPLATE_MODULES.get(key)
        templates[key] = _module_digest(module) if module else "missing"  # 없으면 삭제된 템플릿
    payload = {
        "templates": templates,
        "shared": {m: _module_digest(m) for m in SHARED_MODULES},
        "libraries": dict(_library_versions()),
        "tessellation": [printing.tessellation_tolerance_mm, printing.tessellation_angular_tolerance_deg],
    }
    return file_digest(json.dumps(payload, sort_keys=True).encode())
