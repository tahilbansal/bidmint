"""Shared portal runner — used by both scheduler.py and admin/routes/scrape.py.

Handles the Playwright/non-Playwright routing automatically via the registry,
so neither caller needs to know which scrapers need a browser subprocess.

Windows note:
  Playwright requires ProactorEventLoop to spawn browser subprocesses.
  FastAPI/uvicorn uses SelectorEventLoop, which does not support subprocess_exec.
  The fix: run Playwright scrapers in a dedicated ThreadPoolExecutor thread where
  asyncio.run() creates a fresh ProactorEventLoop owned by that thread.
"""
import asyncio
import importlib
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

# Shared pool — one thread per Playwright invocation avoids event-loop conflicts.
# max_workers=2 prevents hammering portals simultaneously.
_scraper_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="playwright")


def _run_in_thread(scraper_fn):
    """Execute an async scraper in a dedicated thread with its own event loop."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(scraper_fn())


async def scrape_portals(portal_keys: list[str]) -> tuple[list, dict]:
    """
    Run the scrapers for the given portal keys in order.

    Returns:
        raw_tenders   — combined raw tender dicts from all portals
        portal_stats  — {key: count} on success, {key: "error: ..."} on failure
    """
    from scraper.registry import get_scraper

    loop = asyncio.get_event_loop()
    raw_tenders: list = []
    portal_stats: dict = {}

    for key in portal_keys:
        try:
            cfg = get_scraper(key)
            mod = importlib.import_module(cfg.module)
            fn = getattr(mod, cfg.fn_name)

            log.info("Scraping %s …", cfg.label)
            if cfg.uses_playwright:
                tenders = await loop.run_in_executor(_scraper_pool, _run_in_thread, fn)
            else:
                tenders = await fn()

            raw_tenders.extend(tenders)
            portal_stats[key] = len(tenders)
            log.info("%s: %d raw tenders", cfg.label, len(tenders))

        except KeyError:
            log.error("Unknown portal key: %r — skipping", key)
            portal_stats[key] = "error: unknown portal"
        except Exception as e:
            log.error("%s scraper failed: %s", key, e, exc_info=True)
            portal_stats[key] = f"error: {e}"

    return raw_tenders, portal_stats
