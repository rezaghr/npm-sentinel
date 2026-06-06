from pathlib import Path

from app.domain.enums import FindingType
from app.infrastructure.scanner.command_execution_detector import detect_command_execution_patterns


def test_detect_command_execution_pattern(tmp_path: Path) -> None:
    file_path = tmp_path / "package" / "runner.js"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("const { execSync } = require('child_process'); execSync('curl http://x');", encoding="utf-8")

    findings = detect_command_execution_patterns(tmp_path)

    assert any(
        f.finding_type == FindingType.COMMAND_EXECUTION_PATTERN and f.evidence in {"child_process", "execSync(", "curl"}
        for f in findings
    )


def test_ignores_command_words_in_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "package" / "README.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("Use curl in your terminal.", encoding="utf-8")

    assert detect_command_execution_patterns(tmp_path) == []
