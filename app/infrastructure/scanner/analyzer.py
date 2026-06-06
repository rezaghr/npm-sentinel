from pathlib import Path

from app.domain.findings import Finding
from app.infrastructure.scanner.binary_detector import detect_executable_binaries
from app.infrastructure.scanner.command_execution_detector import detect_command_execution_patterns
from app.infrastructure.scanner.install_hook_detector import detect_install_hooks
from app.infrastructure.scanner.obfuscation_detector import detect_obfuscated_code
from app.infrastructure.scanner.package_json_reader import read_package_json
from app.infrastructure.scanner.size_comparator import detect_size_increase


class StaticPackageAnalyzer:
    def __init__(
        self,
        *,
        max_files: int = 10_000,
        max_text_file_bytes: int = 1_000_000,
        package_json_max_bytes: int = 1_000_000,
    ) -> None:
        self._max_files = max_files
        self._max_text_file_bytes = max_text_file_bytes
        self._package_json_max_bytes = package_json_max_bytes

    def analyze(
        self,
        *,
        latest_root: Path,
        latest_metadata_scripts: dict[str, object],
        latest_size: int | None,
        previous_root: Path | None,
        previous_metadata_scripts: dict[str, object] | None,
        previous_size: int | None,
    ) -> list[Finding]:
        latest_package_json = read_package_json(latest_root, max_bytes=self._package_json_max_bytes)
        latest_scripts = self._resolve_scripts(latest_metadata_scripts, latest_package_json)

        previous_scripts: dict[str, str] | None = None
        if previous_root is not None:
            previous_package_json = read_package_json(previous_root, max_bytes=self._package_json_max_bytes)
            previous_scripts = self._resolve_scripts(previous_metadata_scripts or {}, previous_package_json)

        findings: list[Finding] = []
        findings.extend(detect_install_hooks(latest_scripts, previous_scripts))
        findings.extend(detect_size_increase(latest_size, previous_size))
        findings.extend(detect_executable_binaries(latest_root, max_files=self._max_files))
        findings.extend(
            detect_obfuscated_code(
                latest_root,
                max_files=self._max_files,
                max_text_file_bytes=self._max_text_file_bytes,
            )
        )
        findings.extend(
            detect_command_execution_patterns(
                latest_root,
                max_files=self._max_files,
                max_text_file_bytes=self._max_text_file_bytes,
            )
        )
        return findings

    @staticmethod
    def _resolve_scripts(
        metadata_scripts: dict[str, object],
        package_json: dict[str, object] | None,
    ) -> dict[str, str]:
        if metadata_scripts:
            return {
                key: value
                for key, value in metadata_scripts.items()
                if isinstance(key, str) and isinstance(value, str)
            }
        if package_json is None:
            return {}
        scripts = package_json.get("scripts")
        if not isinstance(scripts, dict):
            return {}
        normalized: dict[str, str] = {}
        for key, value in scripts.items():
            if isinstance(key, str) and isinstance(value, str):
                normalized[key] = value
        return normalized
