from pathlib import Path
import re

from app.domain.enums import FindingSeverity, FindingType
from app.domain.findings import Finding
from app.infrastructure.scanner.file_iteration import iter_regular_files

_COMMAND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("child_process", re.compile(r"\bchild_process\b")),
    ("exec(", re.compile(r"\bexec\s*\(")),
    ("execSync(", re.compile(r"\bexecSync\s*\(")),
    ("spawn(", re.compile(r"\bspawn\s*\(")),
    ("spawnSync(", re.compile(r"\bspawnSync\s*\(")),
    ("curl", re.compile(r"(?<![A-Za-z0-9_-])curl(?![A-Za-z0-9_-])")),
    ("wget", re.compile(r"(?<![A-Za-z0-9_-])wget(?![A-Za-z0-9_-])")),
    ("powershell", re.compile(r"(?<![A-Za-z0-9_-])powershell(?:\.exe)?(?![A-Za-z0-9_-])", re.IGNORECASE)),
    ("cmd.exe", re.compile(r"(?<![A-Za-z0-9_-])cmd\.exe(?![A-Za-z0-9_-])", re.IGNORECASE)),
    ("bash -c", re.compile(r"\bbash\s+-c\b")),
    ("sh -c", re.compile(r"\bsh\s+-c\b")),
)
_MAX_TEXT_FILE_BYTES = 1_000_000
_CODE_EXTENSIONS = {".cjs", ".cmd", ".js", ".jsx", ".mjs", ".ps1", ".py", ".sh", ".ts", ".tsx"}


def detect_command_execution_patterns(
    extracted_root: Path,
    *,
    max_files: int = 10_000,
    max_text_file_bytes: int = _MAX_TEXT_FILE_BYTES,
) -> list[Finding]:
    findings: list[Finding] = []

    for file_path in iter_regular_files(extracted_root, max_files=max_files):
        if file_path.suffix.lower() not in _CODE_EXTENSIONS:
            continue
        try:
            relative_path = str(file_path.relative_to(extracted_root))
            if file_path.stat().st_size > max_text_file_bytes:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        matched = _match_command_pattern(text)
        if matched is None:
            continue

        findings.append(
            Finding(
                finding_type=FindingType.COMMAND_EXECUTION_PATTERN,
                severity=FindingSeverity.HIGH,
                category="execution",
                file_path=relative_path,
                description="Potential command execution pattern detected in source file.",
                evidence=matched,
            )
        )

    return findings


def _match_command_pattern(text: str) -> str | None:
    for evidence, pattern in _COMMAND_PATTERNS:
        if pattern.search(text):
            return evidence
    return None
