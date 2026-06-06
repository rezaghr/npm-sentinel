from app.infrastructure.scanner.binary_detector import detect_executable_binaries
from app.infrastructure.scanner.command_execution_detector import detect_command_execution_patterns
from app.infrastructure.scanner.install_hook_detector import detect_install_hooks
from app.infrastructure.scanner.obfuscation_detector import detect_obfuscated_code
from app.infrastructure.scanner.package_json_reader import read_package_json
from app.infrastructure.scanner.size_comparator import detect_size_increase

__all__ = [
    "detect_command_execution_patterns",
    "detect_executable_binaries",
    "detect_install_hooks",
    "detect_obfuscated_code",
    "detect_size_increase",
    "read_package_json",
]
