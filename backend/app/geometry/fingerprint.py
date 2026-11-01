"""형상 지문(fingerprint)과 메시 요약값(digest).

DB 에는 설계 버전의 '파라미터·배치'만 남고, 메시는 캐시가 없을 때 *현재 배포된* 코드로 다시 만든다.
템플릿 build() 나 테셀레이션 설정이 바뀌면 같은 파라미터라도 다른 형상이 나올 수 있으므로 두 값을 함께 쓴다.

- 파이프라인 지문: 형상을 만드는 코드(사용한 템플릿 모듈 + 공용 형상 코드)의 소스, 형상 커널·메시 라이브러리
  버전, printing.yaml 의 테셀레이션 설정을 합친 해시. 설계 버전을 저장할 때 기록하고, 메시 캐시 경로의 키로 쓴다.
  (같으면 같은 메시가 나온다고 *기대*할 수 있다.)
- 메시 요약값: 실제로 만든 메시(정점·면)의 해시. 다시 만든 메시가 저장 당시 검증한 메시와 같은지의
  *최종 판정*은 이 값으로 한다. 지문이 놓친 변경(지문에 넣지 않은 모듈 등)도 여기서 걸러진다.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import logging
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import trimesh

from app.rules.loader import PrintingRules
from app.templates.registry import all_templates

log = logging.getLogger(__name__)

# 지문 형식 버전. 지문 계산 방식 자체를 바꾸면 올린다.
_SCHEME = "kkomul-geometry/1"

# 모든 템플릿이 공유하는 형상 생성 경로: 템플릿 계약, 형상 → 메시 변환·출력 자세, 배치 메시(world_mesh),
# build_item(메시 원점 정렬). engine 모듈에는 형상과 무관한 코드도 있어 그 변경에도 지문이 바뀌지만,
# 그때는 다시 만든 메시를 요약값으로 비교할 뿐이라 안전하다.
COMMON_MODULES: tuple[str, ...] = (
    "app.templates.base",
    "app.geometry.mesh",
    "app.domain",
    "app.services.engine",
)

# 테셀레이션·불리언 결과에 영향을 주는 라이브러리 (cadquery-ocp 는 배포판 이름이 두 가지)
LIBRARIES: tuple[str, ...] = ("build123d", "cadquery-ocp-novtk", "cadquery-ocp", "trimesh", "numpy")

# 메시 요약값의 좌표 격자 (mm). 같은 코드에서 생길 수 있는 부동소수점 끝자리 차이는 무시하고,
# 출력에 의미 있는 변화(노즐 0.4mm, 적층 0.1mm 수준)보다 훨씬 작은 변화까지 잡는다.
DIGEST_GRID_MM = 1e-3


def _sha256(*chunks: bytes) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(len(c).to_bytes(8, "little"))  # 경계 표시 (a+bc 와 ab+c 구분)
        h.update(c)
    return h.hexdigest()


def module_source_hash(module_name: str) -> str:
    """모듈 소스 파일의 해시. 소스를 읽을 수 없으면 모듈 이름만 쓴다 (요약값 비교가 여전히 형상을 지킨다)."""
    path = getattr(importlib.import_module(module_name), "__file__", None)
    try:
        if path is None:
            raise FileNotFoundError(module_name)
        return _sha256(Path(path).read_bytes())
    except OSError:
        log.warning("형상 지문: %s 의 소스를 읽지 못해 모듈 이름만 반영합니다.", module_name)
        return _sha256(f"nosource:{module_name}".encode())


def _library_versions() -> str:
    out = []
    for name in LIBRARIES:
        try:
            out.append(f"{name}={importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            out.append(f"{name}=-")
    return ";".join(out)


class GeometryFingerprinter:
    """현재 코드·설정의 파이프라인 지문. 소스 해시는 생성 시 한 번만 계산한다."""

    def __init__(self, printing: PrintingRules):
        tessellation = f"tol={printing.tessellation_tolerance_mm!r};ang={printing.tessellation_angular_tolerance_deg!r}"
        self.common = _sha256(
            _SCHEME.encode(),
            tessellation.encode(),
            _library_versions().encode(),
            *(f"{m}:{module_source_hash(m)}".encode() for m in COMMON_MODULES),
        )
        self.templates: dict[str, str] = {
            t.key: module_source_hash(type(t).__module__) for t in all_templates()
        }

    def for_templates(self, keys: Iterable[str]) -> str:
        """설계 버전이 쓰는 템플릿들에 대한 지문. 다른 템플릿만 바뀌었으면 이 값은 그대로다."""
        parts = [self.common.encode()]
        for key in sorted(set(keys)):
            parts.append(f"{key}:{self.templates.get(key, 'missing')}".encode())
        return _sha256(*parts)


def mesh_digest(*meshes: trimesh.Trimesh | None) -> str:
    """메시들의 정점(격자 반올림)·면 배열 해시. 항목 하나의 출력 메시와 배치 메시를 함께 넣는다."""
    chunks: list[bytes] = []
    for m in meshes:
        if m is None:
            chunks.append(b"none")
            continue
        v = np.round(np.asarray(m.vertices, dtype=np.float64) / DIGEST_GRID_MM).astype("<i8")
        f = np.asarray(m.faces).astype("<i8")
        chunks += [np.array(v.shape + f.shape, dtype="<i8").tobytes(), v.tobytes(), f.tobytes()]
    return _sha256(*chunks)


def geometry_key(digests: Iterable[str]) -> str:
    """버전 전체 형상의 짧은 키 (뷰어 메시 URL 의 ?g= 값). 형상이 바뀌면 URL 이 바뀌어 브라우저 캐시가 섞이지 않는다."""
    return _sha256(*(d.encode() for d in digests))[:16]
