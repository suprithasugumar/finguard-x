"""Test FNCS validity, prototype categories, control experiments, and leakage audit (Task T5).

Verifies:
1. FNCS defines all 7 spec narrative categories: GROWTH, PROFITABILITY, LIQUIDITY, DEMAND, CASH FLOW, RISK, OUTLOOK.
2. Control experiments recorded: unshuffled FNCS vs narrative shuffle control vs label shuffle control.
3. Shuffled narrative control finding is documented honestly without claiming text-number mismatch if performance did not drop.
4. Leakage audit passes: prototype phrases contain zero label-derived or enforcement terms.
5. Multicollinearity / VIF reported and orthogonality claim retracted.
"""

import json
from pathlib import Path
import yaml
import pytest


def test_fncs_spec_categories_present():
    """Verify that prototypes.yaml implements all 7 spec categories."""
    prototypes_path = Path("backend/app/fncs/prototypes.yaml")
    assert prototypes_path.exists(), "prototypes.yaml missing!"
    
    with open(prototypes_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    categories = data.get("categories", {})
    category_names = {cat["name"].upper() for cat in categories.values() if isinstance(cat, dict) and "name" in cat}
    
    spec_required = {"GROWTH", "PROFITABILITY", "LIQUIDITY", "DEMAND", "CASH FLOW", "RISK", "OUTLOOK"}
    for req in spec_required:
        assert req in category_names, f"Spec narrative category {req} missing from prototypes.yaml!"


def test_fncs_control_experiments_and_honest_reporting():
    """Verify fncs_validation_controls.json records shuffle controls honestly."""
    controls_path = Path("data/processed/fncs_validation_controls.json")
    assert controls_path.exists(), "fncs_validation_controls.json missing!"
    
    with open(controls_path, "r", encoding="utf-8") as f:
        ctrl = json.load(f)
    
    assert "prevalence_baseline_pr_auc" in ctrl
    assert "true_fncs" in ctrl
    assert "narrative_shuffle_control" in ctrl
    assert "label_shuffle_control" in ctrl
    
    # Check that finding does not claim text-number mismatch if shuffled didn't drop
    finding = ctrl["narrative_shuffle_control"].get("finding", "")
    assert "narrative alignment" in finding or "does not drop" in finding
    
    # Check VIF and orthogonality claim retraction
    mv = ctrl.get("multicollinearity_and_vif", {})
    assert "estimated_vif" in mv
    assert mv["estimated_vif"] < 5.0
    assert "REPLACED" in mv.get("orthogonality_claim_status", "")


def test_fncs_prototype_leakage_audit():
    """Verify that prototype text contains zero label-derived terms."""
    prototypes_path = Path("backend/app/fncs/prototypes.yaml")
    with open(prototypes_path, "r", encoding="utf-8") as f:
        content = f.read().lower()
    
    forbidden_leakage_terms = [
        "aaer", "sec enforcement", "accounting fraud", "restated financials",
        "doj investigation", "civil money penalty", "officer bar", "manipulation",
    ]
    # In prototypes section, these terms should never be present in prompt prototypes
    with open(prototypes_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    for cat_key, cat_val in data.get("categories", {}).items():
        if isinstance(cat_val, dict) and "prototypes" in cat_val:
            for p in cat_val["prototypes"]:
                p_lower = p.lower()
                for term in forbidden_leakage_terms:
                    assert term not in p_lower, f"Leakage term '{term}' found in prototype '{p}'!"
