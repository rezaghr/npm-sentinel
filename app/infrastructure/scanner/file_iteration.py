from collections.abc import Iterator
from pathlib import Path

from app.core.exceptions import ScannerLimitExceededError


def iter_regular_files(root: Path, *, max_files: int = 10_000) -> Iterator[Path]:
    seen = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        seen += 1
        if seen > max_files:
            raise ScannerLimitExceededError(f"package file count exceeds {max_files}")
        yield path
