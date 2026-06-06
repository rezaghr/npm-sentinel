from app.domain.enums import FindingSeverity, FindingType
from app.domain.findings import Finding


def detect_size_increase(latest_size: int | None, previous_size: int | None) -> list[Finding]:
    if latest_size is None or previous_size is None:
        return []
    if previous_size <= 0 or latest_size <= previous_size:
        return []

    increase_percent = ((latest_size - previous_size) / previous_size) * 100

    if increase_percent > 100:
        return [
            Finding(
                finding_type=FindingType.SIZE_INCREASE_HIGH,
                severity=FindingSeverity.HIGH,
                category="size",
                description="Package size increased by more than 100%.",
                evidence=f"{increase_percent:.2f}%",
            )
        ]

    if increase_percent >= 30:
        return [
            Finding(
                finding_type=FindingType.SIZE_INCREASE_MEDIUM,
                severity=FindingSeverity.MEDIUM,
                category="size",
                description="Package size increased between 30% and 100%.",
                evidence=f"{increase_percent:.2f}%",
            )
        ]

    return []
