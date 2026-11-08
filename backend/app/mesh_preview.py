"""3D 미리보기용 가벼운 메시 (탐색 3D 미리보기·가상 케이지가 원본 대신 받는다).

원본 STL·3MF 는 수십 MB 라 화면에서 받기에 무겁다. 올릴 때 한 번 다음처럼 줄인 사본을 따로 저장한다.
- 같은 위치의 꼭짓점을 합치고(인덱스), 삼각형이 PREVIEW_MAX_TRIS 보다 많으면 QEM 으로 줄인다
  (예: 66만 → 10만 삼각형, 표면 오차 약 0.01 mm)
- 좌표는 외곽 상자 기준 16비트 정수로, 전체를 gzip 으로 묶는다 (33 MB → 약 0.8 MB)
원본 파일은 그대로 두고 내려받기에 쓴다.

형식 NFM1 (리틀 엔디언, 파일 전체를 gzip):
  0   4s  b"NFM1"
  4   u32 flags (bit0: 인덱스가 u16, 아니면 u32)
  8   u32 꼭짓점 수
  12  u32 삼각형 수
  16  f32[3] 원점 (외곽 상자 최솟값, mm)
  28  f32[3] 한 칸 크기 (mm, = 외곽 크기 / 65535)
  40  u16[꼭짓점*3] 좌표, 4바이트 경계까지 0 채움, u16|u32[삼각형*3] 인덱스 (원본과 같은 감김 방향)
"""

from __future__ import annotations

import gzip
import io
import logging
import struct
import threading

import numpy as np

from app.market_formats import load_3mf, mesh_dims, mesh_extents

log = logging.getLogger(__name__)

PREVIEW_MAX_TRIS = 100_000
PREVIEW_CONTENT_TYPE = "application/octet-stream"
# 만드는 동안 수백 MB 를 쓰므로 한 인스턴스에서 한 번에 하나만
_SLOT = threading.BoundedSemaphore(1)
_STL_RECORD = np.dtype([("normal", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])


def preview_key(file_id: str) -> str:
    return f"market/{file_id}/{file_id}.preview.nfm"


def _binary_stl(data: bytes) -> tuple[np.ndarray, np.ndarray] | None:
    n = int.from_bytes(data[80:84], "little") if len(data) >= 84 else 0
    if n <= 0 or 84 + 50 * n != len(data):
        return None
    v = np.frombuffer(data, dtype=_STL_RECORD, count=n, offset=84)["v"].reshape(-1, 3)
    # 같은 위치(비트까지 같은) 꼭짓점을 하나로
    keys = np.ascontiguousarray(v).view(np.dtype((np.void, 12))).ravel()
    _, first, inv = np.unique(keys, return_index=True, return_inverse=True)
    del keys
    verts = np.ascontiguousarray(v[first], dtype=np.float32)
    faces = inv.reshape(-1, 3).astype(np.int32)
    return verts, faces


def _with_trimesh(fmt: str, data: bytes) -> tuple[np.ndarray, np.ndarray] | None:
    if fmt == "3mf":
        m = load_3mf(data)  # 풀린 크기가 크면(압축 폭탄) None
        if m is None:
            return None
    else:
        import trimesh  # 무거운 모듈이라 필요할 때만

        m = trimesh.load(io.BytesIO(data), file_type=fmt, force="mesh")
    return np.asarray(m.vertices, dtype=np.float32), np.asarray(m.faces, dtype=np.int32)


def _pack(verts: np.ndarray, faces: np.ndarray) -> bytes:
    lo = verts.min(axis=0)
    span = np.maximum(verts.max(axis=0) - lo, 1e-6)
    q = np.round((verts - lo) / span * 65535).astype("<u2")
    u16 = len(verts) <= 65535
    idx = faces.astype("<u2" if u16 else "<u4")
    head = b"NFM1" + struct.pack("<III3f3f", 1 if u16 else 0, len(verts), len(faces), *lo.tolist(), *(span / 65535).tolist())
    body = head + q.tobytes()
    body += b"\0" * ((-len(body)) % 4) + idx.tobytes()
    return gzip.compress(body, 6, mtime=0)


def _simplify_and_pack(verts: np.ndarray, faces: np.ndarray) -> bytes | None:
    if len(faces) == 0 or len(verts) < 3:
        return None
    if len(faces) > PREVIEW_MAX_TRIS:
        import fast_simplification

        verts, faces = fast_simplification.simplify(verts, faces, target_reduction=1 - PREVIEW_MAX_TRIS / len(faces))
    return _pack(np.asarray(verts, dtype=np.float32), np.asarray(faces))


def build_preview(fmt: str, data: bytes) -> bytes | None:
    """STL·3MF 로 미리보기 메시(NFM1, gzip)를 만든다. 못 만들면 None (올리기는 막지 않고 화면은 원본을 쓴다)."""
    if fmt not in ("stl", "3mf"):
        return None
    with _SLOT:
        try:
            got = _binary_stl(data) if fmt == "stl" else None
            if got is None:
                got = _with_trimesh(fmt, data)
            return _simplify_and_pack(*got) if got is not None else None
        except Exception:  # noqa: BLE001 - 미리보기는 덤이다. 실패해도 원본으로 보여 준다
            log.warning("3D 미리보기 메시를 만들지 못했습니다 (%s)", fmt, exc_info=True)
            return None


def measure_and_preview(fmt: str, data: bytes) -> tuple[list[float] | None, bytes | None]:
    """올리기를 마칠 때: 외곽 크기와 미리보기 메시를 함께 (3MF 는 한 번만 읽는다. 무거운 해석을 두 번 하지 않게)"""
    if fmt == "stl":
        dims = mesh_dims(fmt, data)
        return dims, build_preview(fmt, data) if dims is not None else None
    if fmt != "3mf":
        return None, None
    with _SLOT:
        try:
            mesh = load_3mf(data)
            if mesh is None:
                return None, None
            dims = mesh_extents(mesh)
            if dims is None:
                return None, None
            verts = np.asarray(mesh.vertices, dtype=np.float32)
            faces = np.asarray(mesh.faces, dtype=np.int32)
            del mesh
            return dims, _simplify_and_pack(verts, faces)
        except Exception:  # noqa: BLE001 - 크기·미리보기는 덤이다. 올리기는 막지 않는다
            log.warning("3MF 크기·미리보기를 만들지 못했습니다", exc_info=True)
            return None, None


def read_preview(blob: bytes) -> tuple[np.ndarray, np.ndarray]:
    """NFM1 을 다시 읽는다 (테스트·확인용): 꼭짓점 좌표(mm), 삼각형 인덱스"""
    body = gzip.decompress(blob)
    if body[:4] != b"NFM1":
        raise ValueError("NFM1 이 아니에요")
    flags, nv, nt, *rest = struct.unpack_from("<III3f3f", body, 4)
    origin, scale = np.array(rest[:3]), np.array(rest[3:])
    q = np.frombuffer(body, dtype="<u2", count=nv * 3, offset=40).reshape(-1, 3)
    off = 40 + nv * 6
    off += (-off) % 4
    idx = np.frombuffer(body, dtype="<u2" if flags & 1 else "<u4", count=nt * 3, offset=off).reshape(-1, 3)
    return origin + q * scale, idx
