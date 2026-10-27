import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.core.config import Settings
import requests

# Let's check SEC EDGAR submissions API or search for accession 0001104659-14-019994
cik = "0000886171"
acc = "0001104659-14-019994"
headers = {"User-Agent": "FinGuardX-Research user@finguard.org"}

url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
print("Checking submissions JSON for CIK:", cik)
try:
    r = requests.get(url, headers=headers, timeout=10)
    print("Status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        recent = data.get("filings", {}).get("recent", {})
        acc_nums = recent.get("accessionNumber", [])
        if acc in acc_nums:
            idx = acc_nums.index(acc)
            pdoc = recent.get("primaryDocument", [])[idx]
            print(f"Found accession in recent! primaryDocument: {pdoc}")
        else:
            print("Accession not in recent (might be older or in files). Checking older files...")
            files = data.get("filings", {}).get("files", [])
            print("Older files count:", len(files))
            for f_info in files:
                f_name = f_info.get("name")
                f_url = f"https://data.sec.gov/submissions/{f_name}"
                f_r = requests.get(f_url, headers=headers, timeout=10)
                if f_r.status_code == 200:
                    f_data = f_r.json()
                    f_accs = f_data.get("accessionNumber", [])
                    if acc in f_accs:
                        f_idx = f_accs.index(acc)
                        pdoc = f_data.get("primaryDocument", [])[f_idx]
                        print(f"Found accession in {f_name}! primaryDocument: {pdoc}")
                        break
except Exception as e:
    print("Error:", e)
