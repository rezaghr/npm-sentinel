from pathlib import Path
import base64
import hashlib

import httpx
import pytest

from app.core.exceptions import (
    TarballDownloadError,
    TarballIntegrityError,
    TarballDownloadTimeoutError,
    TarballSizeLimitExceededError,
)
from app.infrastructure.npm.tarball_downloader import TarballDownloader


def _fixture_bytes(name: str) -> bytes:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "tarballs" / name
    return path.read_bytes()


@pytest.mark.anyio
async def test_download_stream_writes_tarball_file(tmp_path: Path) -> None:
    payload = _fixture_bytes("minimal_valid.tgz")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        downloader = TarballDownloader(timeout_seconds=5.0, max_bytes=10_000_000, http_client=http_client)
        tarball_path = await downloader.download(
            tarball_url="https://registry.npmjs.org/lodash/-/lodash-1.0.0.tgz",
            destination_dir=tmp_path,
        )

    assert tarball_path.exists()
    assert tarball_path.name == "lodash-1.0.0.tgz"
    assert tarball_path.read_bytes() == payload


@pytest.mark.anyio
async def test_download_verifies_integrity(tmp_path: Path) -> None:
    payload = _fixture_bytes("minimal_valid.tgz")
    digest = base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        downloader = TarballDownloader(timeout_seconds=5.0, max_bytes=10_000_000, http_client=http_client)
        tarball_path = await downloader.download(
            tarball_url="https://registry.npmjs.org/lodash/-/lodash-1.0.0.tgz",
            destination_dir=tmp_path,
            integrity=f"sha512-{digest}",
        )

    assert tarball_path.exists()


@pytest.mark.anyio
async def test_download_rejects_integrity_mismatch(tmp_path: Path) -> None:
    payload = _fixture_bytes("minimal_valid.tgz")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        downloader = TarballDownloader(timeout_seconds=5.0, max_bytes=10_000_000, http_client=http_client)
        with pytest.raises(TarballIntegrityError):
            await downloader.download(
                tarball_url="https://registry.npmjs.org/lodash/-/lodash-1.0.0.tgz",
                destination_dir=tmp_path,
                integrity="sha512-bm90LXRoZS1kaWdlc3Q=",
            )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_download_raises_timeout_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        downloader = TarballDownloader(timeout_seconds=5.0, max_bytes=10_000_000, http_client=http_client)
        with pytest.raises(TarballDownloadTimeoutError) as exc_info:
            await downloader.download(
                tarball_url="https://registry.npmjs.org/lodash/-/lodash-1.0.0.tgz?token=secret",
                destination_dir=tmp_path,
            )
    assert "token=secret" not in str(exc_info.value)


@pytest.mark.anyio
async def test_download_raises_size_limit_exceeded(tmp_path: Path) -> None:
    payload = _fixture_bytes("minimal_valid.tgz")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        downloader = TarballDownloader(timeout_seconds=5.0, max_bytes=10, http_client=http_client)
        with pytest.raises(TarballSizeLimitExceededError):
            await downloader.download(
                tarball_url="https://registry.npmjs.org/lodash/-/lodash-1.0.0.tgz",
                destination_dir=tmp_path,
            )


@pytest.mark.anyio
async def test_download_rejects_non_http_url(tmp_path: Path) -> None:
    downloader = TarballDownloader(timeout_seconds=5.0, max_bytes=10_000_000)

    with pytest.raises(TarballDownloadError):
        await downloader.download("file:///etc/passwd", tmp_path)
