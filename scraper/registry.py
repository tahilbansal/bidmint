"""Scraper registry — single source of truth for all data portals.

To add a new portal:
  1. Create  scraper/<name>_scraper.py  with  async scrape_<name>_tenders() -> list
  2. Add a Scraper() entry to SCRAPERS below.
  3. The new portal will automatically appear in /admin/config and be usable
     as a ?portals=<name> parameter in /admin/scrape.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scraper:
    key: str               # Short ID used as API param, e.g. ?portals=gem
    label: str             # Human-readable name for logs and admin UI
    module: str            # Dotted Python module path
    fn_name: str           # Async function to call within that module
    uses_playwright: bool  # True → spawns a browser; must run in threadpool on Windows
    enabled: bool = True   # Toggle without deleting the entry


# ── Portal registry ───────────────────────────────────────────────────────────
# Add a line here to register a new portal. Order controls scrape execution order.

SCRAPERS: list[Scraper] = [
    Scraper(
        key="gem",
        label="GeM Portal (bidplus.gem.gov.in)",
        module="scraper.gem_scraper",
        fn_name="scrape_gem_tenders",
        uses_playwright=True,
    ),
    Scraper(
        key="cppp",
        label="CPPP Portal (eprocure.gov.in)",
        module="scraper.cppp_scraper",
        fn_name="scrape_cppp_tenders",
        uses_playwright=False,
    ),
    Scraper(
        key="punjab",
        label="Punjab State Portal (eproc.punjab.gov.in)",
        module="scraper.punjab_scraper",
        fn_name="scrape_punjab_tenders",
        uses_playwright=False,
    ),
    Scraper(
        key="haryana",
        label="Haryana State Portal (etenders.hry.nic.in)",
        module="scraper.haryana_scraper",
        fn_name="scrape_haryana_tenders",
        uses_playwright=False,
    ),
]

_INDEX: dict[str, Scraper] = {s.key: s for s in SCRAPERS}


def get_scraper(key: str) -> Scraper:
    if key not in _INDEX:
        raise KeyError(f"Unknown scraper: {key!r}. Registered: {list(_INDEX)}")
    return _INDEX[key]


def all_keys() -> list[str]:
    """All registered portal keys (including disabled)."""
    return list(_INDEX)


def enabled_keys() -> list[str]:
    """Keys for all enabled portals — used as the default when no portals param supplied."""
    return [s.key for s in SCRAPERS if s.enabled]


def scraper_labels() -> dict[str, str]:
    """Map of key → label for admin display."""
    return {s.key: s.label for s in SCRAPERS}
