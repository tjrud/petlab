"""둥지마당 파일 저장소.

- Vercel Blob (BLOB_READ_WRITE_TOKEN 이 있을 때): 공개 주소로 바로 내려받는다 (배포 플랫폼의 응답 크기 한도를 피한다)
- 로컬 디스크 (개발·테스트): 백엔드가 파일을 직접 돌려준다
배포 환경에서 토큰이 없으면 저장소가 없다고 보고 올리기를 막는다 (인스턴스마다 디스크가 사라지므로).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,250}$")


@dataclass(frozen=True)
class Stored:
    key: str
    url: str | None  # 공개 주소 (Blob). 로컬이면 None


class StorageError(Exception):
    pass


class LocalStorage:
    kind = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key) or ".." in key:
            raise StorageError("잘못된 저장 키")
        return self.root / key

    def put(self, key: str, data: bytes, content_type: str) -> Stored:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return Stored(key=key, url=None)

    def path(self, key: str) -> Path:
        return self._path(key)

    def delete(self, stored: list[Stored]) -> None:
        for s in stored:
            try:
                self._path(s.key).unlink(missing_ok=True)
            except (OSError, StorageError):
                log.warning("로컬 파일을 지우지 못했습니다: %s", s.key)


class BlobStorage:
    """Vercel Blob REST API (공식 SDK 와 같은 요청: PUT ?pathname=, POST /delete)."""

    kind = "blob"

    def __init__(self, token: str, api_url: str) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}", "x-api-version": "12", **(extra or {})}

    def put(self, key: str, data: bytes, content_type: str) -> Stored:
        if not _KEY_RE.fullmatch(key):
            raise StorageError("잘못된 저장 키")
        headers = self._headers({
            "x-vercel-blob-access": "public",
            "x-add-random-suffix": "0",  # 키에 이미 무작위 ID 가 들어 있다
            "x-content-type": content_type,
            "x-cache-control-max-age": str(60 * 60 * 24 * 365),
        })
        try:
            r = httpx.put(f"{self.api_url}/", params={"pathname": key}, content=data, headers=headers, timeout=120)
        except httpx.HTTPError as e:
            raise StorageError(f"Blob 저장 요청 실패: {type(e).__name__}") from e
        if r.status_code >= 300:
            raise StorageError(f"Blob 저장 실패 (HTTP {r.status_code})")
        url = r.json().get("url")
        if not isinstance(url, str) or not _is_blob_url(url):
            raise StorageError("Blob 응답에 공개 주소가 없습니다")
        return Stored(key=key, url=url)

    def delete(self, stored: list[Stored]) -> None:
        urls = [s.url for s in stored if s.url]
        if not urls:
            return
        try:
            r = httpx.post(f"{self.api_url}/delete", json={"urls": urls}, headers=self._headers(), timeout=30)
            if r.status_code >= 300:
                log.warning("Blob 파일을 지우지 못했습니다 (HTTP %s)", r.status_code)
        except httpx.HTTPError:
            log.warning("Blob 삭제 요청이 실패했습니다")


def _is_blob_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").endswith(".blob.vercel-storage.com")


Storage = LocalStorage | BlobStorage


def make_storage(settings: Settings) -> Storage | None:
    """설정에 맞는 저장소. 배포 환경인데 Blob 토큰이 없으면 None (올리기를 막는다)."""
    if settings.blob_read_write_token:
        return BlobStorage(settings.blob_read_write_token, settings.blob_api_url)
    if settings.deployed:
        return None
    return LocalStorage(settings.market_storage_dir)
