from dataclasses import dataclass
from typing import Any, Iterable

from app.domain.enums import FindingType
from app.domain.findings import Finding

BASE_SCORE = 1
MAX_SCORE = 100

FINDING_SCORE_DELTAS: dict[FindingType, int] = {
    FindingType.EXECUTABLE_BINARY: 25,
    FindingType.INSTALL_HOOK_ADDED: 20,
    FindingType.COMMAND_EXECUTION_PATTERN: 15,
    FindingType.OBFUSCATED_CODE: 15,
    FindingType.SIZE_INCREASE_HIGH: 10,
    FindingType.SIZE_INCREASE_MEDIUM: 5,
    FindingType.INSTALL_HOOK_PRESENT: 5,
    FindingType.INSTALL_HOOK_REMOVED: 0,
}


@dataclass(frozen=True)
class ScoreContribution:
    finding_type: str
    points: int


def calculate_score(findings: Iterable[Finding | Any]) -> int:
    raw_score = BASE_SCORE + sum(contribution.points for contribution in explain_score(findings))
    return _clamp_score(raw_score)


def calculate_risk_level(score: int) -> str:
    normalized_score = _clamp_score(score)

    if normalized_score <= 30:
        return "low"
    if normalized_score <= 70:
        return "medium"
    return "high"


def explain_score(findings: Iterable[Finding | Any]) -> list[ScoreContribution]:
    contributions: list[ScoreContribution] = []

    for finding in findings:
        finding_type = getattr(finding, "finding_type", None)
        points = FINDING_SCORE_DELTAS.get(finding_type, 0)
        contributions.append(
            ScoreContribution(
                finding_type=str(finding_type),
                points=points,
            )
        )

    return contributions


def _clamp_score(score: int) -> int:
    if score < BASE_SCORE:
        return BASE_SCORE
    if score > MAX_SCORE:
        return MAX_SCORE
    return score
