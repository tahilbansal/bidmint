"""
CPPP Portal Scraper — eprocure.gov.in
Scrapes Central Public Procurement Portal for food procurement tenders.
"""
import asyncio
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


CPPP_SEARCH_URL = "https://eprocure.gov.in/eprocure/app"
CPPP_ACTIVE_TENDERS_URL = "https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=60, min=60, max=300),
    reraise=True
)
async def scrape_cppp_tenders() -> list:
    """
    Scrape CPPP portal for active food-related tenders.
    Returns list of raw tender dicts.
    """
    tenders = []

    async with httpx.AsyncClient(
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
        follow_redirects=True
    ) as client:
        try:
            resp = await client.get(CPPP_ACTIVE_TENDERS_URL)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # CPPP uses a table layout for active tenders
            table = soup.find("table", {"id": "table"})
            if not table:
                # Fallback: parse whatever table exists
                table = soup.find("table")

            if not table:
                print("CPPP: No tender table found on page")
                return tenders

            rows = table.find_all("tr")[1:]  # Skip header row

            for row in rows:
                try:
                    cols = row.find_all("td")
                    if len(cols) < 5:
                        continue

                    tender_id = cols[0].get_text(strip=True)
                    title = cols[1].get_text(strip=True)
                    department = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                    location = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    deadline_str = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                    deadline = _parse_date(deadline_str)

                    if tender_id and title:
                        tenders.append({
                            "id": f"cppp-{tender_id.strip()}",
                            "title": title.strip(),
                            "department": department.strip(),
                            "location": location.strip(),
                            "quantity": "",  # CPPP doesn't always show quantity in listing
                            "deadline": deadline,
                            "source": "cppp",
                        })
                except Exception as e:
                    print(f"Error parsing CPPP row: {e}")
                    continue

        except httpx.HTTPStatusError as e:
            print(f"CPPP HTTP error: {e.response.status_code}")
            raise
        except Exception as e:
            print(f"CPPP scraper error: {e}")
            raise

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
