"""
GeM Portal Scraper — bidplus.gem.gov.in
Scrapes government e-marketplace tenders using Playwright for JS-rendered pages.
"""
import asyncio
import argparse
import os
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential


GEM_BASE_URL = "https://bidplus.gem.gov.in/all-bids"

# Container selector — confirmed from live page HTML
_CONTENT_SELECTOR = "#bidCard"

# Fallback containers if GeM ever changes the id
_CONTENT_SELECTORS_FALLBACK = [
    "#pagi_content",
    ".bids",
    ".bid-list",
]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=30, min=30, max=120),
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
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            # Mask automation signals
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        # Override navigator.webdriver to avoid bot detection
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        try:
            # Use domcontentloaded — networkidle can hang on CDN resources
            await page.goto(GEM_BASE_URL, timeout=90000, wait_until="domcontentloaded")

            # Small human-like pause
            await asyncio.sleep(3)

            # Wait for the confirmed content container
            loaded = False
            try:
                await page.wait_for_selector(_CONTENT_SELECTOR, timeout=20000)
                loaded = True
                print(f"GeM: content loaded (selector: '{_CONTENT_SELECTOR}')")
            except Exception:
                pass

            if not loaded:
                # Try fallbacks
                for sel in _CONTENT_SELECTORS_FALLBACK:
                    try:
                        await page.wait_for_selector(sel, timeout=10000)
                        loaded = True
                        print(f"GeM: content loaded via fallback selector '{sel}'")
                        break
                    except Exception:
                        continue

            if not loaded:
                _save_debug_snapshot(
                    await page.content(),
                    await page.screenshot(full_page=True)
                )
                raise RuntimeError(
                    "GeM page loaded but no bid content found. "
                    "Debug snapshot saved to scraper/gem_debug.html and gem_debug.png"
                )

            content = await page.content()
            page_tenders = _parse_tenders_from_html(content)
            tenders.extend(page_tenders)
            print(f"  Page 1: {len(page_tenders)} tenders")

            # Paginate — pages are loaded via AJAX on .page-link click
            for page_num in range(2, 11):
                try:
                    # href="#page-N" pattern confirmed in live HTML
                    next_link = await page.query_selector(f'a[href="#page-{page_num}"].page-link')
                    if not next_link:
                        break

                    await next_link.click()
                    # Wait for AJAX to repopulate #bidCard
                    await asyncio.sleep(3)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass

                    content = await page.content()
                    page_tenders = _parse_tenders_from_html(content)
                    if not page_tenders:
                        break
                    tenders.extend(page_tenders)
                    print(f"  Page {page_num}: {len(page_tenders)} tenders")

                except Exception:
                    break

        except Exception as e:
            print(f"GeM scraper error: {e}")
            raise
        finally:
            await browser.close()

    print(f"GeM scraper: found {len(tenders)} tenders")
    return tenders


def _parse_tenders_from_html(content: str) -> list:
    """
    Parse bid cards from GeM page HTML.
    Confirmed structure from live page (March 2026):
      Container : #bidCard
      Each card : div.card
      Bid ID    : p.bid_no > a.bid_no_hover  (text)
      Full title: a[data-toggle="popover"]   (data-content attr — displayed text is truncated)
      Quantity  : col-md-4, second div.row   (after "Quantity:" label)
      Department: col-md-5, second div.row   (after "Department Name And Address:" label)
      Deadline  : span.end_date              (text like "23-03-2026 9:00 AM")
    """
    soup = BeautifulSoup(content, "html.parser")
    tenders = []

    # Prefer scoped search inside #bidCard; fall back to all .card divs
    container = soup.select_one("#bidCard") or soup
    bid_cards = container.select("div.card")

    for card in bid_cards:
        try:
            # ── Bid ID ───────────────────────────────────────────
            bid_link = card.select_one("p.bid_no a.bid_no_hover, p.bid_no a")
            if not bid_link:
                continue
            bid_id = bid_link.get_text(strip=True)
            if not bid_id or len(bid_id) < 5:
                continue

            # ── Title — full text lives in data-content attr ─────
            # The visible link text is truncated ("Jaw Plate Moveable S. Toggle J...")
            # The full title is in the Bootstrap popover data-content attribute
            col4 = card.select_one("div.col-md-4")
            title = ""
            if col4:
                popover = col4.select_one("a[data-toggle='popover']")
                if popover:
                    title = (
                        popover.get("data-content", "")
                        or popover.get("title", "")
                        or popover.get_text(strip=True)
                    )
                else:
                    # Plain text item (no popover, e.g. "MICA PAPER")
                    rows = col4.select("div.row")
                    if rows:
                        title = rows[0].get_text(strip=True).replace("Items:", "").strip()

            if not title:
                continue

            # ── Quantity ─────────────────────────────────────────
            quantity = ""
            if col4:
                rows = col4.select("div.row")
                if len(rows) >= 2:
                    quantity = rows[1].get_text(strip=True).replace("Quantity:", "").strip()

            # ── Department + Location ────────────────────────────
            # col-md-5 has two rows: label row + value row
            # Value row: "Ministry of Communications\nDepartment of Posts"
            # GeM doesn't show a separate city/district field in the listing —
            # the filter will match Punjab keywords against the department text.
            col5 = card.select_one("div.col-md-5")
            department = ""
            if col5:
                dept_rows = col5.select("div.row")
                if len(dept_rows) >= 2:
                    department = dept_rows[1].get_text(separator=", ", strip=True)
                elif dept_rows:
                    department = dept_rows[0].get_text(separator=", ", strip=True)

            # Location: same text as department (for Punjab keyword matching in filter.py)
            location = department

            # ── Deadline ─────────────────────────────────────────
            deadline_span = card.select_one("span.end_date")
            deadline_str = deadline_span.get_text(strip=True) if deadline_span else ""
            deadline = _parse_date(deadline_str)

            tenders.append({
                "id": bid_id,
                "title": title,
                "department": department,
                "location": location,
                "quantity": quantity,
                "deadline": deadline,
                "source": "gem",
            })

        except Exception as e:
            print(f"Error parsing bid card: {e}")
            continue

    return tenders


def _save_debug_snapshot(html: str, screenshot: bytes):
    """Save HTML and screenshot for debugging failed scrapes."""
    base = os.path.join(os.path.dirname(__file__))
    html_path = os.path.join(base, "gem_debug.html")
    png_path = os.path.join(base, "gem_debug.png")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(png_path, "wb") as f:
        f.write(screenshot)
    print(f"Debug snapshot saved: {html_path} and {png_path}")


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
