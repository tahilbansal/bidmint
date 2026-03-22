"""
Dashboard stats endpoint — GET /admin/stats
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from admin.auth import require_admin_key
from database.connection import get_db
from database.models import Alert, Supplier, Tender

router = APIRouter(prefix="/stats", tags=["Admin – Stats"])


@router.get("", dependencies=[Depends(require_admin_key)])
async def dashboard_stats(db: Session = Depends(get_db)):
    """Overview: active suppliers, tender counts by source/category, alert response rate."""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    alerts_today = db.query(Alert).filter(Alert.sent_at >= day_ago).all()
    yes_today = sum(1 for a in alerts_today if a.response == "YES")
    total_today = len(alerts_today)

    return {
        "suppliers": {
            "active": db.query(Supplier).filter(Supplier.active == True).count(),  # noqa: E712
            "total": db.query(Supplier).count(),
        },
        "tenders": {
            "total": db.query(Tender).count(),
            "last_24h": db.query(Tender).filter(Tender.scraped_at >= day_ago).count(),
            "last_7d": db.query(Tender).filter(Tender.scraped_at >= week_ago).count(),
            "by_source": {
                src: db.query(Tender).filter(Tender.source == src).count()
                for src in ["gem", "cppp", "punjab_state"]
            },
            "by_category": {
                cat: db.query(Tender).filter(Tender.category == cat).count()
                for cat in ["rice", "wheat", "pulses", "oils", "sugar", "dairy", "spices"]
            },
        },
        "alerts": {
            "sent_today": total_today,
            "yes_today": yes_today,
            "response_rate": f"{round(yes_today / total_today * 100)}%" if total_today else "0%",
        },
    }
