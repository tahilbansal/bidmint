"""
GeM Portal Scraper — bidplus.gem.gov.in
Scrapes government e-marketplace tenders using Playwright for JS-rendered pages.
"""
import asyncio
import argparse
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


GEM_BASE_URL = "https://bidplus.gem.gov.in/all-bids"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=60, min=60, max=300),
    reraise=True
)
async def scrape_gem_tenders() -> list:
    """
    Scrape GeM portal for latest tender listings.
    Returns list of raw tender dicts with keys:
    id, title, department, location, quantity, deadline, source
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
            await page.goto(GEM_BASE_URL, timeout=60000, wait_until="networkidle")

            # Wait for bid listing table to render
            await page.wait_for_selector("#pagi_content", timeout=30000)

            # Extract page HTML for parsing
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            # Parse each bid block
            bid_blocks = soup.select("#pagi_content .bid_no")
            if not bid_blocks:
                # Fallback: try alternate selectors for GeM's dynamic layout
                bid_blocks = soup.select(".bid_no")

            for block in bid_blocks:
                try:
                    bid_id = _extract_text(block, ".bid_no a, a")
                    parent = block.find_parent("div", class_="border")
                    if not parent:
                        parent = block.find_parent("div")

                    title = _extract_text(parent, ".bid_header, h5, h6")
                    department = _extract_text(parent, ".org_name, .department")
                    quantity = _extract_text(parent, ".qty, .quantity")
                    location = _extract_text(parent, ".location, .address")
                    deadline_str = _extract_text(parent, ".end_date, .closing_date")
                    deadline = _parse_date(deadline_str)

                    if bid_id and title:
                        tenders.append({
                            "id": bid_id.strip(),
                            "title": title.strip(),
                            "department": department.strip() if department else "",
                            "location": location.strip() if location else "",
                            "quantity": quantity.strip() if quantity else "",
                            "deadline": deadline,
                            "source": "gem",
                        })
                except Exception as e:
                    print(f"Error parsing bid block: {e}")
                    continue

            # Paginate through additional pages (up to 10 pages)
            for page_num in range(2, 11):
                try:
                    next_btn = await page.query_selector(
                        f'a[data-page="{page_num}"], .pagination a:has-text("{page_num}")'
                    )
                    if not next_btn:
                        break

                    await next_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(2)  # Allow dynamic content to load

                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    bid_blocks = soup.select("#pagi_content .bid_no, .bid_no")

                    for block in bid_blocks:
                        try:
                            bid_id = _extract_text(block, ".bid_no a, a")
                            parent = block.find_parent("div", class_="border")
                            if not parent:
                                parent = block.find_parent("div")

                            title = _extract_text(parent, ".bid_header, h5, h6")
                            department = _extract_text(parent, ".org_name, .department")
                            quantity = _extract_text(parent, ".qty, .quantity")
                            location = _extract_text(parent, ".location, .address")
                            deadline_str = _extract_text(parent, ".end_date, .closing_date")
                            deadline = _parse_date(deadline_str)

                            if bid_id and title:
                                tenders.append({
                                    "id": bid_id.strip(),
                                    "title": title.strip(),
                                    "department": department.strip() if department else "",
                                    "location": location.strip() if location else "",
                                    "quantity": quantity.strip() if quantity else "",
                                    "deadline": deadline,
                                    "source": "gem",
                                })
                        except Exception:
                            continue
                except Exception:
                    break

        except Exception as e:
            print(f"GeM scraper error: {e}")
            raise
        finally:
            await browser.close()

    print(f"GeM scraper: found {len(tenders)} tenders")
    return tenders


def _extract_text(element, selector: str) -> str:
    """Extract text from first matching child element using CSS selector."""
    if element is None:
        return ""
    selectors = [s.strip() for s in selector.split(",")]
    for sel in selectors:
        found = element.select_one(sel)
        if found:
            return found.get_text(strip=True)
    return element.get_text(strip=True) if element else ""


def _parse_date(date_str: str) -> datetime | None:
    """Try multiple date formats common on GeM portal."""
    if not date_str:
        return None
    formats = [
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%b-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GeM tender scraper")
    parser.add_argument("--dry-run", action="store_true", help="Print tenders without saving")
    args = parser.parse_args()

    tenders = asyncio.run(scrape_gem_tenders())

    if args.dry_run:
        print(f"\n--- DRY RUN: {len(tenders)} tenders scraped ---")
        for t in tenders[:10]:
            print(f"  [{t['id']}] {t['title'][:80]}")
    else:
        from scraper.filter import filter_tenders
        filtered = filter_tenders(tenders)
        print(f"Filtered to {len(filtered)} Punjab food tenders")
