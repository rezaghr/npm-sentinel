from dataclasses import dataclass

from app.domain.enums import FindingSeverity, FindingType


@dataclass(frozen=True)
class Finding:
    finding_type: FindingType
    severity: FindingSeverity
    category: str
    description: str
    file_path: str | None = None
    evidence: str | None = None
