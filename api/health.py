"""
Health check and admin stats endpoints.
"""
from database.connection import SessionLocal
from database.models import Supplier, Tender, Alert
from datetime import datetime, timedelta


def get_daily_stats() -> dict:
    """Generate daily stats summary for admin health report."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        active_suppliers = db.query(Supplier).filter(Supplier.active == True).count()  # noqa: E712
        total_tenders = db.query(Tender).filter(Tender.scraped_at >= today_start).count()

        alerts_today = db.query(Alert).filter(Alert.sent_at >= today_start).all()
        yes_count = sum(1 for a in alerts_today if a.response == "YES")
        no_count = sum(1 for a in alerts_today if a.response == "NO")

        return {
            "scraped": total_tenders,
            "new": total_tenders,
            "alerts_sent": len(alerts_today),
            "yes": yes_count,
            "no": no_count,
            "no_response": len(alerts_today) - yes_count - no_count,
            "suppliers": active_suppliers,
            "api_cost_inr": total_tenders * 0.08,  # ~Rs 0.08 per Claude call
            "errors": 0,
        }
    finally:
        db.close()
