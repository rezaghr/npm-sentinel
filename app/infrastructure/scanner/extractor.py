import tarfile
from pathlib import Path

from app.core.exceptions import (
    TarballExtractionLimitExceededError,
    TarballMalformedArchiveError,
    TarballUnsafeMemberError,
)


class SafeExtractor:
    def __init__(
        self,
        *,
        max_members: int = 10_000,
        max_total_uncompressed_bytes: int = 100_000_000,
        max_file_bytes: int = 10_000_000,
        max_path_depth: int = 20,
    ) -> None:
        self._max_members = max_members
        self._max_total_uncompressed_bytes = max_total_uncompressed_bytes
        self._max_file_bytes = max_file_bytes
        self._max_path_depth = max_path_depth

    def extract(self, archive_path: Path, destination_dir: Path) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_root = destination_dir.resolve()

        try:
            with tarfile.open(archive_path, mode="r:gz") as archive:
                members = archive.getmembers()
                self._validate_archive(members=members, destination_root=destination_root)
                for member in members:
                    archive.extract(member, path=destination_root)
        except (TarballExtractionLimitExceededError, TarballUnsafeMemberError):
            raise
        except (tarfile.TarError, OSError) as exc:
            raise TarballMalformedArchiveError(f"invalid tarball archive: {archive_path}") from exc

        return destination_root

    def _validate_archive(self, *, members: list[tarfile.TarInfo], destination_root: Path) -> None:
        if len(members) > self._max_members:
            raise TarballExtractionLimitExceededError(
                f"archive has {len(members)} members; limit is {self._max_members}"
            )

        total_uncompressed_bytes = 0
        for member in members:
            self._validate_member(member=member, destination_root=destination_root)
            if member.isfile():
                total_uncompressed_bytes += member.size
                if total_uncompressed_bytes > self._max_total_uncompressed_bytes:
                    raise TarballExtractionLimitExceededError(
                        "archive uncompressed size exceeds "
                        f"{self._max_total_uncompressed_bytes} bytes"
                    )

    def _validate_member(self, *, member: tarfile.TarInfo, destination_root: Path) -> None:
        member_path = Path(member.name)
        if not member.name or member.name in {".", "./"}:
            raise TarballUnsafeMemberError("empty archive path is not allowed")
        if member_path.is_absolute():
            raise TarballUnsafeMemberError(f"absolute archive path is not allowed: {member.name}")
        if self._path_depth(member_path) > self._max_path_depth:
            raise TarballExtractionLimitExceededError(
                f"archive path depth exceeds {self._max_path_depth}: {member.name}"
            )

        resolved_member_path = (destination_root / member_path).resolve()
        self._ensure_within_destination(
            candidate=resolved_member_path,
            destination_root=destination_root,
            member_name=member.name,
        )

        if member.isdev() or member.isfifo():
            raise TarballUnsafeMemberError(f"special archive member is not allowed: {member.name}")
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise TarballUnsafeMemberError(f"unsupported archive member type: {member.name}")
        if member.isfile() and member.size > self._max_file_bytes:
            raise TarballExtractionLimitExceededError(
                f"archive member exceeds {self._max_file_bytes} bytes: {member.name}"
            )

        if member.issym() or member.islnk():
            link_target = Path(member.linkname)
            if link_target.is_absolute():
                raise TarballUnsafeMemberError(
                    f"absolute link target is not allowed: {member.name} -> {member.linkname}"
                )

            resolved_link_target = (resolved_member_path.parent / link_target).resolve()
            self._ensure_within_destination(
                candidate=resolved_link_target,
                destination_root=destination_root,
                member_name=f"{member.name} -> {member.linkname}",
            )

    @staticmethod
    def _ensure_within_destination(*, candidate: Path, destination_root: Path, member_name: str) -> None:
        try:
            candidate.relative_to(destination_root)
        except ValueError as exc:
            raise TarballUnsafeMemberError(
                f"archive member escapes destination: {member_name}"
            ) from exc

    @staticmethod
    def _path_depth(path: Path) -> int:
        return len([part for part in path.parts if part not in {"", "."}])
