import re
from pathlib import Path

from app.domain.enums import FindingSeverity, FindingType
from app.domain.findings import Finding
from app.infrastructure.scanner.file_iteration import iter_regular_files

_HEX_IDENTIFIER_RE = re.compile(r"_0x[a-fA-F0-9]+")
_HEX_ESCAPE_RE = re.compile(r"(?:\\x[0-9a-fA-F]{2}){6,}")
_BASE64_LIKE_RE = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
_MAX_TEXT_FILE_BYTES = 1_000_000
_CODE_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
_SKIPPED_EXTENSIONS = {".map", ".md", ".markdown", ".txt"}
_MINIFIED_LINE_MIN_LENGTH = 2_000
_MINIFIED_LINE_MAX_WHITESPACE_RATIO = 0.02
_MINIFIED_LINE_MIN_SYMBOL_RATIO = 0.08
_MINIFIED_SYMBOLS = set("{}[]();,:.=+-*/%&|!<>?~")


def detect_obfuscated_code(
    extracted_root: Path,
    *,
    max_files: int = 10_000,
    max_text_file_bytes: int = _MAX_TEXT_FILE_BYTES,
) -> list[Finding]:
    findings: list[Finding] = []

    for file_path, relative_path, text in _iter_text_files(
        extracted_root,
        max_files=max_files,
        max_text_file_bytes=max_text_file_bytes,
    ):
        evidence = _match_obfuscation_evidence(text)
        if evidence is None:
            continue

        findings.append(
            Finding(
                finding_type=FindingType.OBFUSCATED_CODE,
                severity=FindingSeverity.MEDIUM,
                category="code",
                file_path=relative_path,
                description="Suspicious obfuscation pattern detected in source file.",
                evidence=evidence,
            )
        )

    return findings


def _match_obfuscation_evidence(text: str) -> str | None:
    if "eval(" in text:
        return "eval("
    if "Function(" in text:
        return "Function("
    if _HEX_IDENTIFIER_RE.search(text):
        return "_0x*"
    if _HEX_ESCAPE_RE.search(text):
        return "\\xNN repeated"
    if _BASE64_LIKE_RE.search(text):
        return "long base64-like string"
    if _has_long_minified_like_line(text):
        return "long minified-like line"

    return None


def _has_long_minified_like_line(text: str) -> bool:
    for line in text.splitlines() or [text]:
        line_length = len(line)
        if line_length < _MINIFIED_LINE_MIN_LENGTH:
            continue
        whitespace_ratio = sum(1 for char in line if char.isspace()) / line_length
        symbol_ratio = sum(1 for char in line if char in _MINIFIED_SYMBOLS) / line_length
        if whitespace_ratio <= _MINIFIED_LINE_MAX_WHITESPACE_RATIO and symbol_ratio >= _MINIFIED_LINE_MIN_SYMBOL_RATIO:
            return True
    return False


def _iter_text_files(extracted_root: Path, *, max_files: int, max_text_file_bytes: int):
    for file_path in iter_regular_files(extracted_root, max_files=max_files):
        suffix = file_path.suffix.lower()
        if suffix in _SKIPPED_EXTENSIONS:
            continue
        if suffix and suffix not in _CODE_EXTENSIONS:
            continue
        try:
            relative_path = str(file_path.relative_to(extracted_root))
            stat = file_path.stat()
            if stat.st_size > max_text_file_bytes:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        yield file_path, relative_path, text
