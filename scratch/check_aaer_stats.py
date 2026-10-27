from collections import Counter
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.session import get_session_factory
from backend.app.db.models.entities import AAERCase

session_factory = get_session_factory()
session = session_factory()

total_cases = session.query(AAERCase).count()
excluded = session.query(AAERCase).filter(AAERCase.exclusion_reason.isnot(None)).count()
non_excluded = session.query(AAERCase).filter(AAERCase.exclusion_reason.is_(None)).count()

exclusions = Counter([c.exclusion_reason for c in session.query(AAERCase).filter(AAERCase.exclusion_reason.isnot(None)).all()])

with_cik = session.query(AAERCase).filter(AAERCase.cik.isnot(None)).count()
non_excluded_with_cik = session.query(AAERCase).filter(AAERCase.exclusion_reason.is_(None), AAERCase.cik.isnot(None)).count()

print("==========================================")
print(f"Total AAER cases in database: {total_cases}")
print(f"Excluded cases: {excluded}")
print(f"Non-excluded corporate fraud cases: {non_excluded}")
print(f"Cases with CIK resolved: {with_cik}")
print(f"Non-excluded with CIK resolved: {non_excluded_with_cik}")
print("\nTop Exclusions Breakdown:")
for reason, count in exclusions.most_common(10):
    print(f"  - {reason}: {count}")

# Check year distribution
all_non_ex = session.query(AAERCase).filter(AAERCase.exclusion_reason.is_(None)).all()
year_counts = Counter()
for c in all_non_ex:
    for y in c.affected_fiscal_years or []:
        if 2010 <= y <= 2025:
            year_counts[y] += 1

print("\nAffected Fiscal Years (2010-2025) count in non-excluded cases:")
for y in sorted(year_counts.keys()):
    print(f"  - FY{y}: {year_counts[y]} cases")

session.close()
