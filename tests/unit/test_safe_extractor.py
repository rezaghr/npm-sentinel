import io
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.core.exceptions import (
    TarballExtractionLimitExceededError,
    TarballMalformedArchiveError,
    TarballUnsafeMemberError,
)
from app.infrastructure.scanner.extractor import SafeExtractor


def _fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "tarballs" / name


def _build_traversal_tarball(path: Path) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        payload = b"evil"
        info = tarfile.TarInfo(name="../outside.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def _build_unsafe_symlink_tarball(path: Path) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        symlink_info = tarfile.TarInfo(name="package/bad_link")
        symlink_info.type = tarfile.SYMTYPE
        symlink_info.linkname = "../../outside.txt"
        archive.addfile(symlink_info)


def _build_tarball_with_files(path: Path, count: int) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for index in range(count):
            payload = b"ok"
            info = tarfile.TarInfo(name=f"package/file-{index}.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _build_special_file_tarball(path: Path) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        info = tarfile.TarInfo(name="package/fifo")
        info.type = tarfile.FIFOTYPE
        archive.addfile(info)


def test_extract_valid_tarball_success() -> None:
    extractor = SafeExtractor()

    with TemporaryDirectory() as temp_dir:
        output = extractor.extract(
            archive_path=_fixture_path("minimal_valid.tgz"),
            destination_dir=Path(temp_dir) / "extract",
        )
        package_json = output / "package" / "package.json"
        assert package_json.exists()
        assert "\"minimal\"" in package_json.read_text(encoding="utf-8")


def test_extract_rejects_path_traversal_member() -> None:
    extractor = SafeExtractor()

    with TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "traversal.tgz"
        _build_traversal_tarball(archive_path)

        with pytest.raises(TarballUnsafeMemberError):
            extractor.extract(archive_path=archive_path, destination_dir=Path(temp_dir) / "extract")


def test_extract_rejects_unsafe_symlink_target() -> None:
    extractor = SafeExtractor()

    with TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "symlink_escape.tgz"
        _build_unsafe_symlink_tarball(archive_path)

        with pytest.raises(TarballUnsafeMemberError):
            extractor.extract(archive_path=archive_path, destination_dir=Path(temp_dir) / "extract")


def test_extract_rejects_too_many_members() -> None:
    extractor = SafeExtractor(max_members=1)

    with TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "too_many.tgz"
        _build_tarball_with_files(archive_path, count=2)

        with pytest.raises(TarballExtractionLimitExceededError):
            extractor.extract(archive_path=archive_path, destination_dir=Path(temp_dir) / "extract")


def test_extract_rejects_special_members() -> None:
    extractor = SafeExtractor()

    with TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "special.tgz"
        _build_special_file_tarball(archive_path)

        with pytest.raises(TarballUnsafeMemberError):
            extractor.extract(archive_path=archive_path, destination_dir=Path(temp_dir) / "extract")


def test_extract_rejects_excess_uncompressed_size() -> None:
    extractor = SafeExtractor(max_total_uncompressed_bytes=1)

    with TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "large.tgz"
        _build_tarball_with_files(archive_path, count=1)

        with pytest.raises(TarballExtractionLimitExceededError):
            extractor.extract(archive_path=archive_path, destination_dir=Path(temp_dir) / "extract")


def test_extract_raises_for_malformed_tarball() -> None:
    extractor = SafeExtractor()

    with TemporaryDirectory() as temp_dir:
        with pytest.raises(TarballMalformedArchiveError):
            extractor.extract(
                archive_path=_fixture_path("malformed.tgz"),
                destination_dir=Path(temp_dir) / "extract",
            )


def test_temporary_directory_cleanup_after_context_exit() -> None:
    extractor = SafeExtractor()

    temp_root: Path | None = None
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        extractor.extract(
            archive_path=_fixture_path("minimal_valid.tgz"),
            destination_dir=temp_root / "extract",
        )
        assert (temp_root / "extract" / "package" / "package.json").exists()

    assert temp_root is not None
    assert not temp_root.exists()
