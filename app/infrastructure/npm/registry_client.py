from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.application.ports.package_registry import (
    PackageRegistry,
    PackageRegistryMetadata,
    PackageVersionMetadata,
)
from app.core.exceptions import (
    NpmPackageNotFoundError,
    NpmRegistryError,
    NpmRegistryMalformedResponseError,
    NpmRegistryTimeoutError,
)


class NpmRegistryClient(PackageRegistry):
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def fetch_metadata(self, package_name: str) -> PackageRegistryMetadata:
        payload = await self._fetch_package_payload(package_name)

        if not isinstance(payload, dict):
            raise NpmRegistryMalformedResponseError("registry payload must be an object")

        versions = payload.get("versions")
        dist_tags = payload.get("dist-tags")
        time_map = payload.get("time")

        if not isinstance(versions, dict) or not isinstance(dist_tags, dict) or not isinstance(time_map, dict):
            raise NpmRegistryMalformedResponseError("missing required versions, dist-tags, or time")

        latest_version = dist_tags.get("latest")
        if not isinstance(latest_version, str) or latest_version not in versions:
            raise NpmRegistryMalformedResponseError("latest version is missing from versions map")

        latest_metadata = self._build_version_metadata(
            package_name=package_name,
            version=latest_version,
            versions=versions,
            time_map=time_map,
        )

        previous_version_name = self._resolve_previous_version_name(
            latest_version=latest_version,
            versions=versions,
            time_map=time_map,
        )

        previous_metadata = (
            self._build_version_metadata(
                package_name=package_name,
                version=previous_version_name,
                versions=versions,
                time_map=time_map,
            )
            if previous_version_name is not None
            else None
        )

        return PackageRegistryMetadata(
            package_name=package_name,
            latest_version=latest_metadata,
            previous_version=previous_metadata,
        )

    async def _fetch_package_payload(self, package_name: str) -> dict[str, Any]:
        encoded_name = quote(package_name, safe="@")
        url = f"{self._base_url}/{encoded_name}"

        try:
            if self._http_client is not None:
                response = await self._http_client.get(url, timeout=self._timeout_seconds)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise NpmRegistryTimeoutError(f"registry request timed out for package: {package_name}") from exc
        except httpx.HTTPError as exc:
            raise NpmRegistryError(f"registry request failed for package: {package_name}") from exc

        if response.status_code == 404:
            raise NpmPackageNotFoundError(f"package not found: {package_name}")
        if response.status_code >= 400:
            raise NpmRegistryError(
                f"registry returned HTTP {response.status_code} for package: {package_name}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise NpmRegistryMalformedResponseError("registry returned non-JSON response") from exc

        if not isinstance(payload, dict):
            raise NpmRegistryMalformedResponseError("registry payload must be an object")
        return payload

    def _resolve_previous_version_name(
        self,
        *,
        latest_version: str,
        versions: dict[str, Any],
        time_map: dict[str, Any],
    ) -> str | None:
        latest_published_at = self._parse_version_publish_time(version=latest_version, time_map=time_map)
        best_candidate: tuple[str, datetime] | None = None

        for version_name in versions:
            if version_name == latest_version:
                continue
            published_at = self._parse_version_publish_time(version=version_name, time_map=time_map)
            if published_at >= latest_published_at:
                continue
            if best_candidate is None or published_at > best_candidate[1]:
                best_candidate = (version_name, published_at)

        if best_candidate is None:
            return None
        return best_candidate[0]

    def _build_version_metadata(
        self,
        *,
        package_name: str,
        version: str,
        versions: dict[str, Any],
        time_map: dict[str, Any],
    ) -> PackageVersionMetadata:
        payload = versions.get(version)
        if not isinstance(payload, dict):
            raise NpmRegistryMalformedResponseError(f"missing payload for version: {version}")

        dist = payload.get("dist")
        if not isinstance(dist, dict):
            raise NpmRegistryMalformedResponseError(f"missing dist payload for version: {version}")

        tarball_url = dist.get("tarball")
        if not isinstance(tarball_url, str) or not tarball_url:
            raise NpmRegistryMalformedResponseError(f"missing tarball url for version: {version}")

        dependencies = payload.get("dependencies", {})
        if not isinstance(dependencies, dict):
            raise NpmRegistryMalformedResponseError(f"dependencies must be an object for version: {version}")

        scripts = payload.get("scripts", {})
        if not isinstance(scripts, dict):
            raise NpmRegistryMalformedResponseError(f"scripts must be an object for version: {version}")

        return PackageVersionMetadata(
            package_name=package_name,
            version=version,
            published_at=self._parse_version_publish_time(version=version, time_map=time_map),
            tarball_url=tarball_url,
            integrity=self._as_optional_str(dist.get("integrity")),
            unpacked_size=self._as_optional_int(dist.get("unpackedSize"), field_name="unpackedSize"),
            file_count=self._as_optional_int(dist.get("fileCount"), field_name="fileCount"),
            package_json=dict(payload),
            dependencies=dict(dependencies),
            scripts=dict(scripts),
        )

    def _parse_version_publish_time(self, *, version: str, time_map: dict[str, Any]) -> datetime:
        value = time_map.get(version)
        if not isinstance(value, str):
            raise NpmRegistryMalformedResponseError(f"missing publish timestamp for version: {version}")

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise NpmRegistryMalformedResponseError(
                f"invalid publish timestamp for version: {version}"
            ) from exc

    @staticmethod
    def _as_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raise NpmRegistryMalformedResponseError("expected string field in dist payload")

    @staticmethod
    def _as_optional_int(value: Any, *, field_name: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        raise NpmRegistryMalformedResponseError(f"expected integer for {field_name}")
