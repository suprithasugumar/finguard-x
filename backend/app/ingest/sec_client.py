"""Rate-limited, cached SEC EDGAR HTTP client with request audit logging (R4)."""

import hashlib
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.entities import RequestLog
from backend.app.db.session import get_session_factory

logger = logging.getLogger("finguard.ingest.sec_client")


class SECClient:
    """SEC EDGAR compliant HTTP client.

    Guarantees:
    - Lazy SEC_USER_AGENT compliance validation (R4)
    - Max 5.0 requests/second strict rate limiting
    - Disk caching keyed by URL hash (no redundant downloads)
    - Exponential backoff with jitter on 429/503 errors
    - Audit logging of every request to request_log table
    """

    def __init__(
        self,
        max_rate_per_sec: float = 5.0,
        cache_dir: Optional[Path] = None,
        max_retries: int = 5,
        base_backoff: float = 1.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.settings = get_settings()
        self.max_rate_per_sec = max_rate_per_sec
        self.min_interval = 1.0 / max_rate_per_sec
        self.cache_dir = cache_dir or (self.settings.CACHE_DIR / "sec")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.transport = transport
        self._last_request_time: float = 0.0

    def _get_user_agent(self) -> str:
        """Lazily validate and return SEC User-Agent."""
        return self.settings.validate_sec_user_agent()

    def _wait_for_rate_limit(self) -> None:
        """Enforce maximum requests per second limiter."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            sleep_duration = self.min_interval - elapsed
            time.sleep(sleep_duration)
        self._last_request_time = time.monotonic()

    def _get_cache_path(self, url: str) -> Path:
        """Return deterministic cache path based on URL SHA-256 hash."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{url_hash}.json"

    def _read_cache(self, url: str) -> Optional[Tuple[int, bytes, Dict[str, str]]]:
        """Read cached response if present on disk."""
        path = self._get_cache_path(url)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Content is stored as hex
            content = bytes.fromhex(data["content_hex"])
            return data["status_code"], content, data.get("headers", {})
        except Exception as e:
            logger.warning(f"Failed to read cache for {url}: {e}")
            return None

    def _write_cache(
        self, url: str, status_code: int, content: bytes, headers: Dict[str, str]
    ) -> None:
        """Write response to disk cache."""
        path = self._get_cache_path(url)
        try:
            serializable_headers = {k: v for k, v in headers.items() if isinstance(v, str)}
            data = {
                "url": url,
                "status_code": status_code,
                "headers": serializable_headers,
                "content_hex": content.hex(),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write cache for {url}: {e}")

    def _log_request(
        self,
        url: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        cached: bool,
        error_message: Optional[str] = None,
        db_session: Optional[Session] = None,
    ) -> None:
        """Audit request in database request_log table."""
        session_created = False
        if db_session is None:
            session_factory = get_session_factory()
            db_session = session_factory()
            session_created = True

        try:
            entry = RequestLog(
                url=url,
                method=method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                cached=cached,
                error_message=error_message,
            )
            db_session.add(entry)
            db_session.commit()
        except Exception as e:
            logger.warning(f"Failed to audit request to DB: {e}")
            if session_created:
                db_session.rollback()
        finally:
            if session_created:
                db_session.close()

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
        db_session: Optional[Session] = None,
    ) -> httpx.Response:
        """Perform GET request with rate limiting, retries, and caching."""
        # 1. Check cache first
        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                status_code, content, cached_headers = cached
                self._log_request(
                    url=url,
                    method="GET",
                    status_code=status_code,
                    response_time_ms=0.0,
                    cached=True,
                    db_session=db_session,
                )
                request = httpx.Request("GET", url)
                return httpx.Response(
                    status_code=status_code,
                    content=content,
                    headers=cached_headers,
                    request=request,
                )

        # 2. Lazy User-Agent validation
        ua = self._get_user_agent()
        req_headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
        if headers:
            req_headers.update(headers)

        retries = 0
        last_error: Optional[str] = None

        while retries <= self.max_retries:
            self._wait_for_rate_limit()
            start_time = time.monotonic()
            try:
                with httpx.Client(
                    transport=self.transport,
                    timeout=httpx.Timeout(30.0, connect=10.0),
                    follow_redirects=True,
                ) as client:
                    resp = client.get(url, params=params, headers=req_headers)
                    elapsed_ms = (time.monotonic() - start_time) * 1000.0

                    # Handle 429 Too Many Requests or 503 Service Unavailable
                    if resp.status_code in (429, 503):
                        retries += 1
                        if retries > self.max_retries:
                            self._log_request(
                                url=url,
                                method="GET",
                                status_code=resp.status_code,
                                response_time_ms=elapsed_ms,
                                cached=False,
                                error_message=f"Max retries exceeded with status {resp.status_code}",
                                db_session=db_session,
                            )
                            resp.raise_for_status()

                        # Exponential backoff + jitter
                        jitter = random.uniform(0.1, 0.5)
                        backoff = (self.base_backoff * (2 ** (retries - 1))) + jitter
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            backoff = max(backoff, float(retry_after))

                        logger.warning(
                            f"HTTP {resp.status_code} on {url}. Retrying ({retries}/{self.max_retries}) in {backoff:.2f}s"
                        )
                        time.sleep(backoff)
                        continue

                    # Success or non-retryable response
                    self._log_request(
                        url=url,
                        method="GET",
                        status_code=resp.status_code,
                        response_time_ms=elapsed_ms,
                        cached=False,
                        db_session=db_session,
                    )

                    if resp.is_success and use_cache:
                        self._write_cache(
                            url=url,
                            status_code=resp.status_code,
                            content=resp.content,
                            headers=dict(resp.headers),
                        )

                    return resp

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                retries += 1
                elapsed_ms = (time.monotonic() - start_time) * 1000.0
                last_error = str(exc)
                if retries > self.max_retries:
                    self._log_request(
                        url=url,
                        method="GET",
                        status_code=0,
                        response_time_ms=elapsed_ms,
                        cached=False,
                        error_message=last_error,
                        db_session=db_session,
                    )
                    raise

                jitter = random.uniform(0.1, 0.5)
                backoff = (self.base_backoff * (2 ** (retries - 1))) + jitter
                logger.warning(
                    f"Request failed on {url} ({exc}). Retrying ({retries}/{self.max_retries}) in {backoff:.2f}s"
                )
                time.sleep(backoff)

        raise RuntimeError(f"Max retries exceeded for {url}: {last_error}")
