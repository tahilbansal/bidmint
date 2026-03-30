"""
Punjab State e-Procurement Portal Scraper — eproc.punjab.gov.in

Strategy (CAPTCHA bypass via org-specific links):
  1. GET /nicgep/app?page=FrontEndTendersByOrganisation&service=page
     → Page loads WITHOUT CAPTCHA and lists all organisations with clickable links.
  2. Find org links whose names match food-related keywords.
  3. Follow each org link within the SAME httpx session (maintains cookie state).
     → The org-specific tender list page also loads WITHOUT CAPTCHA.
  4. Parse the tender table (columns: S.No | Published | Closing | Opening | Title+ID | Org).

The "Active Tenders" listing page requires CAPTCHA, but "Tenders by Organisation"
org-specific drill-down links bypass it completely when accessed with session cookies.
"""
import asyncio
import re
from pathlib import Path
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


_BASE = "https://eproc.punjab.gov.in"
_ORG_LIST_URL = _BASE + "/nicgep/app?page=FrontEndTendersByOrganisation&service=page"
_DEBUG_FILE = Path(__file__).parent / "punjab_debug.html"

# Org names containing any of these keywords will be scraped
_FOOD_ORG_KEYWORDS = [
    "food", "civil supply", "civil supplies", "grain", "ration",
    "agro", "punsup", "agriculture", "horticulture", "warehousing",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


def _save_debug_snapshot(html: str) -> None:
    _DEBUG_FILE.write_text(html, encoding="utf-8")
    print(f"Debug snapshot saved: {_DEBUG_FILE.resolve()}")


def _is_food_org(org_name: str) -> bool:
    name_lower = org_name.lower()
    return any(kw in name_lower for kw in _FOOD_ORG_KEYWORDS)


def _parse_tender_table(soup: BeautifulSoup, org_name: str) -> list:
    """
    Parse the tender table from an org-specific page.
    Table columns: S.No | e-Published Date | Closing Date | Opening Date |
                   Title and Ref.No./Tender ID | Organisation Chain
    Title column format: [Title][Ref.No.][Tender ID]
    """
    tenders = []
    # Target the table whose header row contains "S.No" and "Closing Date"
    for tbl in soup.find_all("table"):
        rows = tbl.find_all("tr")
        if not rows:
            continue
        header_cells = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
        if "S.No" in header_cells and "Closing Date" in header_cells:
            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) < 5:
                    continue
                try:
                    # col[4] = "[Title][Ref.No.][Tender ID]"
                    bracket_groups = re.findall(r"\[([^\]]+)\]", cols[4].get_text())
                    if len(bracket_groups) < 3:
                        continue
                    title = bracket_groups[0].strip()
                    tender_id = bracket_groups[2].strip()   # e.g. 2026_FCSCA_163613_1
                    deadline = _parse_date(cols[2].get_text(strip=True))

                    # Extract direct URL from the anchor in the title column
                    tender_url = ""
                    anchor = cols[4].find("a", href=True)
                    if anchor:
                        href = anchor["href"]
                        if href.startswith("http"):
                            tender_url = href
                        elif href.startswith("/"):
                            tender_url = _BASE + href

                    tenders.append({
                        "id": f"pb-{tender_id}",
                        "title": title,
                        "department": org_name,
                        "location": "Punjab",
                        "quantity": "",
                        "deadline": deadline,
                        "tender_url": tender_url,
                        "source": "punjab_state",
                    })
                except Exception as e:
                    print(f"  Error parsing Punjab tender row: {e}")
            break
    return tenders


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=30, min=30, max=120),
    reraise=True
)
async def scrape_punjab_tenders() -> list:
    """
    Scrape Punjab state e-procurement portal via org-specific links (no CAPTCHA).
    Returns list of raw tender dicts.
    """
    tenders = []

    async with httpx.AsyncClient(
        timeout=30, headers=_HEADERS, follow_redirects=True
    ) as client:
        try:
            # Step 1: Load the Tenders by Organisation page (no CAPTCHA)
            resp1 = await client.get(_ORG_LIST_URL)
            resp1.raise_for_status()
            soup1 = BeautifulSoup(resp1.text, "html.parser")

            # Step 2: Find all org links, filter by food keywords
            food_org_links = {}   # {org_name: href}
            for text_node in soup1.find_all(string=True):
                org_name = text_node.strip()
                if not org_name or not _is_food_org(org_name):
                    continue
                # Walk up to find the nearest enclosing anchor
                for ancestor in text_node.parent.parents:
                    a = ancestor.find("a", href=True)
                    if a and "DirectLink" in a.get("href", ""):
                        food_org_links[org_name] = a["href"]
                        break
                    if ancestor.name in ("tr", "table"):
                        break

            if not food_org_links:
                print("Punjab: No food-related organisations found on org list page.")
                _save_debug_snapshot(resp1.text)
                return tenders

            print(f"Punjab: Found {len(food_org_links)} food-related orgs: {list(food_org_links)}")

            # Step 3: Follow each org link (same session = no CAPTCHA) and parse tenders
            for org_name, href in food_org_links.items():
                try:
                    resp2 = await client.get(_BASE + href)
                    resp2.raise_for_status()
                    soup2 = BeautifulSoup(resp2.text, "html.parser")
                    org_tenders = _parse_tender_table(soup2, org_name)
                    print(f"  {org_name}: {len(org_tenders)} tenders")
                    tenders.extend(org_tenders)
                except Exception as e:
                    print(f"  Error fetching {org_name}: {e}")

        except httpx.HTTPStatusError as e:
            print(f"Punjab HTTP error {e.response.status_code}")
            raise
        except Exception as e:
            print(f"Punjab scraper error: {e}")
            raise

    print(f"Punjab scraper: found {len(tenders)} tenders total")
    return tenders


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    formats = [
        "%d-%b-%Y %I:%M %p",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%b-%Y",
        "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    tenders = asyncio.run(scrape_punjab_tenders())
    print(f"\n{len(tenders)} Punjab state tenders found:")
    for t in tenders[:10]:
        print(f"  [{t['id']}] {t['title'][:80]}")
