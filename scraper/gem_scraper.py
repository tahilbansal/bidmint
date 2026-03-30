"""
GeM Portal Scraper — bidplus.gem.gov.in

Strategy:
  Instead of scraping the generic all-bids page (which returns random bid types),
  we perform targeted keyword searches for food-related terms.  Each search URL
  returns bids matching that keyword across all categories.  Results are collected
  and deduplicated by bid ID before returning.

  _FOOD_SEARCH_TERMS  × _PAGES_PER_TERM pages × ~10 results/page
  ≈ 13 terms × 3 pages × 10 = ~390 targeted results per run.
"""
import asyncio
import argparse
import logging
import os
import urllib.parse
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

# Food keyword searches — one browser navigation per term, deduped by bid id
_FOOD_SEARCH_TERMS = [
    "rice", "chawal", "wheat", "atta",
    "dal", "pulses", "lentil",
    "sugar", "edible oil", "ghee",
    "milk dairy", "grocery ration", "foodgrain",
]

# Pages to paginate per search term (3 × ~10 bids = up to 30 targeted results each)
_PAGES_PER_TERM = 3

# URL template — search param appended to the all-bids endpoint
_GEM_SEARCH_URL = (
    "https://bidplus.gem.gov.in/all-bids"
    "?bid_number=&items_per_page=&search_under=&search={term}"
)

# Content container selectors (in priority order)
_CONTENT_SELECTOR = "#bidCard"
_CONTENT_SELECTORS_FALLBACK = ["#pagi_content", ".bids", ".bid-list"]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=30, min=30, max=120),
    reraise=True,
)
async def scrape_gem_tenders() -> list:
    """
    Scrape GeM portal using food keyword searches.
    Returns deduplicated list of raw tender dicts:
      id, title, department, location, quantity, deadline, source
    """
    all_tenders: list = []
    seen_ids: set = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
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
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        try:
            for term in _FOOD_SEARCH_TERMS:
                url = _GEM_SEARCH_URL.format(term=urllib.parse.quote(term))
                term_tenders = await _scrape_search_term(page, url, term)

                new_count = 0
                for t in term_tenders:
                    if t["id"] not in seen_ids:
                        seen_ids.add(t["id"])
                        all_tenders.append(t)
                        new_count += 1

                log.info(
                    "GeM '%s': %d found, %d new after dedup",
                    term, len(term_tenders), new_count,
                )
                # Brief pause between searches to avoid rate limiting
                await asyncio.sleep(2)

        except Exception as e:
            log.error("GeM scraper error: %s", e)
            raise
        finally:
            await browser.close()

    log.info(
        "GeM scraper: %d unique tenders from %d search terms",
        len(all_tenders), len(_FOOD_SEARCH_TERMS),
    )
    return all_tenders


async def _scrape_search_term(page, url: str, term: str) -> list:
    """Navigate to a search URL and scrape up to _PAGES_PER_TERM pages."""
    tenders = []
    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Wait for content container
        loaded = False
        try:
            await page.wait_for_selector(_CONTENT_SELECTOR, timeout=15000)
            loaded = True
        except Exception:
            pass

        if not loaded:
            for sel in _CONTENT_SELECTORS_FALLBACK:
                try:
                    await page.wait_for_selector(sel, timeout=8000)
                    loaded = True
                    break
                except Exception:
                    continue

        if not loaded:
            log.warning("GeM: no content container for '%s' — skipping", term)
            _save_debug_snapshot(
                await page.content(),
                await page.screenshot(full_page=True),
            )
            return tenders

        # Page 1
        page_tenders = _parse_tenders_from_html(await page.content())
        tenders.extend(page_tenders)

        # Pages 2..N
        for page_num in range(2, _PAGES_PER_TERM + 1):
            try:
                next_link = await page.query_selector(f'a[href="#page-{page_num}"].page-link')
                if not next_link:
                    break
                await next_link.click()
                await asyncio.sleep(2)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                page_tenders = _parse_tenders_from_html(await page.content())
                if not page_tenders:
                    break
                tenders.extend(page_tenders)
            except Exception:
                break

    except Exception as e:
        log.warning("GeM search '%s' failed: %s", term, e)

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

             # ── Tender URL ───────────────────────────────────────
            # The anchor href is typically /bids/bidsview?BID=... (relative)
            href = bid_link.get("href", "")
            if href.startswith("/"):
                tender_url = "https://bidplus.gem.gov.in" + href
            elif href.startswith("http"):
                tender_url = href
            else:
                # Construct a reliable search URL as fallback
                import urllib.parse as _up
                tender_url = (
                    "https://bidplus.gem.gov.in/search-bids?"
                    + _up.urlencode({"searchBidTitle": "", "bid_number": bid_id})
                )

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
                "tender_url": tender_url,
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
