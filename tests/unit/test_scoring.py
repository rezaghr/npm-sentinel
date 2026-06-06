from dataclasses import dataclass

from app.domain.enums import FindingSeverity, FindingType
from app.domain.findings import Finding
from app.domain.scoring import BASE_SCORE, calculate_risk_level, calculate_score, explain_score


def _finding(finding_type: FindingType) -> Finding:
    return Finding(
        finding_type=finding_type,
        severity=FindingSeverity.MEDIUM,
        category="test",
        description="test finding",
    )


def test_calculate_score_low() -> None:
    score = calculate_score([_finding(FindingType.INSTALL_HOOK_PRESENT)])
    assert score == 6
    assert calculate_risk_level(score) == "low"


def test_calculate_score_medium() -> None:
    score = calculate_score(
        [
            _finding(FindingType.EXECUTABLE_BINARY),
            _finding(FindingType.SIZE_INCREASE_MEDIUM),
        ]
    )
    assert score == 31
    assert calculate_risk_level(score) == "medium"


def test_calculate_score_high() -> None:
    score = calculate_score(
        [
            _finding(FindingType.EXECUTABLE_BINARY),
            _finding(FindingType.INSTALL_HOOK_ADDED),
            _finding(FindingType.COMMAND_EXECUTION_PATTERN),
            _finding(FindingType.OBFUSCATED_CODE),
        ]
    )
    assert score == 76
    assert calculate_risk_level(score) == "high"


def test_calculate_score_capped_at_100() -> None:
    findings = [_finding(FindingType.EXECUTABLE_BINARY) for _ in range(10)]
    score = calculate_score(findings)
    assert score == 100


def test_calculate_risk_level_boundaries() -> None:
    assert calculate_risk_level(30) == "low"
    assert calculate_risk_level(31) == "medium"
    assert calculate_risk_level(70) == "medium"
    assert calculate_risk_level(71) == "high"


@dataclass(frozen=True)
class UnknownFinding:
    finding_type: str = "UNKNOWN_FINDING"


def test_unknown_finding_contributes_zero() -> None:
    score = calculate_score([UnknownFinding()])
    assert score == BASE_SCORE


def test_explain_score_is_traceable() -> None:
    findings = [
        _finding(FindingType.INSTALL_HOOK_PRESENT),
        _finding(FindingType.SIZE_INCREASE_HIGH),
        _finding(FindingType.INSTALL_HOOK_REMOVED),
    ]
    contributions = explain_score(findings)
    total_points = sum(item.points for item in contributions)

    assert [item.points for item in contributions] == [5, 10, 0]
    assert calculate_score(findings) == BASE_SCORE + total_points
