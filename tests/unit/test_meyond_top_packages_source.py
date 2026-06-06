from pathlib import Path

import httpx
import pytest

from app.core.exceptions import PackageListSourceMalformedContentError, PackageListSourceTimeoutError
from app.infrastructure.package_list.meyond_top_packages_source import MeyondTopPackagesSource


def _fixture_text(name: str) -> str:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "package_list" / name
    return path.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_load_package_names_parses_dedupes_and_decodes() -> None:
    content = _fixture_text("meyond_readme_sample.md")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, text=content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        source = MeyondTopPackagesSource(
            source_url="https://example.test/list.md",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        package_names = await source.load_package_names()

    assert package_names == ["lodash", "react", "@types/node", "@babel/core"]


@pytest.mark.anyio
async def test_load_package_names_applies_limit() -> None:
    content = _fixture_text("meyond_readme_sample.md")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, text=content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        source = MeyondTopPackagesSource(
            source_url="https://example.test/list.md",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        package_names = await source.load_package_names(limit=2)

    assert package_names == ["lodash", "react"]


@pytest.mark.anyio
async def test_load_package_names_raises_malformed_content_for_invalid_markdown() -> None:
    content = _fixture_text("meyond_readme_invalid.md")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, text=content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        source = MeyondTopPackagesSource(
            source_url="https://example.test/list.md",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        with pytest.raises(PackageListSourceMalformedContentError):
            await source.load_package_names()


@pytest.mark.anyio
async def test_load_package_names_raises_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        source = MeyondTopPackagesSource(
            source_url="https://example.test/list.md",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        with pytest.raises(PackageListSourceTimeoutError):
            await source.load_package_names()


@pytest.mark.anyio
async def test_load_package_names_ignores_non_ranked_npm_links() -> None:
    content = """# Top packages

[project-link](https://www.npmjs.org/package/top-packages)
0. [lodash](https://www.npmjs.org/package/lodash)
1. [react](https://www.npmjs.org/package/react)
"""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, text=content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        source = MeyondTopPackagesSource(
            source_url="https://example.test/list.md",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        package_names = await source.load_package_names()

    assert package_names == ["lodash", "react"]
