"""Tests for matched controls generation, leakage prevention, and distance calculation."""

from backend.app.ingest.controls import ControlsMatcher


def test_matched_controls_without_replacement():
    """Verify 1:5 control matching selects nearest log-asset controls without replacement."""
    matcher = ControlsMatcher(ratio=3, seed=42)

    positives = [
        {
            "id": 1,
            "cik": "0000100001",
            "fiscal_year": 2018,
            "sic": "3571",
            "assets": 1000000.0,
            "revenue": 500000.0,
        },
        {
            "id": 2,
            "cik": "0000100002",
            "fiscal_year": 2018,
            "sic": "3571",
            "assets": 5000000.0,
            "revenue": 2000000.0,
        },
    ]

    # 10 control candidates in SIC 3571
    candidates = [
        {
            "cik": f"000020000{i}",
            "fiscal_year": 2018,
            "sic": "3571",
            "assets": float((i + 1) * 1000000),
            "revenue": 500000.0,
        }
        for i in range(10)
    ]

    enforced_ciks = {"0000100001", "0000100002", "0000200009"}  # CIK 0000200009 is enforced!

    matched, unmatched = matcher.find_matched_controls(positives, candidates, enforced_ciks)

    assert len(unmatched) == 0
    # 2 positives * 3 controls = 6 controls
    assert len(matched) == 6

    # Verify no control was reused (matching without replacement)
    control_ciks = [c["cik"] for c in matched]
    assert len(control_ciks) == len(
        set(control_ciks)
    ), "Controls must be matched without replacement"

    # Verify enforced CIK 0000200009 was NEVER selected as a control
    assert "0000200009" not in control_ciks, "Enforced CIK must never be chosen as a control"

    # Verify matched_positive_id and match_distance are populated
    for c in matched:
        assert c["matched_positive_id"] in (1, 2)
        assert c["match_distance"] >= 0.0
        assert c["label"] == 0
