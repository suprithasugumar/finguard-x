import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models.graph import CompanyYearGraphFeatures
from backend.app.graph.knowledge_graph import RelatedPartyGraphExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("finguard.stage1.graph")


def populate_graph_features():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    extractor = RelatedPartyGraphExtractor()

    logger.info("Initializing Stage 1: Knowledge Graph Population...")

    with Session(engine) as session:
        # Load all cohort company-years ordered by cik, fiscal_year
        cohort_rows = session.execute(
            text("""
                SELECT DISTINCT ON (cyl.cik, cyl.fiscal_year)
                    cyl.cik,
                    cyl.fiscal_year,
                    COALESCE(f.accession_number, '') as accession_number,
                    f.id as filing_id,
                    c.name as company_name,
                    cyl.label
                FROM company_year_labels cyl
                JOIN companies c ON c.cik = cyl.cik
                LEFT JOIN filings f ON f.cik = cyl.cik AND f.fiscal_year = cyl.fiscal_year AND f.form_type = '10-K'
                ORDER BY cyl.cik, cyl.fiscal_year ASC
            """)
        ).fetchall()

        total_cohort = len(cohort_rows)
        logger.info(f"Loaded {total_cohort} cohort company-years to process.")

        # Pre-fetch all related_party texts and item_13 texts from filing_sections
        section_rows = session.execute(
            text("""
                SELECT cik, fiscal_year, text
                FROM filing_sections
                WHERE section_type = 'related_party' AND text IS NOT NULL AND length(text) > 50
            """)
        ).fetchall()
        text_map = {(r[0], r[1]): r[2] for r in section_rows}
        logger.info(f"Loaded {len(text_map)} related-party text disclosures.")

        item13_rows = session.execute(
            text("""
                SELECT cik, fiscal_year, text
                FROM filing_sections
                WHERE section_type = 'item_13' AND text IS NOT NULL AND length(text) > 20
            """)
        ).fetchall()
        item13_map = {(r[0], r[1]): r[2] for r in item13_rows}
        logger.info(f"Loaded {len(item13_map)} Item 13 disclosures.")

        # Clean existing rows
        session.execute(text("DELETE FROM company_year_graph_features"))
        session.commit()

        # Prior graphs dictionary: cik -> prior NetworkX graph
        prior_graphs = {}
        
        usable_count = 0
        total_nodes_all = 0
        total_edges_all = 0
        total_shells_all = 0
        state_counts = {"graph_built": 0, "note_found_extraction_failed": 0, "note_by_reference": 0, "no_note_disclosed": 0}
        real_examples = []

        batch_to_insert = []

        import re

        for idx, row in enumerate(cohort_rows, 1):
            cik = row.cik
            fy = row.fiscal_year
            acc = row.accession_number
            filing_id = row.filing_id
            company_name = row.company_name or "Registrant"
            label = row.label

            related_party_text = text_map.get((cik, fy))
            item13_text = item13_map.get((cik, fy))
            prior_g = prior_graphs.get(cik)

            # Build graph and compute topological features
            G, feats = extractor.extract_graph(company_name, related_party_text, prior_graph=prior_g)
            
            # Save G as prior graph for next year
            if G.number_of_nodes() > 1:
                prior_graphs[cik] = G

            # Determine 4 distinct related-party states:
            # (d) graph_built
            # (c) note_found_extraction_failed
            # (b) note_by_reference
            # (a) no_note_disclosed
            if feats["graph_available"] and feats["num_nodes"] > 1:
                rp_state = "graph_built"
            elif related_party_text and len(related_party_text.strip()) > 50:
                rp_state = "note_found_extraction_failed"
            elif item13_text:
                if re.search(r'incorporat.*reference|proxy statement|definitive proxy|item 13|part iii', item13_text, re.I):
                    rp_state = "note_by_reference"
                else:
                    rp_state = "no_note_disclosed"
            else:
                rp_state = "no_note_disclosed"

            state_counts[rp_state] += 1

            if feats["graph_available"]:
                usable_count += 1
                total_nodes_all += feats["num_nodes"]
                total_edges_all += feats["num_edges"]
                total_shells_all += feats["num_undisclosed_or_shell"]
                
                if len(real_examples) < 5 and feats["evidence_edges"]:
                    real_examples.append({
                        "cik": cik,
                        "company": company_name,
                        "fiscal_year": fy,
                        "label": label,
                        "nodes": feats["num_nodes"],
                        "edges": feats["num_edges"],
                        "shells": feats["num_undisclosed_or_shell"],
                        "anomaly_score": feats["graph_anomaly_score"],
                        "evidence": feats["evidence_edges"][0],
                    })

            payload = feats["graph_payload"] or {"nodes": [], "edges": []}
            payload["related_party_state"] = rp_state

            record = CompanyYearGraphFeatures(
                filing_id=filing_id,
                cik=cik,
                fiscal_year=fy,
                accession_number=acc,
                graph_available=feats["graph_available"],
                graph_size=feats["graph_size"],
                related_party_state=rp_state,
                num_nodes=feats["num_nodes"],
                num_edges=feats["num_edges"],
                density=feats["density"],
                avg_degree=feats["avg_degree"],
                num_officers=feats["num_officers"],
                num_entities=feats["num_entities"],
                num_undisclosed_or_shell=feats["num_undisclosed_or_shell"],
                max_clique_size=feats["max_clique_size"],
                clustering_coefficient=feats["clustering_coefficient"],
                betweenness_centrality_max=feats["betweenness_centrality_max"],
                yoy_node_churn=feats["yoy_node_churn"],
                yoy_edge_churn=feats["yoy_edge_churn"],
                graph_anomaly_score=feats["graph_anomaly_score"],
                graph_payload=payload,
                evidence_edges=feats["evidence_edges"],
            )
            batch_to_insert.append(record)

            if len(batch_to_insert) >= 100:
                session.add_all(batch_to_insert)
                session.commit()
                batch_to_insert = []
                logger.info(f"Processed {idx}/{total_cohort} ({usable_count} usable graphs so far)...")

        if batch_to_insert:
            session.add_all(batch_to_insert)
            session.commit()

        usable_pct = (usable_count / total_cohort) * 100.0
        logger.info(f"Stage 1 Graph Population Complete!")
        logger.info(f"Total cohort: {total_cohort}")
        logger.info(f"Usable graphs (graph_available=True): {usable_count} ({usable_pct:.2f}%)")
        logger.info(f"Total nodes extracted: {total_nodes_all}, Total edges: {total_edges_all}, Shells: {total_shells_all}")
        
        logger.info("--- 3 REAL EVIDENCE EXAMPLES ---")
        for i, ex in enumerate(real_examples[:3], 1):
            logger.info(
                f"Example {i}: {ex['company']} (CIK {ex['cik']}, FY{ex['fiscal_year']}, Label={ex['label']}) | "
                f"Nodes={ex['nodes']}, Edges={ex['edges']}, Shells={ex['shells']}, AnomalyScore={ex['anomaly_score']:.4f}\n"
                f"  Edge: {ex['evidence']['source']} <-> {ex['evidence']['target']} ({ex['evidence']['relation']})\n"
                f"  Evidence: \"{ex['evidence']['evidence_sentence'][:200]}...\"\n"
            )

        # Output summary json for docs/PROGRESS.md
        summary = {
            "total_cohort": total_cohort,
            "usable_graphs": usable_count,
            "usable_pct": usable_pct,
            "total_nodes": total_nodes_all,
            "total_edges": total_edges_all,
            "total_shells": total_shells_all,
            "examples": real_examples[:3],
        }
        with open("data/processed/stage1_graph_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    populate_graph_features()
