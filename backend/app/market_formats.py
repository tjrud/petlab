"""둥지마당 파일 형식: 확장자와 실제 내용이 맞는지 확인한다 (확장자만 바꾼 다른 파일을 막는다)."""

from __future__ import annotations

import io
import zipfile

MODEL_FORMATS = {"skp", "3mf", "stl"}
IMAGE_FORMATS = {"png", "jpg", "webp"}
EXT_ALIASES = {"jpeg": "jpg"}

MAX_MODEL_BYTES = 50 * 1024 * 1024
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
