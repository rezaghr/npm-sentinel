from pathlib import Path

from app.domain.enums import FindingSeverity, FindingType
from app.domain.findings import Finding
from app.infrastructure.scanner.file_iteration import iter_regular_files

_EXECUTABLE_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".node"}


def detect_executable_binaries(extracted_root: Path, *, max_files: int = 10_000) -> list[Finding]:
    findings: list[Finding] = []

    for path in iter_regular_files(extracted_root, max_files=max_files):
        relative_path = _relative_path(path, extracted_root)
        if relative_path is None:
            continue

        reason: str | None = None
        if path.suffix.lower() in _EXECUTABLE_EXTENSIONS:
            reason = f"extension:{path.suffix.lower()}"
        else:
            magic = _read_magic(path)
            if magic.startswith(b"\x7fELF"):
                reason = "magic:ELF"
            elif magic.startswith(b"MZ"):
                reason = "magic:PE"

        if reason is None:
            continue

        findings.append(
            Finding(
                finding_type=FindingType.EXECUTABLE_BINARY,
                severity=FindingSeverity.HIGH,
                category="binary",
                file_path=relative_path,
                description="Executable binary pattern detected in package files.",
                evidence=reason,
            )
        )

    return findings


def _read_magic(path: Path) -> bytes:
    try:
        with path.open("rb") as file_handle:
            return file_handle.read(4)
    except OSError:
        return b""


def _relative_path(path: Path, root: Path) -> str | None:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return None
