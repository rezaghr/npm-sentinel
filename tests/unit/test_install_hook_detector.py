from app.domain.enums import FindingType
from app.infrastructure.scanner.install_hook_detector import detect_install_hooks


def test_detect_install_hook_added() -> None:
    findings = detect_install_hooks(
        latest_scripts={"preinstall": "node setup.js"},
        previous_scripts={},
    )
    finding_types = {finding.finding_type for finding in findings}
    assert FindingType.INSTALL_HOOK_ADDED in finding_types


def test_detect_install_hook_removed() -> None:
    findings = detect_install_hooks(
        latest_scripts={},
        previous_scripts={"postinstall": "node done.js"},
    )
    finding_types = {finding.finding_type for finding in findings}
    assert FindingType.INSTALL_HOOK_REMOVED in finding_types


def test_detect_install_hook_present() -> None:
    findings = detect_install_hooks(
        latest_scripts={"install": "node install.js"},
        previous_scripts={"install": "node install.js"},
    )
    finding_types = {finding.finding_type for finding in findings}
    assert FindingType.INSTALL_HOOK_PRESENT in finding_types


def test_first_version_hook_is_present_not_added() -> None:
    findings = detect_install_hooks(
        latest_scripts={"postinstall": "node done.js"},
        previous_scripts=None,
    )
    finding_types = {finding.finding_type for finding in findings}
    assert FindingType.INSTALL_HOOK_PRESENT in finding_types
    assert FindingType.INSTALL_HOOK_ADDED not in finding_types
