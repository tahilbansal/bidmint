"""
Tender listing and detail endpoints.

GET  /admin/tenders           — paginated list, filterable by source / category / date
GET  /admin/tenders/{id}      — full tender detail including alerts sent for it
"""
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from admin.auth import require_admin_key
from database.connection import get_db
from database.models import Alert, Tender

router = APIRouter(prefix="/tenders", tags=["Admin – Tenders"])


def _to_dict(t: Tender) -> dict:
    return {
        "id": t.id,
        "source": t.source,
        "title": t.title,
        "title_hindi": t.title_hindi,
        "department": t.department,
        "location": t.location,
        "category": t.category,
        "quantity": t.quantity,
        "quantity_kg": t.quantity_kg,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "ai_confidence": t.ai_confidence,
        "red_flags": t.red_flags,
        "alerted_count": t.alerted_count,
        "scraped_at": t.scraped_at.isoformat() if t.scraped_at else None,
        "whatsapp_summary": t.whatsapp_summary,
    }


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_tenders(
    source: Optional[str] = Query(None, description="gem | cppp | punjab_state"),
    category: Optional[str] = Query(None, description="rice | wheat | pulses | oils | sugar | dairy | spices"),
    since: Optional[date] = Query(None, description="ISO date — only tenders scraped on or after this date"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Tender)
    if source:
        q = q.filter(Tender.source == source)
    if category:
        q = q.filter(Tender.category == category)
    if since:
        q = q.filter(Tender.scraped_at >= datetime.combine(since, datetime.min.time()))

    total = q.count()
    items = q.order_by(Tender.scraped_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_to_dict(t) for t in items],
    }


@router.get("/{tender_id}", dependencies=[Depends(require_admin_key)])
async def get_tender(tender_id: str, db: Session = Depends(get_db)):
    t = db.query(Tender).filter(Tender.id == tender_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tender not found")

    alerts = db.query(Alert).filter(Alert.tender_id == tender_id).all()
    result = _to_dict(t)
    result["alerts"] = [
        {
            "supplier_id": str(a.supplier_id),
            "match_score": a.match_score,
            "sent_at": a.sent_at.isoformat() if a.sent_at else None,
            "response": a.response,
            "responded_at": a.responded_at.isoformat() if a.responded_at else None,
        }
        for a in alerts
    ]
    return result
