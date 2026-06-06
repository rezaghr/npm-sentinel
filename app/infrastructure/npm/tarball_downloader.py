import base64
import binascii
import hashlib
import hmac
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.exceptions import (
    TarballDownloadError,
    TarballIntegrityError,
    TarballDownloadTimeoutError,
    TarballSizeLimitExceededError,
)


class TarballDownloader:
    def __init__(
        self,
        timeout_seconds: float,
        max_bytes: int,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._http_client = http_client

    async def download(self, tarball_url: str, destination_dir: Path, *, integrity: str | None = None) -> Path:
        self._validate_url(tarball_url)
        safe_url = self._safe_url(tarball_url)
        destination_dir.mkdir(parents=True, exist_ok=True)
        target_file = destination_dir / self._filename_from_url(tarball_url)
        downloaded_bytes = 0
        integrity_check = self._build_integrity_check(integrity)

        try:
            if self._http_client is not None:
                async with self._http_client.stream("GET", tarball_url, timeout=self._timeout_seconds) as response:
                    await self._write_stream_to_file(response, target_file, downloaded_bytes, integrity_check)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    async with client.stream("GET", tarball_url) as response:
                        await self._write_stream_to_file(response, target_file, downloaded_bytes, integrity_check)
        except httpx.TimeoutException as exc:
            self._remove_if_exists(target_file)
            raise TarballDownloadTimeoutError(f"tarball download timed out for url: {safe_url}") from exc
        except (TarballIntegrityError, TarballSizeLimitExceededError):
            self._remove_if_exists(target_file)
            raise
        except httpx.HTTPError as exc:
            self._remove_if_exists(target_file)
            raise TarballDownloadError(f"tarball download failed for url: {safe_url}") from exc
        except OSError as exc:
            self._remove_if_exists(target_file)
            raise TarballDownloadError(f"failed writing tarball for url: {safe_url}") from exc

        return target_file

    async def _write_stream_to_file(
        self,
        response: httpx.Response,
        target_file: Path,
        downloaded_bytes: int,
        integrity_check: tuple[str, bytes, "hashlib._Hash"] | None,
    ) -> None:
        if response.status_code >= 400:
            raise TarballDownloadError(f"tarball source returned HTTP {response.status_code}")

        with target_file.open("wb") as file_handle:
            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                downloaded_bytes += len(chunk)
                if downloaded_bytes > self._max_bytes:
                    raise TarballSizeLimitExceededError(
                        f"tarball exceeds max size of {self._max_bytes} bytes"
                    )
                if integrity_check is not None:
                    integrity_check[2].update(chunk)
                file_handle.write(chunk)

        if integrity_check is not None:
            algorithm, expected_digest, digest = integrity_check
            actual_digest = digest.digest()
            if not hmac.compare_digest(actual_digest, expected_digest):
                raise TarballIntegrityError(f"tarball {algorithm} integrity check failed")

    @staticmethod
    def _filename_from_url(tarball_url: str) -> str:
        parsed = urlparse(tarball_url)
        filename = Path(parsed.path).name
        if filename:
            return filename
        return "package.tgz"

    @staticmethod
    def _validate_url(tarball_url: str) -> None:
        parsed = urlparse(tarball_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise TarballDownloadError("tarball url must be an absolute http(s) URL")

    @staticmethod
    def _safe_url(tarball_url: str) -> str:
        parsed = urlparse(tarball_url)
        path = parsed.path or "/"
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    @staticmethod
    def _build_integrity_check(integrity: str | None) -> tuple[str, bytes, "hashlib._Hash"] | None:
        if not integrity:
            return None
        for token in integrity.split():
            if "-" not in token:
                continue
            algorithm, encoded_digest = token.split("-", 1)
            if algorithm not in {"sha1", "sha256", "sha384", "sha512"}:
                continue
            try:
                expected_digest = base64.b64decode(encoded_digest, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise TarballIntegrityError("tarball integrity metadata is malformed") from exc
            return algorithm, expected_digest, hashlib.new(algorithm)
        raise TarballIntegrityError("tarball integrity metadata has no supported digest")

    @staticmethod
    def _remove_if_exists(path: Path) -> None:
        if path.exists():
            path.unlink()
