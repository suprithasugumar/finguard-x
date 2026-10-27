import httpx
import time

client = httpx.Client(
    headers={"User-Agent": "FinGuardX-Research/1.0 (researcher@example.com)"},
    follow_redirects=True
)

t0 = time.time()
downloaded = 0
with client.stream("GET", "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip") as resp:
    for chunk in resp.iter_bytes(1024 * 1024):
        downloaded += len(chunk)
        if downloaded >= 30 * 1024 * 1024:
            break
t1 = time.time()
mb = downloaded / (1024 * 1024)
rate = mb / (t1 - t0)
print(f"Downloaded {mb:.1f} MB in {t1 - t0:.2f}s ({rate:.2f} MB/s)")
