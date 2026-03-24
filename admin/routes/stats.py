"""
Dashboard stats endpoint — GET /admin/stats
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from admin.auth import require_admin_key
from database.connection import get_db
from database.models import Alert, RunLog, Supplier, Tender

router = APIRouter(prefix="/stats", tags=["Admin – Stats"])

ALL_CATEGORIES = ["rice", "wheat", "pulses", "oils", "sugar", "dairy", "spices", "vegetables", "fruits", "other_food"]


@router.get("", dependencies=[Depends(require_admin_key)])
async def dashboard_stats(db: Session = Depends(get_db)):
    """Overview: suppliers, tenders, alerts, scheduler health."""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    # --- Alerts ---
    alerts_today = db.query(Alert).filter(Alert.sent_at >= day_ago).all()
    alerts_7d    = db.query(Alert).filter(Alert.sent_at >= week_ago).all()
    yes_today = sum(1 for a in alerts_today if a.response == "YES")
    yes_7d    = sum(1 for a in alerts_7d    if a.response == "YES")

    def pct(n, total):
        return f"{round(n / total * 100)}%" if total else "0%"

    # --- Scheduler health (last daily_scrape run) ---
    last_scrape = (
        db.query(RunLog)
        .filter(RunLog.job_name == "daily_scrape", RunLog.finished_at.isnot(None))
        .order_by(RunLog.started_at.desc())
        .first()
    )
    stale_cutoff = now - timedelta(hours=26)
    if last_scrape is None:
        scheduler_health = "NEVER_RUN"
    elif last_scrape.started_at < stale_cutoff:
        scheduler_health = "STALE"
    elif last_scrape.status != "success":
        scheduler_health = "ERROR"
    else:
        scheduler_health = "OK"

    return {
        "suppliers": {
            "active": db.query(Supplier).filter(Supplier.active == True).count(),  # noqa: E712
            "total":  db.query(Supplier).count(),
        },
        "tenders": {
            "total":    db.query(Tender).count(),
            "last_24h": db.query(Tender).filter(Tender.scraped_at >= day_ago).count(),
            "last_7d":  db.query(Tender).filter(Tender.scraped_at >= week_ago).count(),
            "by_source": {
                src: db.query(Tender).filter(Tender.source == src).count()
                for src in ["gem", "cppp", "punjab_state"]
            },
            "by_category": {
                cat: db.query(Tender).filter(Tender.category == cat).count()
                for cat in ALL_CATEGORIES
            },
        },
        "alerts": {
            "sent_today":       len(alerts_today),
            "yes_today":        yes_today,
            "response_rate_today": pct(yes_today, len(alerts_today)),
            "sent_7d":          len(alerts_7d),
            "yes_7d":           yes_7d,
            "response_rate_7d": pct(yes_7d, len(alerts_7d)),
        },
        "scheduler": {
            "health": scheduler_health,
            "last_scrape_at":  last_scrape.started_at.isoformat() if last_scrape else None,
            "last_scrape_status": last_scrape.status if last_scrape else None,
            "last_scraped":    last_scrape.scraped if last_scrape else 0,
            "last_new_tenders": last_scrape.new_tenders if last_scrape else 0,
            "last_alerts_sent": last_scrape.alerts_sent if last_scrape else 0,
            "last_errors":     last_scrape.errors if last_scrape else 0,
        },
    }

