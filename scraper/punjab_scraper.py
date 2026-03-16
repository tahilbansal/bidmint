"""
Punjab State e-Procurement Portal Scraper
Scrapes Punjab state government tenders for food procurement.
"""
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


PUNJAB_EPROCURE_URL = "https://eproc.punjab.gov.in/nicgep/app"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=60, min=60, max=300),
    reraise=True
)
async def scrape_punjab_tenders() -> list:
    """
    Scrape Punjab state e-procurement portal.
    Returns list of raw tender dicts.
    """
    tenders = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await page.goto(PUNJAB_EPROCURE_URL, timeout=60000, wait_until="networkidle")

            # Navigate to active tenders section
            active_link = await page.query_selector(
                'a:has-text("Active Tenders"), a:has-text("Latest Active Tenders")'
            )
            if active_link:
                await active_link.click()
                await page.wait_for_load_state("networkidle", timeout=30000)

            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            # Parse tender listing table
            table = soup.find("table", {"id": "table"})
            if not table:
                table = soup.find("table", class_="list_table")
            if not table:
                table = soup.find("table")

            if table:
                rows = table.find_all("tr")[1:]  # Skip header
                for row in rows:
                    try:
                        cols = row.find_all("td")
                        if len(cols) < 4:
                            continue

                        tender_id = cols[0].get_text(strip=True)
                        title = cols[1].get_text(strip=True)
                        department = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                        deadline_str = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                        deadline = _parse_date(deadline_str)

                        if tender_id and title:
                            tenders.append({
                                "id": f"pb-{tender_id.strip()}",
                                "title": title.strip(),
                                "department": department.strip(),
                                "location": "Punjab",  # All tenders are Punjab state
                                "quantity": "",
                                "deadline": deadline,
                                "source": "punjab_state",
                            })
                    except Exception as e:
                        print(f"Error parsing Punjab row: {e}")
                        continue

        except Exception as e:
            print(f"Punjab scraper error: {e}")
            raise
        finally:
            await browser.close()

    print(f"Punjab scraper: found {len(tenders)} tenders")
    return tenders


def _parse_date(date_str: str) -> datetime | None:
    """Parse dates from Punjab portal."""
    if not date_str:
        return None
    formats = [
        "%d-%b-%Y %I:%M %p",
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
