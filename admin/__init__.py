"""
BidMint Admin API — self-contained, mountable FastAPI router.

All endpoints require the  X-Admin-Key  request header.

Route map:
  GET    /admin/stats                   — dashboard: suppliers / tenders / alerts overview
  GET    /admin/suppliers               — list suppliers  (?active_only=true)
  POST   /admin/suppliers               — add a supplier
  PATCH  /admin/suppliers/{phone}       — update district / categories / active
  DELETE /admin/suppliers/{phone}       — deactivate supplier

  GET    /admin/tenders                 — list tenders (?source=gem&category=rice&since=2026-03-01)
  GET    /admin/tenders/{id}            — tender detail + alerts sent

  GET    /admin/prices                  — fetch live AGMARKNET prices on demand

  POST   /admin/scrape                  — trigger manual scrape (returns job_id, async)
  GET    /admin/scrape                  — list recent scrape jobs
  GET    /admin/scrape/{job_id}         — poll status of a scrape job

  GET    /admin/config                  — show runtime config
  PATCH  /admin/config                  — update config (in-memory; survives until restart)

  GET    /admin/run-logs                — scheduler run history (?job=daily_scrape&limit=20)
  GET    /admin/run-logs/latest         — latest completed run per job type
  GET    /admin/run-logs/health         — did daily_scrape run in the last 26 hours?

To move this module to a separate repo in the future:
  1. Copy the admin/ folder
  2. Ensure database/, scraper/, ai/, whatsapp/ are available (as packages or installed)
  3. Mount admin_router on a new FastAPI app
"""
from fastapi import APIRouter

from admin.routes import config, prices, run_logs, scrape, stats, suppliers, tenders

admin_router = APIRouter(prefix="/admin")

admin_router.include_router(stats.router)
admin_router.include_router(suppliers.router)
admin_router.include_router(tenders.router)
admin_router.include_router(prices.router)
admin_router.include_router(scrape.router)
admin_router.include_router(config.router)
admin_router.include_router(run_logs.router)
