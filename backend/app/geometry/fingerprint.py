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
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.rules.loader import PrintingRules

# 모든 템플릿의 형상에 영향을 주는 공용 코드: 템플릿 계약, B-rep → 메시 변환·출력 자세, 형상 생성, 배치 변환,
# 조립형 템플릿의 부품 라이브러리(app.templates.parts)
SHARED_MODULES: tuple[str, ...] = (
    "app.templates.base", "app.geometry.mesh", "app.services.engine", "app.domain",
    "app.templates.parts.common", "app.templates.parts.shell", "app.templates.parts.openings", "app.templates.parts.levels",
    "app.templates.decor",
)
# 각인 글꼴: 글꼴 파일이 바뀌면 각인 형상이 바뀐다
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
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
def _font_digests() -> tuple[tuple[str, str], ...]:
    try:
        return tuple((f.name, file_digest(f.read_bytes())) for f in sorted(FONT_DIR.glob("*.[ot]tf")))
    except OSError:
        return ()


@lru_cache(maxsize=1)
def _library_versions() -> tuple[tuple[str, str], ...]:
    out = []
    for dist in LIBRARIES:
        try:
            out.append((dist, importlib.metadata.version(dist)))
        except importlib.metadata.PackageNotFoundError:
            continue
    return tuple(out)


# 자유 조립 항목의 형상에 영향을 주는 코드 (부품 템플릿과 함께 지문에 넣는다). 조립 해석기(app.modules.compose)는
# 넣지 않는다: 다시 만들 때는 저장된 구조(ResolvedAssembly)만 쓰고 해석기를 부르지 않는다
ASSEMBLY_MODULES: tuple[str, ...] = (
    "app.modules.assembly", "app.modules.module_template", "app.modules.composed", "app.modules.structure",
)
ASSEMBLY_KEY = "assembly"

# 지문에 넣는 항목: 템플릿 키(옛 호출), 저장된 항목 dict (DesignVersion.items), 또는 BuiltItem (key·template 속성)
FingerprintItem = Any


def _template_digest(key: str) -> str:
    from app.templates.keys import TEMPLATE_MODULES

    module = TEMPLATE_MODULES.get(key)
    return _module_digest(module) if module else "missing"  # 삭제된 템플릿


def _stored_assembly(item: FingerprintItem) -> Mapping[str, Any] | None:
    """조립 항목의 저장 형태(ResolvedAssembly dict). 조립 항목이 아니면 None."""
    if isinstance(item, Mapping):
        raw = item.get("assembly")
        return raw if isinstance(raw, Mapping) else None
    template = getattr(item, "template", None)
    resolved = getattr(template, "resolved", None)
    return resolved.stored() if resolved is not None else None


def _assembly_entry(raw: Mapping[str, Any]) -> tuple[str, str]:
    """조립 항목 하나의 (지문 키, 값): "assembly:" + 구조(parts·joins)의 해시 → 조립 코드·쓰는 부품 템플릿의 해시."""
    from app.modules.structure import ResolvedAssembly, canonical_json

    try:
        resolved = ResolvedAssembly.from_stored(raw)
        geo = resolved.geometry_digest()
        templates = sorted({p.template for p in resolved.parts})
    except ValueError:  # 잘못 저장된 구조: 지문은 참고용이라 원본 그대로 해시한다
        geo = file_digest(canonical_json({"parts": raw.get("parts"), "joins": raw.get("joins")}).encode())
        templates = sorted({str(p.get("template")) for p in raw.get("parts") or [] if isinstance(p, Mapping)})
    payload = {
        "assembly": {m: _module_digest(m) for m in ASSEMBLY_MODULES},
        "parts": {k: _template_digest(k) for k in templates},
    }
    return f"{ASSEMBLY_KEY}:{geo}", file_digest(json.dumps(payload, sort_keys=True).encode())


def _entry(item: FingerprintItem) -> tuple[str, str]:
    if isinstance(item, str):
        return item, _template_digest(item)
    raw = _stored_assembly(item)
    if raw is not None:
        return _assembly_entry(raw)
    key = item.get("template") if isinstance(item, Mapping) else getattr(item, "key", None)
    key = str(key)
    return key, _template_digest(key)


def geometry_fingerprint(items: Iterable[FingerprintItem], printing: PrintingRules) -> str:
    """주어진 항목들의 형상을 만드는 지금 코드·설정의 지문 (SHA-256 hex).

    items: 저장된 항목 dict·BuiltItem·템플릿 키. 부품 하나짜리 항목은 템플릿 모듈의 해시(예전과 같은 값),
    조립 항목은 "assembly:<구조 해시>" → 조립 코드(ASSEMBLY_MODULES)와 쓰는 부품 템플릿의 해시."""
    templates = dict(_entry(it) for it in items)
    payload = {
        "templates": dict(sorted(templates.items())),
        "shared": {m: _module_digest(m) for m in SHARED_MODULES},
        "libraries": dict(_library_versions()),
        "fonts": dict(_font_digests()),
        "tessellation": [printing.tessellation_tolerance_mm, printing.tessellation_angular_tolerance_deg],
    }
    return file_digest(json.dumps(payload, sort_keys=True).encode())
