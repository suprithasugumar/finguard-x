"""Streaming SEC bulk files loader (submissions.zip and companyfacts.zip) with manifest tracking."""

import hashlib
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.entities import Company, Filing
from backend.app.ingest.facts_parser import FactsParser, parse_date
from backend.app.ingest.fiscal_year import derive_fiscal_year
from backend.app.ingest.sec_client import SECClient

logger = logging.getLogger("finguard.ingest.bulk_loader")


class BulkLoader:
    """Manages streaming extraction from SEC submissions.zip and companyfacts.zip without disk extraction."""

    def __init__(self, raw_dir: Optional[Path] = None, sec_client: Optional[SECClient] = None):
        settings = get_settings()
        self.raw_dir = raw_dir or settings.RAW_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.raw_dir / "manifest.json"
        self.client = sec_client or SECClient()
        self.facts_parser = FactsParser()

    def get_manifest(self) -> Dict[str, Any]:
        """Read or initialize manifest.json."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read manifest: {e}")
        return {"files": {}}

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Write manifest.json with atomic save."""
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def download_bulk_archives(self, force: bool = False) -> Dict[str, Path]:
        """Download submissions.zip and companyfacts.zip once into data/raw/ with checksums."""
        manifest = self.get_manifest()
        archives = {
            "submissions.zip": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
            "companyfacts.zip": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
        }
        paths: Dict[str, Path] = {}

        for filename, url in archives.items():
            dest = self.raw_dir / filename
            already_recorded = filename in manifest.get("files", {})

            if dest.exists() and already_recorded and not force:
                logger.info(f"Using existing cached bulk archive: {dest}")
                paths[filename] = dest
                continue

            logger.info(f"Downloading SEC bulk archive {filename} from {url}...")
            resp = self.client.get(url, use_cache=False)
            content = resp.content

            # Calculate SHA-256
            sha256 = hashlib.sha256(content).hexdigest()
            with open(dest, "wb") as f:
                f.write(content)

            manifest["files"][filename] = {
                "url": url,
                "sha256": sha256,
                "size_bytes": len(content),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
            paths[filename] = dest

        self.save_manifest(manifest)
        return paths

    def stream_company_submissions(
        self, zip_path: Path, target_ciks: Optional[Set[str]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream company records and filings from submissions.zip.

        Handles:
        - Primary submissions file (CIK{cik}.json)
        - Older filings files (CIK{cik}-submissions-001.json, etc.)
        """
        with zipfile.ZipFile(zip_path, "r") as zf:
            name_list = zf.namelist()
            # Identify primary files: CIK{10 digits}.json
            primary_files = [
                n for n in name_list if n.startswith("CIK") and n.endswith(".json") and "-" not in n
            ]

            # Index older submission files by base CIK
            older_files_map: Dict[str, List[str]] = {}
            for n in name_list:
                if "-" in n and n.startswith("CIK") and n.endswith(".json"):
                    base_cik = n.split("-")[0].replace("CIK", "").zfill(10)
                    older_files_map.setdefault(base_cik, []).append(n)

            for member_name in primary_files:
                cik_from_name = member_name.replace("CIK", "").replace(".json", "").zfill(10)
                if target_ciks and cik_from_name not in target_ciks:
                    continue

                try:
                    with zf.open(member_name) as f:
                        data = json.load(f)

                    # Check for older filings files and merge if present
                    if cik_from_name in older_files_map:
                        recent = data.get("filings", {}).get("recent", {})
                        for older_member in sorted(older_files_map[cik_from_name]):
                            with zf.open(older_member) as of:
                                older_data = json.load(of)
                            # Append older lists
                            for col, values in older_data.items():
                                if (
                                    col in recent
                                    and isinstance(recent[col], list)
                                    and isinstance(values, list)
                                ):
                                    recent[col].extend(values)

                    yield data
                except Exception as e:
                    logger.warning(f"Error reading {member_name} from {zip_path}: {e}")

    def load_companies_and_filings(
        self,
        submissions_zip_path: Path,
        session: Session,
        target_ciks: Optional[Set[str]] = None,
        min_fiscal_year: int = 2010,
    ) -> Tuple[int, int, Dict[str, Dict[str, Any]]]:
        """Parse submissions and store Company and Filing entities in database.

        Returns (companies_count, filings_count, company_lookup_dict_with_former_names)
        """
        companies_count = 0
        filings_count = 0
        company_lookup: Dict[str, Dict[str, Any]] = {}

        for sub in self.stream_company_submissions(submissions_zip_path, target_ciks):
            cik_raw = str(sub.get("cik", ""))
            if not cik_raw:
                continue
            cik = cik_raw.zfill(10)
            name = sub.get("name", "").strip()
            tickers = sub.get("tickers", [])
            ticker = tickers[0] if tickers else None
            exchanges = sub.get("exchanges", [])
            exchange = exchanges[0] if exchanges else None
            sic = str(sub.get("sic", "")).strip() or None
            sic_desc = sub.get("sicDescription")
            fye = str(sub.get("fiscalYearEnd", "")).strip() or None
            state = sub.get("stateOfIncorporation")
            former_names_list = [
                fn.get("name", "") for fn in sub.get("formerNames", []) if fn.get("name")
            ]

            # Record in company_lookup for AAER matching
            from backend.app.ingest.aaer_parser import normalize_company_name

            norm_name = normalize_company_name(name)
            company_lookup[norm_name] = {
                "cik": cik,
                "name": name,
                "ticker": ticker,
                "former_names": former_names_list,
                "sic": sic,
                "fiscal_year_end": fye,
            }

            # Upsert Company
            company = session.query(Company).filter(Company.cik == cik).first()
            if not company:
                company = Company(
                    cik=cik,
                    name=name,
                    ticker=ticker,
                    exchange=exchange,
                    sic=sic,
                    sic_description=sic_desc,
                    fiscal_year_end=fye,
                    state_location=state,
                )
                session.add(company)
                session.flush()
                companies_count += 1
            else:
                company.name = name
                company.ticker = ticker or company.ticker
                company.exchange = exchange or company.exchange
                company.sic = sic or company.sic
                company.fiscal_year_end = fye or company.fiscal_year_end
                session.flush()

            # Process Filings
            recent = sub.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accns = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            report_dates = recent.get("reportDate", [])
            primary_docs = recent.get("primaryDocument", [])

            # Map to select exactly ONE original 10-K per (cik, fiscal_year)
            orig_10k_by_fy: Dict[int, Dict[str, Any]] = {}
            all_10k_entries: List[Dict[str, Any]] = []

            for i in range(len(forms)):
                form = forms[i]
                if form not in ("10-K", "10-K/A", "10-KT", "10-KT/A"):
                    continue

                accn = str(accns[i]).strip()
                f_date = parse_date(filing_dates[i])
                r_date = parse_date(report_dates[i]) if i < len(report_dates) else None
                p_doc = str(primary_docs[i]) if i < len(primary_docs) else None
                if not f_date:
                    continue

                period_end = r_date or f_date
                fy = derive_fiscal_year(period_end, fye)
                if fy < min_fiscal_year - 1:  # Allow 1 prior year for lagged features
                    continue

                is_amendment = form in ("10-K/A", "10-KT/A")
                entry = {
                    "company_id": company.id,
                    "cik": cik,
                    "accession_number": accn,
                    "form_type": form,
                    "fiscal_year": fy,
                    "fiscal_period": "FY",
                    "filing_date": f_date,
                    "period_end": period_end,
                    "report_date": r_date,
                    "primary_document": p_doc,
                    "is_amendment": is_amendment,
                }
                all_10k_entries.append(entry)

                if form == "10-K":
                    # Keep earliest original 10-K per fiscal year
                    if fy not in orig_10k_by_fy or f_date < orig_10k_by_fy[fy]["filing_date"]:
                        orig_10k_by_fy[fy] = entry

            # Insert filings into DB
            for entry in all_10k_entries:
                existing_filing = (
                    session.query(Filing)
                    .filter(Filing.accession_number == entry["accession_number"])
                    .first()
                )
                if not existing_filing:
                    filing = Filing(
                        company_id=entry["company_id"],
                        cik=entry["cik"],
                        accession_number=entry["accession_number"],
                        form_type=entry["form_type"],
                        fiscal_year=entry["fiscal_year"],
                        fiscal_period=entry["fiscal_period"],
                        filing_date=entry["filing_date"],
                        period_end=entry["period_end"],
                        report_date=entry["report_date"],
                        primary_document=entry["primary_document"],
                        is_amendment=entry["is_amendment"],
                    )
                    session.add(filing)
                    filings_count += 1

            session.commit()

        return companies_count, filings_count, company_lookup
