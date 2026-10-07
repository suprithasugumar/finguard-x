"""Verification test for Gate Check 1: Zero new network requests on repeated ingest."""

import httpx
from sqlalchemy import func

from backend.app.db.models.entities import RequestLog
from backend.app.ingest.sec_client import SECClient


def test_zero_network_requests_on_second_ingest(tmp_path, db_session):
    """Verify that a second run makes zero new network requests, served 100% from cache."""
    calls_made = 0

    def mock_server(request: httpx.Request) -> httpx.Response:
        nonlocal calls_made
        calls_made += 1
        return httpx.Response(200, json={"data": "sec_filing_facts", "call": calls_made})

    transport = httpx.MockTransport(mock_server)
    cache_dir = tmp_path / "sec_cache"
    client = SECClient(cache_dir=cache_dir, transport=transport)

    urls = [
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000885590.json",
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000865917.json",
        "https://data.sec.gov/submissions/CIK0000885590.json",
    ]

    # --- Run 1: Initial Ingest ---
    for url in urls:
        resp = client.get(url, use_cache=True, db_session=db_session)
        assert resp.status_code == 200

    assert calls_made == len(urls)

    # Record network requests count
    network_requests_after_run1 = calls_made

    # --- Run 2: Second Ingest ---
    for url in urls:
        resp = client.get(url, use_cache=True, db_session=db_session)
        assert resp.status_code == 200

    # Gate proof: calls_made has NOT increased at all
    assert calls_made == network_requests_after_run1, "Second run must make ZERO new network calls"

    # Verify request_log has recorded cached=True entries
    cached_entries = (
        db_session.query(func.count(RequestLog.id)).filter(RequestLog.cached.is_(True)).scalar()
    )
    assert cached_entries >= len(urls), "Cached hits must be audited in request_log"
