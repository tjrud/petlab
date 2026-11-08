"""탐색 파일 형식: 확장자와 실제 내용이 맞는지 확인한다 (확장자만 바꾼 다른 파일을 막는다)."""

from __future__ import annotations

import io
import re
import zipfile

import numpy as np

MODEL_FORMATS = {"skp", "3mf", "stl"}
IMAGE_FORMATS = {"png", "jpg", "webp"}
EXT_ALIASES = {"jpeg": "jpg"}

MESH_FORMATS = {"stl", "3mf"}  # 가상 케이지에서 3D 로 보여 줄 수 있는 형식
FILE_ASSET_PREFIX = "file_"  # 가상 케이지 배치안에서 내가 올린 파일을 가리키는 에셋 키: file_<파일 ID>

MAX_MODEL_BYTES = 50 * 1024 * 1024
# 3MF 는 zip 이라 작은 파일이 크게 풀릴 수 있다 (압축 폭탄). 풀린 크기가 이보다 크면 외곽 크기를 재지 않는다
MAX_3MF_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024

CONTENT_TYPES = {
    "skp": "application/vnd.sketchup.skp",
    "3mf": "model/3mf",
    "stl": "model/stl",
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


def format_of(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXT_ALIASES.get(ext, ext) or None


def _is_skp(d: bytes) -> bool:
    # SketchUp 파일은 UTF-16LE 로 "SketchUp Model" 을 적고 시작한다
    return d[:4] == b"\xff\xfe\xff\x0e" and "SketchUp Model".encode("utf-16le") in d[:64]


def _is_3mf(d: bytes) -> bool:
    if d[:4] != b"PK\x03\x04":
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(d)) as z:
            names = {n.lower() for n in z.namelist()}
    except zipfile.BadZipFile:
        return False
    return "3d/3dmodel.model" in names


def _is_stl(d: bytes) -> bool:
    if len(d) >= 84:
        n = int.from_bytes(d[80:84], "little")
        if 84 + 50 * n == len(d):
            return True  # 바이너리 STL
    head = d[:1024].lstrip().lower()
    return head.startswith(b"solid") and b"facet" in d[:4096].lower()


def _is_png(d: bytes) -> bool:
    return d[:8] == b"\x89PNG\r\n\x1a\n"


def _is_jpg(d: bytes) -> bool:
    return d[:3] == b"\xff\xd8\xff"


def _is_webp(d: bytes) -> bool:
    return d[:4] == b"RIFF" and d[8:12] == b"WEBP"


SNIFF = {"skp": _is_skp, "3mf": _is_3mf, "stl": _is_stl, "png": _is_png, "jpg": _is_jpg, "webp": _is_webp}


def content_matches(fmt: str, data: bytes) -> bool:
    check = SNIFF.get(fmt)
    return bool(check and check(data))


# ── 외곽 크기 (가상 케이지에 실제 크기로 놓기) ──

_STL_RECORD = np.dtype([("normal", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])
_ASCII_VERTEX = re.compile(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", re.IGNORECASE)


def _extents(lo: np.ndarray, hi: np.ndarray) -> list[float] | None:
    ext = hi - lo
    if not np.all(np.isfinite(ext)):
        return None
    out = [float(round(float(v), 2)) for v in ext]
    return out if all(0 < v < 10_000 for v in out) else None


def _stl_dims(d: bytes) -> list[float] | None:
    n = int.from_bytes(d[80:84], "little") if len(d) >= 84 else 0
    if n > 0 and 84 + 50 * n == len(d):  # 바이너리: 꼭짓점을 복사 없이 바로 읽는다
        v = np.frombuffer(d, dtype=_STL_RECORD, count=n, offset=84)["v"].reshape(-1, 3)
        return _extents(v.min(axis=0), v.max(axis=0))
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    batch: list[tuple[bytes, bytes, bytes]] = []
    for m in _ASCII_VERTEX.finditer(d):
        batch.append(m.groups())
        if len(batch) >= 65_536:
            lo, hi = _fold(batch, lo, hi)
            batch = []
    if batch:
        lo, hi = _fold(batch, lo, hi)
    return _extents(lo, hi) if np.all(np.isfinite(lo)) else None


def _fold(batch: list[tuple[bytes, bytes, bytes]], lo: np.ndarray, hi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.array(batch, dtype=float)
    return np.minimum(lo, a.min(axis=0)), np.maximum(hi, a.max(axis=0))


def safe_3mf(d: bytes) -> bool:
    """풀어도 될 3MF 인지 (압축 폭탄 막기). zipfile 은 목록에 적힌 크기 이상으로 풀지 않으므로,
    목록의 합계로 풀린 크기를 미리 알 수 있다"""
    try:
        with zipfile.ZipFile(io.BytesIO(d)) as z:
            return sum(i.file_size for i in z.infolist()) <= MAX_3MF_UNPACKED_BYTES
    except zipfile.BadZipFile:
        return False


def load_3mf(d: bytes):
    """3MF 를 한 메시로 읽는다 (풀린 크기가 크면 None). trimesh 는 무거워 필요할 때만 불러온다"""
    if not safe_3mf(d):
        return None
    import trimesh

    return trimesh.load(io.BytesIO(d), file_type="3mf", force="mesh")


def mesh_extents(mesh) -> list[float] | None:
    lo, hi = np.asarray(mesh.bounds, dtype=float)
    return _extents(lo, hi)


def _3mf_dims(d: bytes) -> list[float] | None:
    mesh = load_3mf(d)
    return mesh_extents(mesh) if mesh is not None else None


def mesh_dims(fmt: str, data: bytes) -> list[float] | None:
    """STL·3MF 외곽 크기 [x, y, z] mm (못 읽거나 너무 크면 None. 올리기 자체는 막지 않는다)."""
    try:
        if fmt == "stl":
            return _stl_dims(data)
        if fmt == "3mf":
            return _3mf_dims(data)
    except Exception:  # noqa: BLE001 - 형식은 이미 확인했고, 크기를 못 읽어도 올리기는 막지 않는다
        return None
    return None
