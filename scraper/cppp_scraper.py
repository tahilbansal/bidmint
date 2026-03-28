"""
CPPP Portal Scraper — eprocure.gov.in/cppp
Scrapes the Central Public Procurement Portal (new Drupal-based frontend) which
does NOT require CAPTCHA for public listings, unlike the legacy /eprocure/ path.

URL structure:
  Page 1 : https://eprocure.gov.in/cppp/latestactivetendersnew/cppp10
  Page N : https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata?page=N

Table columns: Sl.No | e-Published Date | Closing Date | Opening Date |
               Title/Ref.No./Tender Id | Organisation Name | Corrigendum
"""
import asyncio
from pathlib import Path
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


_PAGE1_URL = "https://eprocure.gov.in/cppp/latestactivetendersnew/cppp10"
_PAGE_N_URL = "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata?page={n}"
_MAX_PAGES = 5   # 50 tenders per run — filter narrows to food/Punjab
_DEBUG_FILE = Path(__file__).parent / "cppp_debug.html"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _save_debug_snapshot(html: str) -> None:
    _DEBUG_FILE.write_text(html, encoding="utf-8")
    print(f"Debug snapshot saved: {_DEBUG_FILE.resolve()}")


def _parse_rows(soup: BeautifulSoup) -> list:
    """Parse tender rows from a fetched CPPP page."""
    tenders = []
    table = soup.find("table")
    if not table:
        return tenders
    for row in table.find_all("tr")[1:]:   # skip header
        cols = row.find_all("td")
        if len(cols) < 6:
            continue
        try:
            # col[4]: anchor text = clean title; full text = title/ref/id
            title_td = cols[4]
            anchor = title_td.find("a")
            title = anchor.get_text(strip=True) if anchor else title_td.get_text(strip=True)
            full_ref = title_td.get_text(strip=True)
            tender_id = full_ref.rsplit("/", 1)[-1].strip() or full_ref.replace("/", "-")

            department = cols[5].get_text(strip=True)
            deadline_str = cols[2].get_text(strip=True)   # Bid Submission Closing Date
            deadline = _parse_date(deadline_str)

            # Direct link to the tender detail page
            tender_url = ""
            if anchor:
                href = anchor.get("href", "")
                if href.startswith("http"):
                    tender_url = href
                elif href.startswith("/"):
                    tender_url = "https://eprocure.gov.in" + href

            if title:
                tenders.append({
                    "id": f"cppp-{tender_id}",
                    "title": title,
                    "department": department,
                    "location": "",
                    "quantity": "",
                    "deadline": deadline,
                    "tender_url": tender_url,
                    "source": "cppp",
                })
        except Exception as e:
            print(f"Error parsing CPPP row: {e}")
    return tenders


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=30, min=30, max=120),
    reraise=True
)
async def scrape_cppp_tenders() -> list:
    """
    Scrape CPPP portal (new frontend) for active tenders.
    Fetches up to _MAX_PAGES pages (10 tenders each).
    Returns list of raw tender dicts.
    """
    tenders = []

    async with httpx.AsyncClient(
        timeout=30, headers=_HEADERS, follow_redirects=True
    ) as client:
        for page_num in range(1, _MAX_PAGES + 1):
            url = _PAGE1_URL if page_num == 1 else _PAGE_N_URL.format(n=page_num)
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # Sanity check: if somehow a CAPTCHA page slips through, bail
                if not soup.find("table"):
                    _save_debug_snapshot(resp.text)
                    print(f"CPPP: No table on page {page_num} — saved debug HTML.")
                    break

                rows = _parse_rows(soup)
                if not rows:
                    break   # no more data
                tenders.extend(rows)

            except httpx.HTTPStatusError as e:
                print(f"CPPP HTTP error on page {page_num}: {e.response.status_code}")
                break
            except Exception as e:
                print(f"CPPP scraper error on page {page_num}: {e}")
                break

    print(f"CPPP scraper: found {len(tenders)} tenders")
    return tenders


def _parse_date(date_str: str) -> datetime | None:
    """Parse dates from CPPP portal."""
    if not date_str:
        return None
    formats = [
        "%d-%b-%Y %I:%M %p",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%b-%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    tenders = asyncio.run(scrape_cppp_tenders())
    print(f"\n{len(tenders)} CPPP tenders found:")
    for t in tenders[:10]:
        print(f"  [{t['id']}] {t['title'][:80]}")
