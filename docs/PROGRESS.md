# FinGuard-X: Tonight Mode Progress Log

Progress log tracking autonomous completion across Stages 1–6.

## Stage 1: Knowledge Graph (Done)
- **Done**: NetworkX graphs built for 500 cohort company-years with entity normalization, topological metrics, YoY evolution, and GRAPH_ANOMALY_SCORE.
- **Counts**: 149 / 500 (29.80%) usable graphs extracted; 3,268 total nodes, 3,871 edges, 484 shell/holding entities.
- **Evidence**: 3 real examples extracted with evidence sentences (CECO ENV FY2019, LSB INDUSTRIES FY2012, MOOG INC FY2023).
- **Known Gaps**: 351 company-years lack related-party footnotes or extracted entities; marked with graph_available=False and zero-imputed topological metrics.
- **Artifacts**: Populated company_year_graph_features table; summary serialized to data/processed/stage1_graph_summary.json; no gold set used.

## Stage 2: FNCS (Financial-Narrative Contradiction Score) (Done)
- **Done**: Built 7-category prototypes.yaml, numeric winsorized industry-year z-score + tanh signals, MiniLM retrieval, Loughran-McDonald sentiment tone, contradiction scores, and plain-language explanations.
- **Counts**: 500 / 500 cohort company-years scored; mean FNCS 0.8571 (positives) vs 0.8235 (controls); fixed weights without test set tuning.
- **Evidence**: 3 real explanation sentences verified (CECO ENV FY2019, APPLIED MATERIALS FY2019, ARMSTRONG WORLD FY2017) linking optimistic disclosures to declining numeric ratios.
- **Known Gaps**: 84 company-years lacked MD&A text in filing_sections; resolved via zero-imputed text tone and neutral contradiction fallback.
- **Artifacts**: Populated company_year_fncs_features table; summary serialized to data/processed/stage2_fncs_summary.json.

