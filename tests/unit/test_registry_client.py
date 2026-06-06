import json
from pathlib import Path

import httpx
import pytest

from app.core.exceptions import (
    NpmPackageNotFoundError,
    NpmRegistryMalformedResponseError,
    NpmRegistryTimeoutError,
)
from app.infrastructure.npm.registry_client import NpmRegistryClient


def _fixture_json(name: str) -> dict:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "npm" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.anyio
async def test_fetch_metadata_parses_latest_and_previous_by_publish_time() -> None:
    payload = _fixture_json("registry_weird_versions.json")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NpmRegistryClient(
            base_url="https://registry.npmjs.org",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        metadata = await client.fetch_metadata("example-pkg")

    assert metadata.package_name == "example-pkg"
    assert metadata.latest_version.version == "1.0.1-beta"
    assert metadata.previous_version is not None
    assert metadata.previous_version.version == "1.0.0"
    assert metadata.latest_version.dependencies == {"chalk": "^5.1.0", "debug": "^4.3.0"}
    assert metadata.latest_version.scripts == {"build": "tsc"}
    assert metadata.latest_version.tarball_url.endswith("1.0.1-beta.tgz")


@pytest.mark.anyio
async def test_fetch_metadata_returns_none_previous_when_single_version() -> None:
    payload = _fixture_json("registry_single_version.json")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NpmRegistryClient(
            base_url="https://registry.npmjs.org",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        metadata = await client.fetch_metadata("single-version-package")

    assert metadata.latest_version.version == "1.0.0"
    assert metadata.previous_version is None


@pytest.mark.anyio
async def test_fetch_metadata_raises_not_found_for_missing_package() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NpmRegistryClient(
            base_url="https://registry.npmjs.org",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        with pytest.raises(NpmPackageNotFoundError):
            await client.fetch_metadata("does-not-exist")


@pytest.mark.anyio
async def test_fetch_metadata_raises_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NpmRegistryClient(
            base_url="https://registry.npmjs.org",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        with pytest.raises(NpmRegistryTimeoutError):
            await client.fetch_metadata("lodash")


@pytest.mark.anyio
async def test_fetch_metadata_raises_malformed_response_for_bad_time_map() -> None:
    payload = _fixture_json("registry_malformed_time.json")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NpmRegistryClient(
            base_url="https://registry.npmjs.org",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        with pytest.raises(NpmRegistryMalformedResponseError):
            await client.fetch_metadata("broken-package")


@pytest.mark.anyio
async def test_fetch_metadata_encodes_scoped_package_path() -> None:
    payload = _fixture_json("registry_single_version.json")
    captured_raw_path = {"value": b""}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_raw_path["value"] = request.url.raw_path
        return httpx.Response(status_code=200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = NpmRegistryClient(
            base_url="https://registry.npmjs.org",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        await client.fetch_metadata("@babel/core")

    assert captured_raw_path["value"] == b"/@babel%2Fcore"
