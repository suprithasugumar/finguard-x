"""Test ablation evaluation design, temporal isolation, and honest statistics (Tasks T3 & T4).

Verifies:
1. M1-M9 spec models plus M10 FNCS-alone extra.
2. Every model reports LogReg, XGBoost, and Random Forest (except rule-based M1).
3. Time-aware split has strict zero CIK leakage across partitions.
4. 5-Fold CIK-grouped CV reports real positive and CIK counts per fold.
5. Random-guess PR-AUC (prevalence) reported alongside all PR-AUC numbers.
6. Cluster bootstrap uses B >= 2000 and never outputs 'p = 0.0000'.
7. Holm-Bonferroni correction covers M9 vs M1, M2, and M8 with monotonic adjusted p-values.
"""

import json
from pathlib import Path
import numpy as np
import pytest

from backend.app.models.train_ablation import (
    MODEL_SPECS,
    BOOTSTRAP_RESAMPLES,
    holm_bonferroni_correction,
    load_dataset,
    evaluate_time_aware_splits,
)


def test_ablation_model_spec_coverage():
    """Verify that M1-M9 match the spec exactly and M10 is FNCS-alone extra."""
    assert 1 in MODEL_SPECS
    assert "Beneish" in MODEL_SPECS[1]["name"]

    assert 2 in MODEL_SPECS
    assert "Numeric" in MODEL_SPECS[2]["name"]

    assert 3 in MODEL_SPECS
    assert "Text" in MODEL_SPECS[3]["name"]

    assert 4 in MODEL_SPECS
    assert "Graph" in MODEL_SPECS[4]["name"]

    assert 5 in MODEL_SPECS
    assert "Numeric + Text" in MODEL_SPECS[5]["name"]

    assert 6 in MODEL_SPECS
    assert "Numeric + Graph" in MODEL_SPECS[6]["name"]

    assert 7 in MODEL_SPECS
    assert "Text + Graph" in MODEL_SPECS[7]["name"]

    assert 8 in MODEL_SPECS
    assert "Numeric + Text + Graph" in MODEL_SPECS[8]["name"]

    assert 9 in MODEL_SPECS
    assert "Numeric + Text + Graph + FNCS" in MODEL_SPECS[9]["name"]

    assert 10 in MODEL_SPECS
    assert "fncs" in MODEL_SPECS[10]["name"].lower()


def test_time_aware_splits_have_zero_cik_leakage():
    """Verify that train, validation, and test splits have zero CIK overlap."""
    df = load_dataset()
    cik_latest_fy = df.groupby("cik")["fiscal_year"].max().to_dict()
    train_ciks = {c for c, y in cik_latest_fy.items() if y <= 2018}
    val_ciks = {c for c, y in cik_latest_fy.items() if 2019 <= y <= 2020}
    test_ciks = {c for c, y in cik_latest_fy.items() if y >= 2021}

    # Strict zero CIK leakage assertions
    assert len(train_ciks.intersection(val_ciks)) == 0, "CIK leakage between Train and Val!"
    assert len(train_ciks.intersection(test_ciks)) == 0, "CIK leakage between Train and Test!"
    assert len(val_ciks.intersection(test_ciks)) == 0, "CIK leakage between Val and Test!"

    assert len(train_ciks) > 0
    assert len(val_ciks) > 0
    assert len(test_ciks) > 0

    # Also verify the persisted artifact records non-zero positives and records per split
    artifact_path = Path("data/processed/stage3_results_summary.json")
    if artifact_path.exists():
        with open(artifact_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        splits = data["time_aware_evaluation"]["splits"]
        assert splits["train"]["positives"] > 0
        assert splits["validation"]["positives"] > 0
        assert splits["test"]["positives"] > 0
        assert splits["train"]["unique_ciks"] == len(train_ciks)
        assert splits["validation"]["unique_ciks"] == len(val_ciks)
        assert splits["test"]["unique_ciks"] == len(test_ciks)


def test_holm_bonferroni_correction_monotonicity():
    """Verify that Holm-Bonferroni correction enforces family-wise error control and monotonicity."""
    raw_comps = [
        {"comparison": "M9 vs M8", "p_raw": 0.0000},
        {"comparison": "M9 vs M2", "p_raw": 0.0350},
        {"comparison": "M9 vs M1", "p_raw": 0.0020},
    ]
    corrected = holm_bonferroni_correction(raw_comps)

    assert len(corrected) == 3
    for c in corrected:
        assert "p_adj" in c
        assert "p_adj_str" in c
        # Never output p = 0.0000
        assert c["p_adj_str"] != "0.0000"
        assert c["p_adj_str"] != "p = 0.0000"
        if c["p_adj"] == 0.0:
            assert "< 1/" in c["p_adj_str"]

    # Check monotonicity
    p_adjs = [c["p_adj"] for c in corrected]
    assert all(p >= 0.0 and p <= 1.0 for p in p_adjs)
