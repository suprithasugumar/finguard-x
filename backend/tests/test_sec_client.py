"""Tests for SECClient rate limiting, disk caching, retry backoff, and lazy UA validation."""

import time

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.ingest.sec_client import SECClient


def test_lazy_user_agent_validation(monkeypatch, tmp_path):
    """Client raises on first network request if SEC_USER_AGENT is missing or invalid."""
    invalid_settings = Settings(SEC_USER_AGENT="")
    monkeypatch.setattr("backend.app.ingest.sec_client.get_settings", lambda: invalid_settings)

    client = SECClient(cache_dir=tmp_path / "cache")
    with pytest.raises(ValueError, match="SEC_USER_AGENT is not configured"):
        client.get("https://data.sec.gov/test", use_cache=False)


def test_cache_hit_on_second_call(tmp_path, db_session):
    """Second call to identical URL reads from disk cache with zero network calls."""
    calls = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": "ok", "call": calls})

    transport = httpx.MockTransport(mock_handler)
    client = SECClient(cache_dir=tmp_path / "cache", transport=transport)

    test_url = "https://data.sec.gov/api/xbrl/test_cache.json"

    # 1. First call - goes to network
    resp1 = client.get(test_url, use_cache=True, db_session=db_session)
    assert resp1.status_code == 200
    assert calls == 1
    assert resp1.json()["call"] == 1

    # 2. Second call - served from cache
    resp2 = client.get(test_url, use_cache=True, db_session=db_session)
    assert resp2.status_code == 200
    assert calls == 1  # Network handler not called again
    assert resp2.json()["call"] == 1


def test_rate_limiter_timing(tmp_path):
    """Limiter enforces maximum requests per second spacing."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(mock_handler)
    # Set to 5 req/s => minimum 0.20s interval
    client = SECClient(max_rate_per_sec=5.0, cache_dir=tmp_path / "cache", transport=transport)

    start = time.monotonic()
    client.get("https://data.sec.gov/req1", use_cache=False)
    client.get("https://data.sec.gov/req2", use_cache=False)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.18, f"Expected elapsed >= 0.18s, got {elapsed:.3f}s"


def test_exponential_backoff_on_429(tmp_path, db_session):
    """Client backs off with exponential delay on HTTP 429 then succeeds."""
    attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, headers={"Retry-After": "0.1"})
        return httpx.Response(200, json={"status": "recovered"})

    transport = httpx.MockTransport(mock_handler)
    client = SECClient(
        cache_dir=tmp_path / "cache", transport=transport, base_backoff=0.05, max_retries=3
    )

    resp = client.get("https://data.sec.gov/rate_limited", use_cache=False, db_session=db_session)
    assert resp.status_code == 200
    assert attempts == 3
    assert resp.json()["status"] == "recovered"
