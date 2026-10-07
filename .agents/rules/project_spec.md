# FinGuard-X Workspace Rules and Guidelines

Refer to [PROJECT_SPEC.md](file:///c:/Users/RITHIKESH%20S/finguard-x/PROJECT_SPEC.md) in the project root for the complete master build specification.

## Core Rules:
1. **R1. No fake data.** Never synthesize, simulate, hard-code or "fill in" companies, filings, financials, labels, entities, or metrics. If data is missing or extraction fails, log it, store a null with a reason code, and report it in the phase report.
2. **R2. Honest reporting.** Report all results, including negative ones. If multimodal fusion does not beat numeric baseline, report it. Never tune on the test set. Never cherry-pick seeds.
3. **R3. No leakage.** Company-year features may only use info available at that filing's date. As-originally-reported XBRL values only. Enforcement dates/AAER used only for labels. Prior-year features use earlier filings only.
4. **R4. SEC compliance.** Declared User-Agent from `SEC_USER_AGENT`. Max 5 req/s. Disk cache keyed by URL/accession. Request log table. Prefer SEC bulk files (`companyfacts.zip`, `submissions.zip`).
5. **R5. Language.** Never say "fraud detected" or "proof". Use: "Fraud Risk / Review Priority", "Potential inconsistency", "Unusual related-party network pattern", "Risk signal", "Requires review".
6. **R6. Reproducibility.** Python 3.11, pinned dependencies, `SEED=42`, deterministic splits, single command per pipeline stage, CPU-only.
7. **Protocol.** Build ONE phase at a time. Work in Planning mode (implementation plan + approval first). Run gate checks, write `docs/phase_N_report.md` before moving to next phase. Maintain `docs/DECISIONS.md`.
