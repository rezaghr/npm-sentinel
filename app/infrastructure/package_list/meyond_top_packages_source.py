import re
from urllib.parse import unquote

import httpx

from app.application.ports.package_list_source import PackageListSource
from app.core.exceptions import (
    PackageListSourceError,
    PackageListSourceMalformedContentError,
    PackageListSourceTimeoutError,
)

_NPM_PACKAGE_LINK_PATTERN = re.compile(
    r"(?m)^\s*\d+\.\s+\[[^\]]+\]\(https?://www\.npmjs\.(?:org|com)/package/([^)\s]+)\)"
)


class MeyondTopPackagesSource(PackageListSource):
    def __init__(
        self,
        source_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._source_url = source_url
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def load_package_names(self, limit: int | None = None) -> list[str]:
        content = await self._fetch_content()
        package_names = self._parse_package_names(content)

        if limit is None:
            return package_names
        return package_names[:limit]

    async def _fetch_content(self) -> str:
        try:
            if self._http_client is not None:
                response = await self._http_client.get(self._source_url, timeout=self._timeout_seconds)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(self._source_url)
        except httpx.TimeoutException as exc:
            raise PackageListSourceTimeoutError("top package source request timed out") from exc
        except httpx.HTTPError as exc:
            raise PackageListSourceError("top package source request failed") from exc

        if response.status_code >= 400:
            raise PackageListSourceError(
                f"top package source returned HTTP {response.status_code}"
            )

        return response.text

    def _parse_package_names(self, content: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()

        for match in _NPM_PACKAGE_LINK_PATTERN.finditer(content):
            name = unquote(match.group(1)).strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)

        if not names:
            raise PackageListSourceMalformedContentError("no package names found in source content")

        return names
