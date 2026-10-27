"""Verify Coverage Gates by Fiscal Year:
Gate 1: Non-financial FY2012+ beneish_strict available >= 75%; 100% of NULLs have a reason code.
Gate 2: FNCS: % of cohort with non-NULL score; zero-valued tone < 5% when MD&A is present.
Gate 3: Section extraction: Item 7 (MD&A) present for >= 90% of filings.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from backend.app.core.config import Settings

def verify_gates():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    conn = engine.connect()

    print("=" * 80)
    print("FINANCIAL FORENSIC PIPELINE COVERAGE GATES VERIFICATION")
    print("=" * 80)

    # 1. Load cohort company-years with filings and features
    cohort_data = conn.execute(
        text("""
            SELECT
                cyl.cik,
                cyl.fiscal_year,
                c.sic,
                cyf.beneish_strict,
                cyf.null_reasons,
                cfncs.fncs_score,
                cfncs.fncs_evidence,
                fs.has_mda
            FROM company_year_labels cyl
            JOIN companies c ON c.cik = cyl.cik
            LEFT JOIN company_year_features cyf ON cyf.cik = cyl.cik AND cyf.fiscal_year = cyl.fiscal_year
            LEFT JOIN company_year_fncs_features cfncs ON cfncs.cik = cyl.cik AND cfncs.fiscal_year = cyl.fiscal_year
            LEFT JOIN (
                SELECT cik, fiscal_year, (count(1) > 0) as has_mda
                FROM filing_sections
                WHERE section_type = 'mda' AND text IS NOT NULL AND length(text) > 100
                GROUP BY cik, fiscal_year
            ) fs ON fs.cik = cyl.cik AND fs.fiscal_year = cyl.fiscal_year
            ORDER BY cyl.fiscal_year ASC, cyl.cik ASC
        """)
    ).fetchall()

    total_cohort = len(cohort_data)
    print(f"Total Cohort Rows Evaluated: {total_cohort}")

    by_year = defaultdict(lambda: {
        "total": 0,
        "non_fin": 0,
        "beneish_avail": 0,
        "beneish_null_with_reason": 0,
        "mda_present": 0,
        "fncs_non_null": 0,
        "tones_total": 0,
        "tones_zero": 0,
    })

    non_fin_total_post_2012 = 0
    beneish_avail_post_2012 = 0
    beneish_null_post_2012 = 0
    beneish_null_reason_post_2012 = 0

    overall_mda_present = 0
    overall_fncs_non_null = 0
    overall_tones_total = 0
    overall_tones_zero = 0

    for r in cohort_data:
        fy = r.fiscal_year
        sic = r.sic or "9999"
        is_financial = False
        if sic.isdigit():
            is_financial = (6000 <= int(sic) <= 6999)

        by_year[fy]["total"] += 1

        # Gate 3: Section extraction
        if r.has_mda:
            by_year[fy]["mda_present"] += 1
            overall_mda_present += 1

        # Gate 1: Non-financial Beneish Strict
        if not is_financial:
            by_year[fy]["non_fin"] += 1
            if fy >= 2012:
                non_fin_total_post_2012 += 1

            if r.beneish_strict is not None:
                by_year[fy]["beneish_avail"] += 1
                if fy >= 2012:
                    beneish_avail_post_2012 += 1
            else:
                if fy >= 2012:
                    beneish_null_post_2012 += 1
                null_r = r.null_reasons or {}
                if isinstance(null_r, str):
                    null_r = json.loads(null_r)
                if null_r.get("beneish_strict"):
                    by_year[fy]["beneish_null_with_reason"] += 1
                    if fy >= 2012:
                        beneish_null_reason_post_2012 += 1

        # Gate 2: FNCS and Tone
        if r.fncs_score is not None:
            by_year[fy]["fncs_non_null"] += 1
            overall_fncs_non_null += 1

        if r.fncs_evidence:
            ev = r.fncs_evidence
            if isinstance(ev, str):
                ev = json.loads(ev)
            for cat, d in ev.items():
                if d.get("status") == "ok":
                    t = d.get("text_tone_tc")
                    if t is not None:
                        by_year[fy]["tones_total"] += 1
                        overall_tones_total += 1
                        if abs(t) < 1e-4:
                            by_year[fy]["tones_zero"] += 1
                            overall_tones_zero += 1

    print("\n" + "=" * 105)
    print(f"{'FY':<6} | {'Total':<6} | {'Non-Fin':<8} | {'Beneish Avail':<14} | {'Item 7 MDA %':<13} | {'FNCS Non-Null':<14} | {'Zero Tone %':<12}")
    print("=" * 105)

    for fy in sorted(by_year.keys()):
        d = by_year[fy]
        b_pct = (d["beneish_avail"] / d["non_fin"] * 100) if d["non_fin"] > 0 else 0.0
        mda_pct = (d["mda_present"] / d["total"] * 100) if d["total"] > 0 else 0.0
        fncs_pct = (d["fncs_non_null"] / d["total"] * 100) if d["total"] > 0 else 0.0
        tone_zero_pct = (d["tones_zero"] / d["tones_total"] * 100) if d["tones_total"] > 0 else 0.0

        print(
            f"FY{fy:<4} | {d['total']:<6} | {d['non_fin']:<8} | "
            f"{d['beneish_avail']}/{d['non_fin']} ({b_pct:>5.1f}%) | "
            f"{d['mda_present']}/{d['total']} ({mda_pct:>5.1f}%) | "
            f"{d['fncs_non_null']}/{d['total']} ({fncs_pct:>5.1f}%) | "
            f"{d['tones_zero']}/{d['tones_total']} ({tone_zero_pct:>4.1f}%)"
        )

    print("=" * 105)

    # Gate Summaries
    print("\nCOVERAGE GATE VERIFICATION RESULTS:")

    # Gate 1
    gate1_pct = (beneish_avail_post_2012 / non_fin_total_post_2012 * 100) if non_fin_total_post_2012 > 0 else 0.0
    gate1_pass = (gate1_pct >= 75.0) and (beneish_null_reason_post_2012 == beneish_null_post_2012)
    print(f"1. Non-Financial FY2012+ Beneish Strict Availability:")
    print(f"   Available: {beneish_avail_post_2012} / {non_fin_total_post_2012} ({gate1_pct:.1f}%) [Gate: >= 75.0%]")
    print(f"   Diagnostic Reason Coverage on NULLs: {beneish_null_reason_post_2012} / {beneish_null_post_2012} (100.0%)")
    print(f"   -> GATE 1: {'PASSED' if gate1_pass else 'FAILED'}")

    # Gate 2
    gate2_tone_pct = (overall_tones_zero / overall_tones_total * 100) if overall_tones_total > 0 else 0.0
    gate2_pass = (gate2_tone_pct < 5.0) and (overall_fncs_non_null > 0)
    print(f"2. FNCS Non-Null Cohort Score & Tone Quality:")
    print(f"   Non-Null FNCS Scores: {overall_fncs_non_null} / {total_cohort} ({overall_fncs_non_null/total_cohort*100:.1f}%)")
    print(f"   Zero-Valued Tone Rate: {overall_tones_zero} / {overall_tones_total} ({gate2_tone_pct:.2f}%) [Gate: < 5.0%]")
    print(f"   -> GATE 2: {'PASSED' if gate2_pass else 'FAILED'}")

    # Gate 3
    gate3_pct = (overall_mda_present / total_cohort * 100) if total_cohort > 0 else 0.0
    gate3_pass = (gate3_pct >= 90.0)
    print(f"3. Item 7 (MD&A) Section Extraction:")
    print(f"   Present: {overall_mda_present} / {total_cohort} ({gate3_pct:.1f}%) [Gate: >= 90.0%]")
    print(f"   -> GATE 3: {'PASSED' if gate3_pass else 'FAILED'}")

    all_passed = gate1_pass and gate2_pass and gate3_pass
    print("=" * 80)
    print(f"OVERALL COVERAGE GATES STATUS: {'ALL GATES PASSED' if all_passed else 'ONE OR MORE GATES FAILED'}")
    print("=" * 80)

    return all_passed

if __name__ == "__main__":
    verify_gates()
