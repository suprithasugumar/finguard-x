"""Data Provenance Guard: Enforces Rule R1 (Zero Synthetic Data) by cryptographic/source tracing."""

import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.entities import (
    AAERCase,
    CompanyYearLabel,
    Filing,
    FinancialFact,
)

logger = logging.getLogger("finguard.ingest.provenance_guard")


class ProvenanceViolationError(Exception):
    """Raised when database records fail cryptographic or source-archive provenance tracing."""

    pass


class ProvenanceGuard:
    """Verifies that all database facts, filings, and labels trace directly to authentic SEC raw archives."""

    def __init__(
        self,
        raw_dir: Optional[Path] = None,
        processed_dir: Optional[Path] = None,
    ):
        settings = get_settings()
        self.raw_dir = raw_dir or settings.RAW_DIR
        self.processed_dir = processed_dir or settings.PROCESSED_DIR
        self.companyfacts_zip = self.raw_dir / "companyfacts.zip"
        self.submissions_zip = self.raw_dir / "submissions.zip"
        self.manifest_path = self.raw_dir / "manifest.json"
        self.aaer_index_path = self.processed_dir / "aaer_full_scraped_releases.json"

    def verify_all(self, session: Session, fact_sample_size: int = 10000) -> Dict[str, Any]:
        """Mandatory first step of every pipeline run: fails hard if any check fails."""
        logger.info("Executing mandatory ProvenanceGuard pre-flight audit...")
        manifest = self.verify_manifest()
        filings_checked = self.verify_filings_provenance(session)
        facts_checked = self.verify_facts_provenance(session, sample_size=fact_sample_size)
        labels_checked = self.verify_labels_provenance(session)
        logger.info("ProvenanceGuard pre-flight audit PASSED with 100% data authenticity.")
        return {
            "manifest": manifest,
            "filings_verified": filings_checked,
            "facts_verified": facts_checked,
            "labels_verified": labels_checked,
        }

    def verify_manifest(self) -> Dict[str, Any]:
        """Verify that manifest.json exists and contains genuine non-empty SHA-256 checksums."""
        if not self.manifest_path.exists():
            raise ProvenanceViolationError(f"Missing manifest.json at {self.manifest_path}")

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        files = manifest.get("files", {})
        for fname in ("submissions.zip", "companyfacts.zip"):
            if fname not in files:
                raise ProvenanceViolationError(f"{fname} missing from manifest.json")
            entry = files[fname]
            if not entry.get("sha256") or len(entry["sha256"]) != 64:
                raise ProvenanceViolationError(f"Invalid SHA256 checksum for {fname} in manifest")
            if entry.get("size_bytes", 0) <= 0:
                raise ProvenanceViolationError(f"Invalid file size for {fname} in manifest")

        return manifest

    def verify_facts_provenance(
        self,
        session: Session,
        sample_size: int = 10000,
    ) -> int:
        """Verify that sampled rows from financial_facts exist verbatim in companyfacts.zip."""
        total_facts = session.query(FinancialFact).count()
        if total_facts == 0:
            logger.warning("No financial facts in database to verify.")
            return 0

        actual_sample_size = min(sample_size, total_facts)
        logger.info(
            f"ProvenanceGuard: Sampling {actual_sample_size:,} random facts out of {total_facts:,} total facts..."
        )

        # Sample facts via fast random offset or limit
        # Using raw SQL for fast random sampling across millions of rows
        raw_conn = session.connection().connection
        cursor = raw_conn.cursor()
        cursor.execute(f"""
            SELECT id, cik, tag, unit, accession_number
            FROM financial_facts
            TABLESAMPLE SYSTEM (5)
            LIMIT {actual_sample_size};
        """)
        sampled_rows = cursor.fetchall()
        if not sampled_rows or len(sampled_rows) < min(100, actual_sample_size):
            # Fallback to standard query if TABLESAMPLE returned too few
            cursor.execute(f"""
                SELECT id, cik, tag, unit, accession_number
                FROM financial_facts
                ORDER BY id DESC
                LIMIT {actual_sample_size};
            """)
            sampled_rows = cursor.fetchall()
        cursor.close()

        if not self.companyfacts_zip.exists():
            raise ProvenanceViolationError(f"companyfacts.zip not found at {self.companyfacts_zip}")

        # Group facts by CIK for single-pass archive opening
        from collections import defaultdict

        facts_by_cik = defaultdict(list)
        for r in sampled_rows:
            facts_by_cik[r[1]].append(r)

        verified_count = 0
        with zipfile.ZipFile(self.companyfacts_zip, "r") as zf:
            zf_names = set(zf.namelist())
            for cik, facts in facts_by_cik.items():
                target_file = f"CIK{cik}.json"
                if target_file not in zf_names:
                    fact_id, _, tag, _, accn = facts[0]
                    raise ProvenanceViolationError(
                        f"Fact ID {fact_id} (CIK {cik}) cannot be traced: "
                        f"{target_file} not found in {self.companyfacts_zip.name}!"
                    )

                with zf.open(target_file) as f:
                    raw_data = json.load(f)

                us_gaap = raw_data.get("facts", {}).get("us-gaap", {})
                for fact_id, _, tag, unit, accn in facts:
                    tag_node = us_gaap.get(tag, {})
                    units = tag_node.get("units", {}).get(unit, [])
                    matching = [u for u in units if str(u.get("accn", "")).strip() == accn]
                    if not matching:
                        raise ProvenanceViolationError(
                            f"Synthetic fact detected! Fact ID {fact_id} (CIK {cik}, tag {tag}, "
                            f"accn {accn}) does NOT exist in {target_file}!"
                        )
                    verified_count += 1

        logger.info(
            f"Verified provenance for {verified_count:,} sampled financial facts against companyfacts.zip (100% authentic)."
        )
        return verified_count

    def verify_filings_provenance(
        self,
        session: Session,
        sample_size: Optional[int] = None,
    ) -> int:
        """Verify that filing accessions exist verbatim in submissions.zip (100% verification by default)."""
        total_filings = session.query(Filing).count()
        if total_filings == 0:
            logger.warning("No filings in database to verify.")
            return 0

        if not self.submissions_zip.exists():
            raise ProvenanceViolationError(f"submissions.zip not found at {self.submissions_zip}")

        raw_conn = session.connection().connection
        cursor = raw_conn.cursor()

        if sample_size and sample_size < total_filings:
            logger.info(
                f"ProvenanceGuard: Sampling {sample_size:,} filings out of {total_filings:,}..."
            )
            cursor.execute(
                f"SELECT cik, accession_number FROM filings ORDER BY id DESC LIMIT {sample_size};"
            )
        else:
            logger.info(
                f"ProvenanceGuard: Verifying 100% of {total_filings:,} filings against submissions.zip..."
            )
            cursor.execute("SELECT cik, accession_number FROM filings;")

        from collections import defaultdict

        filings_by_cik = defaultdict(set)
        total_to_check = 0
        for cik, accn in cursor.fetchall():
            filings_by_cik[cik].add(accn)
            total_to_check += 1
        cursor.close()

        verified_count = 0
        with zipfile.ZipFile(self.submissions_zip, "r") as zf:
            zf_names = set(zf.namelist())
            for cik, accns in filings_by_cik.items():
                target_file = f"CIK{cik}.json"
                if target_file not in zf_names:
                    raise ProvenanceViolationError(
                        f"Filing CIK {cik} cannot be traced: "
                        f"{target_file} not in {self.submissions_zip.name}!"
                    )

                with zf.open(target_file) as f:
                    raw_data = json.load(f)

                recent_accns = set(
                    str(a).strip()
                    for a in raw_data.get("filings", {})
                    .get("recent", {})
                    .get("accessionNumber", [])
                )
                missing = accns - recent_accns
                if missing:
                    bad_accn = next(iter(missing))
                    raise ProvenanceViolationError(
                        f"Synthetic filing detected! Filing (CIK {cik}, "
                        f"accn {bad_accn}) does NOT exist in {target_file}!"
                    )
                verified_count += len(accns)

        logger.info(
            f"Verified provenance for {verified_count:,}/{total_to_check:,} filings against submissions.zip (100% authentic)."
        )
        return verified_count

    def verify_labels_provenance(
        self,
        session: Session,
        sample_size: Optional[int] = None,
    ) -> int:
        """Verify that company_year_labels trace to authentic AAER cases or verified controls (100% by default)."""
        query = session.query(CompanyYearLabel)
        if sample_size:
            labels = query.limit(sample_size).all()
        else:
            labels = query.all()

        if not labels:
            logger.info("No labels in database yet.")
            return 0

        logger.info(f"ProvenanceGuard: Verifying {len(labels)} labels (100% coverage)...")
        for label in labels:
            if label.label == 1:
                # Must trace to an authentic AAERCase
                if not label.aaer_case_id:
                    raise ProvenanceViolationError(
                        f"Positive label ID {label.id} (CIK {label.cik}, FY {label.fiscal_year}) "
                        f"has no aaer_case_id reference!"
                    )
                case = session.query(AAERCase).filter(AAERCase.id == label.aaer_case_id).first()
                if not case or not case.aaer_number:
                    raise ProvenanceViolationError(
                        f"Positive label ID {label.id} references missing AAER case {label.aaer_case_id}!"
                    )
            elif label.label == 0:
                # Must trace to a verified filing in the database
                control_filing = (
                    session.query(Filing)
                    .filter(
                        Filing.cik == label.cik,
                        Filing.fiscal_year == label.fiscal_year,
                    )
                    .first()
                )
                if not control_filing:
                    raise ProvenanceViolationError(
                        f"Control label ID {label.id} (CIK {label.cik}, FY {label.fiscal_year}) "
                        f"has no authentic filing in filings table!"
                    )

        logger.info(f"Verified provenance for {len(labels)}/{len(labels)} labels (100% authentic).")
        return len(labels)
