from pathlib import Path

from app.infrastructure.scanner.package_json_reader import read_package_json


def test_read_package_json_returns_none_when_file_exceeds_limit(tmp_path: Path) -> None:
    package_json = tmp_path / "package" / "package.json"
    package_json.parent.mkdir(parents=True)
    package_json.write_text('{"name":"oversized"}', encoding="utf-8")

    assert read_package_json(tmp_path, max_bytes=1) is None
