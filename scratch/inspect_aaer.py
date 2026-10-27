import httpx
from bs4 import BeautifulSoup

client = httpx.Client(
    headers={"User-Agent": "FinGuardX-Research/1.0 (researcher@example.com)"},
    follow_redirects=True
)

r = client.get("https://www.sec.gov/divisions/enforce/friactions.shtml")
soup = BeautifulSoup(r.content, "html.parser")

print("Title:", soup.title.text if soup.title else "No title")
pager = soup.find(class_=lambda x: x and "pager" in x)
if pager:
    print("Pager links:", [a["href"] for a in pager.find_all("a", href=True)])
else:
    print("No pager found directly, checking page 1")

r2 = client.get("https://www.sec.gov/divisions/enforce/friactions.shtml?page=1")
soup2 = BeautifulSoup(r2.content, "html.parser")
t2 = soup2.find("table")
if t2:
    print("Page 1 table rows:", len(t2.find_all("tr")))
    print("Page 1 first row:", [c.text.strip().replace("\n", " ") for c in t2.find_all("tr")[1].find_all(["td", "th"])])
