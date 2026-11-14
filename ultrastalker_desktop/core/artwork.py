from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from ultrastalker_desktop.core.http import make_session, request_timeout
from ultrastalker_desktop.runtime import local_data_dir


class ArtworkError(RuntimeError):
    pass


class ArtworkCache:
    """Bounded binary artwork cache without persisting source URLs.

    Cache filenames are SHA256(url), so signed provider URLs/account identifiers
    are never written verbatim to disk. The cache accepts only common raster
    image formats and caps each download to avoid turning artwork into an
    accidental arbitrary-file sink.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        http=None,
        *,
        ttl: int = 7 * 24 * 60 * 60,
        max_download_bytes: int = 6 * 1024 * 1024,
        max_files: int = 500,
        max_total_bytes: int = 256 * 1024 * 1024,
    ):
        self.root = Path(cache_dir or (local_data_dir() / "artwork"))
        self.http = http or make_session(retries=1)
        self.ttl = max(60, int(ttl))
        self.max_download_bytes = max(256 * 1024, int(max_download_bytes))
        self.max_files = max(25, int(max_files))
        self.max_total_bytes = max(self.max_download_bytes, int(max_total_bytes))
        # Different artwork URLs must not block one another during network I/O.
        # A small striped lock set deduplicates same-URL downloads without
        # creating an unbounded lock dictionary for every poster ever seen.
        self._locks = [threading.Lock() for _ in range(32)]
        self._prune_lock = threading.Lock()

    @staticmethod
    def _valid_url(url: str) -> bool:
        try:
            parts = urlsplit(str(url or "").strip())
        except ValueError:
            return False
        return parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)

    @staticmethod
    def _looks_like_image(data: bytes) -> bool:
        if len(data) < 8:
            return False
        return bool(ArtworkCache.mime_type(data))

    @staticmethod
    def mime_type(data: bytes) -> str:
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"BM"):
            return "image/bmp"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
            return "image/avif"
        return ""

    def _url_lock(self, url: str):
        digest = hashlib.sha256(url.encode("utf-8", "surrogatepass")).digest()
        return self._locks[digest[0] % len(self._locks)]

    def _path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8", "surrogatepass")).hexdigest()
        return self.root / f"{digest}.img"

    def _read_fresh(self, path: Path) -> bytes | None:
        try:
            stat = path.stat()
            if stat.st_size <= 0 or time.time() - stat.st_mtime > self.ttl:
                return None
            data = path.read_bytes()
            return data if self._looks_like_image(data) else None
        except OSError:
            return None

    def _download(self, url: str, headers: dict | None = None) -> bytes:
        options = {"timeout": request_timeout(8, 4), "stream": True}
        if headers:
            options.update(headers=headers, allow_redirects=False)
        response = self.http.get(url, **options)
        try:
            response.raise_for_status()
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if content_type and not (content_type.startswith("image/") or content_type.split(";")[0] == "application/octet-stream"):
                raise ArtworkError("Artwork response was not an image")

            data = bytearray()
            iterator = getattr(response, "iter_content", None)
            chunks = iterator(64 * 1024) if callable(iterator) else (getattr(response, "content", b""),)
            for chunk in chunks:
                data.extend(chunk)
                if len(data) > self.max_download_bytes:
                    raise ArtworkError("Artwork image exceeded size limit")

            payload = bytes(data)
            if not self._looks_like_image(payload):
                raise ArtworkError("Artwork response had an unsupported image format")
            return payload
        finally:
            close = getattr(response, "close", None)
            if close:
                close()

    def _write_atomic(self, path: Path, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def _prune(self) -> None:
        try:
            if not self.root.exists():
                return
            now = time.time()
            # A hard power-off can leave an atomic-write temp behind. It never
            # participates in normal reads, so remove stale temp files safely.
            for tmp in self.root.glob("*.tmp"):
                try:
                    if tmp.is_file() and now - tmp.stat().st_mtime > 60 * 60:
                        tmp.unlink()
                except OSError:
                    continue

            entries = []
            for path in self.root.glob("*.img"):
                try:
                    stat = path.stat()
                    if not path.is_file():
                        continue
                    if now - stat.st_mtime > self.ttl:
                        path.unlink()
                        continue
                    entries.append([path, stat.st_mtime, stat.st_size])
                except OSError:
                    continue

            # Oldest artwork is evicted first until both independent limits are
            # satisfied. This prevents a provider serving a few huge images from
            # consuming gigabytes even though the file-count limit is respected.
            entries.sort(key=lambda row: row[1])
            total = sum(row[2] for row in entries)
            while entries and (len(entries) > self.max_files or total > self.max_total_bytes):
                path, _, size = entries.pop(0)
                try:
                    path.unlink()
                    total -= size
                except OSError:
                    continue
        except OSError:
            pass

    def fetch(self, url: str, *, headers: dict | None = None, namespace: str = "") -> bytes | None:
        url = str(url or "").strip()
        if not self._valid_url(url):
            return None
        key = f"{namespace}\n{url}" if namespace else url
        path = self._path(key)
        with self._url_lock(key):
            cached = self._read_fresh(path)
            if cached is not None:
                return cached
            try:
                data = self._download(url, headers) if headers else self._download(url)
            except Exception:
                return None
            try:
                self._write_atomic(path, data)
            except OSError:
                return data
        # Pruning never holds the per-URL lock, so one slow directory scan cannot
        # delay another image download. Concurrent prunes are serialized.
        with self._prune_lock:
            self._prune()
        return data
