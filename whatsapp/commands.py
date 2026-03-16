"""
WhatsApp command action implementations.
Reusable command logic extracted for use by both the webhook handler and CLI tools.
"""
from database.models import Supplier, Alert, Tender
from sqlalchemy.orm import Session
from datetime import datetime, timedelta


def get_supplier_stats(db: Session, phone: str) -> dict | None:
    """Get summary stats for a supplier."""
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if not supplier:
        return None

    total_alerts = db.query(Alert).filter(Alert.supplier_id == supplier.id).count()
    yes_count = db.query(Alert).filter(
        Alert.supplier_id == supplier.id,
        Alert.response == "YES"
    ).count()
    no_count = db.query(Alert).filter(
        Alert.supplier_id == supplier.id,
        Alert.response == "NO"
    ).count()

    return {
        "name": supplier.name or "N/A",
        "district": supplier.district,
        "categories": supplier.categories,
        "active": supplier.active,
        "joined_at": supplier.joined_at,
        "total_alerts": total_alerts,
        "yes_replies": yes_count,
        "no_replies": no_count,
        "pending": total_alerts - yes_count - no_count,
    }


def get_open_tenders(db: Session, category: str = None) -> list:
    """Get tenders with deadlines still in the future."""
    query = db.query(Tender).filter(Tender.deadline > datetime.utcnow())
    if category:
        query = query.filter(Tender.category == category)
    return query.order_by(Tender.deadline.asc()).all()


def get_recent_alerts(db: Session, supplier_id, days: int = 7) -> list:
    """Get recent alerts for a supplier in the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    return (
        db.query(Alert)
        .filter(Alert.supplier_id == supplier_id, Alert.sent_at >= since)
        .order_by(Alert.sent_at.desc())
        .all()
    )
