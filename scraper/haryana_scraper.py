"""
Haryana State e-Tendering Portal Scraper — etenders.hry.nic.in (NICGEP)

Strategy (identical to Punjab portal — same NICGEP stack):
  1. GET /nicgep/app?page=FrontEndTendersByOrganisation&service=page
     → Lists all organisations WITHOUT CAPTCHA.
  2. Filter organisations whose names contain food/agriculture keywords.
  3. Follow each org link within the same httpx session (no CAPTCHA on org pages).
  4. Parse the tender table (columns: S.No | Published | Closing | Opening | Title+ID | Org).
"""
import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_BASE = "https://etenders.hry.nic.in"
_ORG_LIST_URL = _BASE + "/nicgep/app?page=FrontEndTendersByOrganisation&service=page"
_DEBUG_FILE = Path(__file__).parent / "haryana_debug.html"

# Org names containing any of these keywords will be scraped
_FOOD_ORG_KEYWORDS = [
    "food", "civil supply", "civil supplies", "supply chain",
    "grain", "ration", "agro", "agriculture", "horticulture",
    "warehousing", "market", "mandi", "consumer affairs",
    "hafed", "confed",   # Haryana state food corporations
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


def _is_food_org(org_name: str) -> bool:
    nl = org_name.lower()
    return any(kw in nl for kw in _FOOD_ORG_KEYWORDS)


def _parse_date(date_str: str) -> datetime | None:
    for fmt in ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_tender_table(soup: BeautifulSoup, org_name: str) -> list:
    """
    Parse the NICGEP tender table.
    Table columns: S.No | e-Published | Closing Date | Opening Date | Title+ID | Org Chain
    Title column format: [Title text][Ref.No.][Tender ID]
    """
    tenders = []
    for tbl in soup.find_all("table"):
        rows = tbl.find_all("tr")
        if not rows:
            continue
        headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
        if "S.No" not in headers or "Closing Date" not in headers:
            continue
        for row in rows[1:]:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
            try:
                bracket_groups = re.findall(r"\[([^\]]+)\]", cols[4].get_text())
                if len(bracket_groups) < 3:
                    continue
                title = bracket_groups[0].strip()
                tender_id = bracket_groups[2].strip()
                deadline = _parse_date(cols[2].get_text(strip=True))
                tenders.append({
                    "id": f"hr-{tender_id}",
                    "title": title,
                    "department": org_name,
                    "location": "Haryana",
                    "quantity": "",
                    "deadline": deadline,
                    "source": "haryana",
                })
            except Exception as e:
                log.debug("Error parsing Haryana tender row: %s", e)
        break   # found the right table
    return tenders


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=30, min=30, max=120), reraise=True)
async def scrape_haryana_tenders() -> list:
    """
    Scrape Haryana NICGEP portal food tenders via org-specific links (no CAPTCHA).
    Returns list of raw tender dicts with keys: id, title, department, location,
    quantity, deadline, source.
    """
    tenders: list = []

    async with httpx.AsyncClient(timeout=30, headers=_HEADERS, follow_redirects=True) as client:
        try:
            resp = await client.get(_ORG_LIST_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find food-related org links (href contains "DirectLink")
            food_org_links: dict[str, str] = {}
            for text_node in soup.find_all(string=True):
                org_name = text_node.strip()
                if not org_name or not _is_food_org(org_name):
                    continue
                for ancestor in text_node.parent.parents:
                    a = ancestor.find("a", href=True)
                    if a and "DirectLink" in a.get("href", ""):
                        food_org_links[org_name] = a["href"]
                        break
                    if ancestor.name in ("tr", "table"):
                        break

            if not food_org_links:
                log.warning("Haryana: no food orgs found — saving debug snapshot")
                _DEBUG_FILE.write_text(resp.text, encoding="utf-8")
                return tenders

            log.info("Haryana: %d food orgs found: %s", len(food_org_links), list(food_org_links))

            for org_name, href in food_org_links.items():
                try:
                    r2 = await client.get(_BASE + href)
                    r2.raise_for_status()
                    org_tenders = _parse_tender_table(BeautifulSoup(r2.text, "html.parser"), org_name)
                    log.info("  %s: %d tenders", org_name, len(org_tenders))
                    tenders.extend(org_tenders)
                except Exception as e:
                    log.error("  Error fetching %s: %s", org_name, e)

        except httpx.HTTPStatusError as e:
            log.error("Haryana HTTP error %s", e.response.status_code)
            raise
        except Exception as e:
            log.error("Haryana scraper error: %s", e)
            raise

    log.info("Haryana scraper: %d raw tenders total", len(tenders))
    return tenders


if __name__ == "__main__":
    tenders = asyncio.run(scrape_haryana_tenders())
    print(f"\n{len(tenders)} tenders found")
    for t in tenders[:5]:
        print(f"  [{t['id']}] {t['title'][:80]}")
