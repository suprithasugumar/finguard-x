import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
from backend.app.ingest.text_extractor import TextExtractor

cik_int = 886171
acc_clean = "000110465914019994"
pdoc = "a13-25733_110k.htm"
url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{pdoc}"
headers = {"User-Agent": "FinGuardX-Research research@finguard.org"}

print(f"Fetching {url}...")
resp = requests.get(url, headers=headers, timeout=15)
print("Status:", resp.status_code, "Length:", len(resp.text))
if resp.status_code == 200:
    extractor = TextExtractor()
    sections = extractor.extract_sections(resp.text)
    for k, v in sections.items():
        print(f"Section {k}: status={v.get('status')}, len={len(v.get('text', ''))}")
        if v.get('text'):
            print(f"Preview {k}: {v['text'][:150]}...")
