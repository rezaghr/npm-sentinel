import json
from pathlib import Path
from typing import Any


def read_package_json(extracted_root: Path, *, max_bytes: int = 1_000_000) -> dict[str, Any] | None:
    package_json_path = extracted_root / "package" / "package.json"

    try:
        if package_json_path.stat().st_size > max_bytes:
            return None
        content = package_json_path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed
