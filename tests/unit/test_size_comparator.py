from app.domain.enums import FindingType
from app.infrastructure.scanner.size_comparator import detect_size_increase


def test_detect_size_increase_medium() -> None:
    findings = detect_size_increase(latest_size=150, previous_size=100)
    assert len(findings) == 1
    assert findings[0].finding_type == FindingType.SIZE_INCREASE_MEDIUM


def test_detect_size_increase_high() -> None:
    findings = detect_size_increase(latest_size=250, previous_size=100)
    assert len(findings) == 1
    assert findings[0].finding_type == FindingType.SIZE_INCREASE_HIGH


def test_detect_size_increase_none_under_threshold() -> None:
    findings = detect_size_increase(latest_size=120, previous_size=100)
    assert findings == []
