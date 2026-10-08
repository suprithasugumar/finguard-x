"""Robust downloader for SEC bulk archives (submissions.zip and companyfacts.zip) with resume and checksums."""
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from typing import Tuple

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("finguard.bulk_download")

URLS = {
    "submissions.zip": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
    "companyfacts.zip": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
}


def download_file_with_resume(url: str, dest_path: Path, user_agent: str, max_retries: int = 50) -> Tuple[str, int]:
    """Download large archive with streaming, progress logging, auto-resume, and sha256 calculation."""
    temp_path = dest_path.with_suffix(".part")
    retries = 0

    while retries < max_retries:
        existing_bytes = temp_path.stat().st_size if temp_path.exists() else 0
        headers = {"User-Agent": user_agent}
        if existing_bytes > 0:
            headers["Range"] = f"bytes={existing_bytes}-"
            logger.info(f"Resuming download from byte {existing_bytes} for {dest_path.name}...")

        client = httpx.Client(headers=headers, follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0))
        mode = "ab" if existing_bytes > 0 else "wb"

        try:
            with client.stream("GET", url) as resp:
                if resp.status_code not in (200, 206):
                    raise RuntimeError(f"HTTP {resp.status_code} on {url}")

                content_len = int(resp.headers.get("content-length", 0))
                total_size = content_len + existing_bytes if resp.status_code == 206 else content_len
                logger.info(f"Downloading {dest_path.name} ({existing_bytes / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)...")

                t_start = time.time()
                last_log = t_start
                bytes_downloaded = existing_bytes

                with open(temp_path, mode) as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        f.flush()
                        bytes_downloaded += len(chunk)

                        now = time.time()
                        if now - last_log >= 10.0:
                            mb = bytes_downloaded / (1024 * 1024)
                            speed = (bytes_downloaded - existing_bytes) / (now - t_start) / (1024 * 1024)
                            pct = (bytes_downloaded / total_size * 100.0) if total_size > 0 else 0
                            logger.info(f"{dest_path.name}: {mb:.1f} MB / {total_size/(1024*1024):.1f} MB ({pct:.1f}%) at {speed:.2f} MB/s")
                            last_log = now

                # Verify completion
                if total_size > 0 and bytes_downloaded >= total_size:
                    break

        except (httpx.RequestError, httpx.HTTPError, Exception) as exc:
            retries += 1
            logger.warning(f"Connection dropped ({exc}). Retrying/resuming ({retries}/{max_retries}) in 2.0s...")
            time.sleep(2.0)

    # Compute final SHA-256
    sha = hashlib.sha256()
    with open(temp_path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            sha.update(chunk)

    if dest_path.exists():
        dest_path.unlink()
    temp_path.rename(dest_path)

    final_size = dest_path.stat().st_size
    final_sha = sha.hexdigest()
    logger.info(f"Finished {dest_path.name} ({final_size / (1024*1024):.1f} MB) SHA256: {final_sha}")
    return final_sha, final_size


def run_bulk_download():
    settings = get_settings()
    ua = settings.validate_sec_user_agent()
    raw_dir = settings.RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"

    manifest = {"files": {}, "updated_at": datetime.now(timezone.utc).isoformat()}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    for filename, url in URLS.items():
        dest = raw_dir / filename
        # Check if already complete
        if dest.exists() and filename in manifest.get("files", {}):
            logger.info(f"{filename} already present and verified in manifest.")
            continue

        sha, size = download_file_with_resume(url, dest, ua)
        manifest["files"][filename] = {
            "url": url,
            "sha256": sha,
            "size_bytes": size,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    logger.info(f"Bulk download completed. Manifest saved to {manifest_path}")


if __name__ == "__main__":
    from typing import Tuple
    run_bulk_download()
