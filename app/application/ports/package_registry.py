from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class PackageVersionMetadata:
    package_name: str
    version: str
    published_at: datetime | None
    tarball_url: str
    integrity: str | None
    unpacked_size: int | None
    file_count: int | None
    package_json: dict[str, Any]
    dependencies: dict[str, Any]
    scripts: dict[str, Any]


@dataclass(frozen=True)
class PackageRegistryMetadata:
    package_name: str
    latest_version: PackageVersionMetadata
    previous_version: PackageVersionMetadata | None


class PackageRegistry(Protocol):
    async def fetch_metadata(self, package_name: str) -> PackageRegistryMetadata:
        ...
