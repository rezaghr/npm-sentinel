from app.domain.enums import FindingSeverity, FindingType
from app.domain.findings import Finding

_REQUIRED_HOOKS = ("preinstall", "install", "postinstall")
_OPTIONAL_HOOKS = ("prepare", "prepublish", "prepublishOnly")
_ALL_HOOKS = _REQUIRED_HOOKS + _OPTIONAL_HOOKS


def detect_install_hooks(
    latest_scripts: dict[str, str],
    previous_scripts: dict[str, str] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    previous = previous_scripts or {}
    has_previous_version = previous_scripts is not None

    for hook_name in _ALL_HOOKS:
        has_latest = hook_name in latest_scripts
        has_previous = hook_name in previous
        required_hook = hook_name in _REQUIRED_HOOKS

        if has_latest and has_previous_version and not has_previous:
            findings.append(
                Finding(
                    finding_type=FindingType.INSTALL_HOOK_ADDED,
                    severity=FindingSeverity.HIGH if required_hook else FindingSeverity.MEDIUM,
                    category="scripts",
                    description=f"{hook_name} script added in latest package version.",
                    evidence=hook_name,
                )
            )
            continue

        if has_previous and not has_latest:
            findings.append(
                Finding(
                    finding_type=FindingType.INSTALL_HOOK_REMOVED,
                    severity=FindingSeverity.LOW,
                    category="scripts",
                    description=f"{hook_name} script removed in latest package version.",
                    evidence=hook_name,
                )
            )
            continue

        if has_latest:
            findings.append(
                Finding(
                    finding_type=FindingType.INSTALL_HOOK_PRESENT,
                    severity=FindingSeverity.MEDIUM if required_hook else FindingSeverity.LOW,
                    category="scripts",
                    description=f"{hook_name} script is present in package scripts.",
                    evidence=hook_name,
                )
            )

    return findings
