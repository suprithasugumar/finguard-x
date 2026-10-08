"""Script to fetch primary 10-K documents, extract sections, and compute NLP narrative drift (Sprint A2 & A3).

Autonomous execution conforming to:
- Cached SEC client (5 req/s, cache, request_log)
- Extraction into filing_sections (MD&A, Risk Factors, Related Party)
- Sentence split, cached MiniLM (all-MiniLM-L6-v2) embeddings keyed by text hash
- Bidirectional best-match drift, doc cosine drift, evidence snippets, supporting linguistic features
- Summary generation for sprint_a_report.md
"""

import json
import logging
import sys
import time
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.core.config import get_settings
from backend.app.db.models.entities import CompanyYearLabel, Filing
from backend.app.db.models.sections import FilingNLPFeatures, FilingSection
from backend.app.db.session import get_session_factory
from backend.app.ingest.sec_client import SECClient
from backend.app.ingest.text_extractor import FilingTextExtractor
from backend.app.nlp.narrative_drift import NarrativeDriftAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("finguard.sprint_a.text_nlp")


def build_submissions_index(
    submissions_zip_path: Path, needed_ciks: Set[str]
) -> Dict[str, Dict[str, str]]:
    """Build a mapping of (cik -> {accession_number -> primaryDocument}) from submissions.zip."""
    logger.info(f"Indexing submissions.zip for {len(needed_ciks)} CIKs...")
    cik_map: Dict[str, Dict[str, str]] = {}
    with zipfile.ZipFile(submissions_zip_path, "r") as zf:
        name_list = set(zf.namelist())
        for cik in needed_ciks:
            fn = f"CIK{cik}.json"
            if fn not in name_list:
                continue
            try:
                data = json.loads(zf.read(fn))
                acc_to_doc = {}
                recent = data.get("filings", {}).get("recent", {})
                accns = recent.get("accessionNumber", [])
                pdocs = recent.get("primaryDocument", [])
                for acc, doc in zip(accns, pdocs):
                    if doc:
                        acc_to_doc[acc] = doc

                # Also inspect older submission files if present
                for f_meta in data.get("filings", {}).get("files", []):
                    f_name = f_meta.get("name")
                    if f_name and f_name in name_list:
                        old_d = json.loads(zf.read(f_name))
                        old_accns = old_d.get("accessionNumber", [])
                        old_pdocs = old_d.get("primaryDocument", [])
                        for acc, doc in zip(old_accns, old_pdocs):
                            if doc:
                                acc_to_doc[acc] = doc

                cik_map[cik] = acc_to_doc
            except Exception as e:
                logger.warning(f"Error parsing CIK{cik}.json: {e}")

    logger.info(f"Indexed submissions for {len(cik_map)} CIKs.")
    return cik_map


def run_text_and_nlp_pipeline():
    """Execute Sprint A2 and A3 pipeline."""
    settings = get_settings()
    session_factory = get_session_factory()
    db = session_factory()

    client = SECClient(max_rate_per_sec=5.0)
    extractor = FilingTextExtractor()
    analyzer = NarrativeDriftAnalyzer()

    # 1. Fetch all labeled company-years (positives + matched controls)
    logger.info("Loading labeled company-year set...")
    labels = db.execute(
        select(CompanyYearLabel).order_by(CompanyYearLabel.id)
    ).scalars().all()
    logger.info(f"Found {len(labels)} labeled company-year records.")

    # Distinct (cik, fiscal_year) pairs in labeled cohort
    labeled_pairs = {(lbl.cik, lbl.fiscal_year) for lbl in labels}
    ciks_needed = {lbl.cik for lbl in labels}
    logger.info(f"Unique CIKs in labeled set: {len(ciks_needed)}")
    logger.info(f"Unique (CIK, FY) pairs in labeled set: {len(labeled_pairs)}")

    # 2. Identify current filings and prior-year filings
    # Query filings for these CIKs and fiscal_years (both FY and FY-1)
    filing_query = text("""
        SELECT f.id, f.cik, f.fiscal_year, f.accession_number, f.filing_date, f.primary_document
        FROM filings f
        WHERE f.cik IN :ciks AND f.form_type = '10-K' AND f.is_amendment = false
    """)
    all_filings = db.execute(filing_query, {"ciks": tuple(ciks_needed)}).fetchall()

    filing_lookup: Dict[Tuple[str, int], Any] = {}
    for f in all_filings:
        # Keep earliest filing if multiple
        key = (f.cik, f.fiscal_year)
        if key not in filing_lookup or f.filing_date < filing_lookup[key].filing_date:
            filing_lookup[key] = f

    # Filings needed: current year (for labeled_pairs) + prior year (fiscal_year - 1)
    needed_filing_keys = set()
    for cik, fy in labeled_pairs:
        needed_filing_keys.add((cik, fy))
        needed_filing_keys.add((cik, fy - 1))

    filings_to_process = [filing_lookup[k] for k in needed_filing_keys if k in filing_lookup]
    logger.info(f"Identified {len(filings_to_process)} unique 10-K filings to extract.")

    # 3. Resolve primary documents from submissions.zip
    sub_index = build_submissions_index(
        settings.RAW_DIR / "submissions.zip", ciks_needed
    )

    # 4. Fetch 10-K HTML and extract sections
    logger.info("Starting filing fetch and section extraction (Sprint A2)...")
    sections_extracted: Dict[str, int] = {"mda": 0, "risk_factors": 0, "related_party": 0}
    sections_attempted = len(filings_to_process)
    sec_cache_hits = 0
    sec_fetch_errors = 0

    # Cache of extracted sections in memory: key (cik, fiscal_year) -> {section_type: section_dict}
    extracted_filing_sections: Dict[Tuple[str, int], Dict[str, Any]] = {}

    # Load already extracted sections from DB
    existing_sections = db.execute(
        text("SELECT cik, fiscal_year, section_type, text, source_location, extraction_status FROM filing_sections")
    ).fetchall()
    for row in existing_sections:
        key = (row.cik, row.fiscal_year)
        if key not in extracted_filing_sections:
            extracted_filing_sections[key] = {}
        extracted_filing_sections[key][row.section_type] = {
            "text": row.text,
            "source_location": row.source_location,
            "status": row.extraction_status,
        }
        if row.extraction_status == "success":
            sections_extracted[row.section_type] = sections_extracted.get(row.section_type, 0) + 1

    logger.info(f"Loaded {len(extracted_filing_sections)} filings from database filing_sections.")

    start_time = time.time()
    for i, f in enumerate(filings_to_process):
        if (f.cik, f.fiscal_year) in extracted_filing_sections:
            continue

        cik_int = int(f.cik)
        acc_no_hyphens = f.accession_number.replace("-", "")
        pdoc = f.primary_document or sub_index.get(f.cik, {}).get(f.accession_number)

        if not pdoc:
            logger.warning(f"[{i+1}/{len(filings_to_process)}] No primaryDocument for {f.cik} {f.accession_number}")
            continue

        # If primary_document was missing in DB, update it
        if not f.primary_document:
            db.execute(
                text("UPDATE filings SET primary_document = :pdoc WHERE id = :fid"),
                {"pdoc": pdoc, "fid": f.id},
            )

        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_hyphens}/{pdoc}"
        try:
            resp = client.get(url, db_session=db)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} on {url}")
                sec_fetch_errors += 1
                continue
            html_text = resp.text
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            sec_fetch_errors += 1
            continue

        # Extract sections
        sections = extractor.extract_sections(html_text)
        extracted_filing_sections[(f.cik, f.fiscal_year)] = sections

        # Record section counts
        for sec_type, sec_data in sections.items():
            if sec_data["status"] == "success":
                sections_extracted[sec_type] += 1

            # Insert/update filing_sections in DB
            text_body = sec_data["text"]
            words = text_body.split() if text_body else []
            stmt = pg_insert(FilingSection).values(
                filing_id=f.id,
                cik=f.cik,
                fiscal_year=f.fiscal_year,
                accession_number=f.accession_number,
                section_type=sec_type,
                text=text_body,
                char_count=len(text_body) if text_body else 0,
                word_count=len(words),
                sentence_count=len(sec_data.get("sentences", [])) if "sentences" in sec_data else 0,
                source_location=sec_data.get("source_location"),
                extraction_status=sec_data.get("status", "not_found"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["cik", "fiscal_year", "section_type"],
                set_={
                    "text": stmt.excluded.text,
                    "char_count": stmt.excluded.char_count,
                    "word_count": stmt.excluded.word_count,
                    "source_location": stmt.excluded.source_location,
                    "extraction_status": stmt.excluded.extraction_status,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            db.execute(stmt)

        if (i + 1) % 50 == 0 or (i + 1) == len(filings_to_process):
            db.commit()
            elapsed = time.time() - start_time
            logger.info(
                f"[{i+1}/{len(filings_to_process)}] Filings processed ({elapsed:.1f}s). "
                f"MDA: {sections_extracted['mda']}/{i+1} ({sections_extracted['mda']/(i+1)*100:.1f}%), "
                f"Risk: {sections_extracted['risk_factors']}/{i+1} ({sections_extracted['risk_factors']/(i+1)*100:.1f}%), "
                f"RP: {sections_extracted['related_party']}/{i+1} ({sections_extracted['related_party']/(i+1)*100:.1f}%)"
            )

    db.commit()
    logger.info("Sprint A2 Filing Text Extraction complete.")

    # 5. Compute NLP Narrative Drift & Linguistic Features (Sprint A3)
    import torch
    torch.set_num_threads(4)

    logger.info("Starting NLP Narrative Drift computation (Sprint A3)...")
    existing_nlp = set(
        db.execute(text("SELECT cik, fiscal_year FROM filing_nlp_features")).fetchall()
    )
    logger.info(f"Loaded {len(existing_nlp)} already computed NLP feature rows.")

    nlp_records = []
    nlp_drift_scores = []
    # Seed with existing scores
    for row in db.execute(text("SELECT narrative_drift_score FROM filing_nlp_features WHERE narrative_drift_score IS NOT NULL")).fetchall():
        nlp_drift_scores.append(row[0])

    sample_snippets = []

    for i, (cik, fy) in enumerate(sorted(labeled_pairs)):
        if (cik, fy) in existing_nlp:
            continue

        curr_filing = filing_lookup.get((cik, fy))
        prior_filing = filing_lookup.get((cik, fy - 1))

        if not curr_filing:
            continue

        curr_sections = extracted_filing_sections.get((cik, fy), {})
        prior_sections = extracted_filing_sections.get((cik, fy - 1), {})

        curr_mda = curr_sections.get("mda", {}).get("text")
        prior_mda = prior_sections.get("mda", {}).get("text")

        curr_risk = curr_sections.get("risk_factors", {}).get("text")
        prior_risk = prior_sections.get("risk_factors", {}).get("text")

        # Run drift on MD&A
        if curr_mda:
            drift_res = analyzer.analyze_drift(
                curr_text=curr_mda,
                prior_text=prior_mda,
                source_location=curr_sections.get("mda", {}).get("source_location"),
            )
        else:
            # Fallback if no MD&A
            drift_res = {
                "narrative_drift_score": None,
                "doc_embedding_cosine_drift": None,
                "vocab_jaccard_distance": None,
                "drift_evidence_snippets": [],
                "uncertainty_rate": None,
                "negative_sentiment_rate": None,
                "financial_uncertainty_rate": None,
                "avg_sentence_length": None,
                "readability_fog_index": None,
                "conditional_language_rate": None,
                "passive_voice_rate": None,
                "numeric_density": None,
            }

        # Also compute risk drift if available
        risk_drift_score = None
        if curr_risk and prior_risk:
            try:
                r_res = analyzer.analyze_drift(curr_text=curr_risk[:25000], prior_text=prior_risk[:25000])
                risk_drift_score = r_res.get("narrative_drift_score")
            except Exception:
                risk_drift_score = None

        if drift_res.get("narrative_drift_score") is not None:
            nlp_drift_scores.append(drift_res["narrative_drift_score"])

        # Capture evidence snippets
        if drift_res.get("drift_evidence_snippets") and len(sample_snippets) < 5:
            for snip in drift_res["drift_evidence_snippets"]:
                sample_snippets.append({
                    "cik": cik,
                    "fiscal_year": fy,
                    "accession_number": curr_filing.accession_number,
                    **snip,
                })
                if len(sample_snippets) >= 5:
                    break

        stmt = pg_insert(FilingNLPFeatures).values(
            filing_id=curr_filing.id,
            cik=cik,
            fiscal_year=fy,
            accession_number=curr_filing.accession_number,
            narrative_drift_score=drift_res.get("narrative_drift_score"),
            doc_embedding_cosine_drift=drift_res.get("doc_embedding_cosine_drift"),
            mda_drift_score=drift_res.get("narrative_drift_score"),
            risk_drift_score=risk_drift_score,
            vocab_jaccard_distance=drift_res.get("vocab_jaccard_distance"),
            uncertainty_rate=drift_res.get("uncertainty_rate"),
            negative_sentiment_rate=drift_res.get("negative_sentiment_rate"),
            financial_uncertainty_rate=drift_res.get("financial_uncertainty_rate"),
            avg_sentence_length=drift_res.get("avg_sentence_length"),
            readability_fog_index=drift_res.get("readability_fog_index"),
            conditional_language_rate=drift_res.get("conditional_language_rate"),
            passive_voice_rate=drift_res.get("passive_voice_rate"),
            numeric_density=drift_res.get("numeric_density"),
            drift_evidence_snippets=drift_res.get("drift_evidence_snippets", []),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["cik", "fiscal_year"],
            set_={
                "narrative_drift_score": stmt.excluded.narrative_drift_score,
                "doc_embedding_cosine_drift": stmt.excluded.doc_embedding_cosine_drift,
                "mda_drift_score": stmt.excluded.mda_drift_score,
                "risk_drift_score": stmt.excluded.risk_drift_score,
                "vocab_jaccard_distance": stmt.excluded.vocab_jaccard_distance,
                "uncertainty_rate": stmt.excluded.uncertainty_rate,
                "negative_sentiment_rate": stmt.excluded.negative_sentiment_rate,
                "financial_uncertainty_rate": stmt.excluded.financial_uncertainty_rate,
                "avg_sentence_length": stmt.excluded.avg_sentence_length,
                "readability_fog_index": stmt.excluded.readability_fog_index,
                "conditional_language_rate": stmt.excluded.conditional_language_rate,
                "passive_voice_rate": stmt.excluded.passive_voice_rate,
                "numeric_density": stmt.excluded.numeric_density,
                "drift_evidence_snippets": stmt.excluded.drift_evidence_snippets,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        db.execute(stmt)

        if (i + 1) % 25 == 0 or (i + 1) == len(labeled_pairs):
            db.commit()
            logger.info(f"[{i+1}/{len(labeled_pairs)}] NLP features populated. "
                        f"Computed drift scores: {len(nlp_drift_scores)}")

    db.commit()
    logger.info("Sprint A3 NLP Pipeline complete.")

    # 6. Generate summary statistics for report
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_filings_attempted": sections_attempted,
        "section_extraction": {
            "mda_success_count": sections_extracted["mda"],
            "mda_success_rate": round(sections_extracted["mda"] / max(sections_attempted, 1) * 100, 2),
            "risk_factors_success_count": sections_extracted["risk_factors"],
            "risk_factors_success_rate": round(sections_extracted["risk_factors"] / max(sections_attempted, 1) * 100, 2),
            "related_party_success_count": sections_extracted["related_party"],
            "related_party_success_rate": round(sections_extracted["related_party"] / max(sections_attempted, 1) * 100, 2),
        },
        "labeled_cohort_nlp": {
            "total_labeled_company_years": len(labeled_pairs),
            "drift_score_computed_count": len(nlp_drift_scores),
            "drift_score_computed_rate": round(len(nlp_drift_scores) / max(len(labeled_pairs), 1) * 100, 2),
            "drift_score_stats": {
                "min": round(float(min(nlp_drift_scores)), 4) if nlp_drift_scores else None,
                "median": round(float(sorted(nlp_drift_scores)[len(nlp_drift_scores)//2]), 4) if nlp_drift_scores else None,
                "max": round(float(max(nlp_drift_scores)), 4) if nlp_drift_scores else None,
            },
        },
        "drift_evidence_snippets_sample": sample_snippets[:3],
    }

    out_file = Path("data/processed/sprint_a_nlp_summary.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Summary written to {out_file}")
    db.close()


if __name__ == "__main__":
    run_text_and_nlp_pipeline()
