from pathlib import Path

from app.domain.enums import FindingType
from app.infrastructure.scanner.binary_detector import detect_executable_binaries


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_detect_elf_magic_bytes(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "package" / "bin" / "tool", b"\x7fELF\x00\x00")
    findings = detect_executable_binaries(tmp_path)

    assert any(f.finding_type == FindingType.EXECUTABLE_BINARY and f.evidence == "magic:ELF" for f in findings)


def test_detect_pe_magic_bytes(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "package" / "bin" / "tool.exe.bin", b"MZ\x00\x00")
    findings = detect_executable_binaries(tmp_path)

    assert any(f.finding_type == FindingType.EXECUTABLE_BINARY and f.evidence == "magic:PE" for f in findings)


def test_detect_executable_extension(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "package" / "native" / "addon.node", b"not-binary")
    findings = detect_executable_binaries(tmp_path)

    assert any(f.finding_type == FindingType.EXECUTABLE_BINARY and f.evidence == "extension:.node" for f in findings)
