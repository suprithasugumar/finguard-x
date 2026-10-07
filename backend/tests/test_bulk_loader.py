"""Tests for BulkLoader streaming extraction and manifest tracking."""

import json
import zipfile

from backend.app.ingest.bulk_loader import BulkLoader


def test_bulk_loader_manifest_and_streaming(tmp_path, db_session):
    """Verify manifest creation and streaming extraction of company submissions."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    loader = BulkLoader(raw_dir=raw_dir)

    # 1. Manifest initialization
    manifest = loader.get_manifest()
    assert "files" in manifest
    manifest["files"]["test.zip"] = {"sha256": "abc", "size_bytes": 100}
    loader.save_manifest(manifest)
    reloaded = loader.get_manifest()
    assert "test.zip" in reloaded["files"]

    # 2. Mock submissions.zip with primary and older filings
    zip_path = raw_dir / "submissions.zip"
    primary_data = {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "fiscalYearEnd": "0930",
        "formerNames": [{"name": "Apple Computer Inc."}],
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["0000320193-23-000100"],
                "filingDate": ["2023-10-27"],
                "reportDate": ["2023-09-30"],
                "primaryDocument": ["aapl-20230930.htm"],
            }
        },
    }
    older_data = {
        "form": ["10-K"],
        "accessionNumber": ["0000320193-22-000100"],
        "filingDate": ["2022-10-28"],
        "reportDate": ["2022-09-24"],
        "primaryDocument": ["aapl-20220924.htm"],
    }

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("CIK0000320193.json", json.dumps(primary_data))
        zf.writestr("CIK0000320193-submissions-001.json", json.dumps(older_data))

    # 3. Stream and load
    comp_count, fil_count, lookup = loader.load_companies_and_filings(zip_path, db_session)
    assert comp_count == 1
    assert fil_count == 2  # Recent + older merged filing
    assert "apple" in lookup
    assert "Apple Computer Inc." in lookup["apple"]["former_names"]
