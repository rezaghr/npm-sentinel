from pathlib import Path
from typing import Protocol

from app.domain.findings import Finding


class TarballDownloader(Protocol):
    async def download(self, tarball_url: str, destination_dir: Path, *, integrity: str | None = None) -> Path:
        ...


class ArchiveExtractor(Protocol):
    def extract(self, archive_path: Path, destination_dir: Path) -> Path:
        ...


class PackageAnalyzer(Protocol):
    def analyze(
        self,
        *,
        latest_root: Path,
        latest_metadata_scripts: dict[str, object],
        latest_size: int | None,
        previous_root: Path | None,
        previous_metadata_scripts: dict[str, object] | None,
        previous_size: int | None,
    ) -> list[Finding]:
        ...
