from pathlib import Path

from app.domain.enums import FindingType
from app.infrastructure.scanner.obfuscation_detector import detect_obfuscated_code


def test_detect_obfuscation_pattern(tmp_path: Path) -> None:
    file_path = tmp_path / "package" / "index.js"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("const x = eval('alert(1)');", encoding="utf-8")

    findings = detect_obfuscated_code(tmp_path)

    assert any(f.finding_type == FindingType.OBFUSCATED_CODE and f.evidence == "eval(" for f in findings)


def test_ignores_plain_minified_line_without_obfuscation(tmp_path: Path) -> None:
    file_path = tmp_path / "package" / "index.js"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("a=" + "!".join(["x"] * 300), encoding="utf-8")

    assert detect_obfuscated_code(tmp_path) == []


def test_detects_long_minified_like_line(tmp_path: Path) -> None:
    file_path = tmp_path / "package" / "bundle.js"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    long_line = "function a(){return 1;}" * 140
    file_path.write_text(long_line, encoding="utf-8")

    findings = detect_obfuscated_code(tmp_path)

    assert any(
        finding.finding_type == FindingType.OBFUSCATED_CODE and finding.evidence == "long minified-like line"
        for finding in findings
    )
