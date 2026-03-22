"""
Supplier management — CRUD endpoints.

POST   /admin/suppliers              — add a new supplier
GET    /admin/suppliers              — list all (pass ?active_only=true to filter)
PATCH  /admin/suppliers/{phone}      — update name / district / categories / active flag
DELETE /admin/suppliers/{phone}      — deactivate (sets active=False, does not hard-delete)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from admin.auth import require_admin_key
from database.connection import get_db
from database.models import Supplier

router = APIRouter(prefix="/suppliers", tags=["Admin – Suppliers"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    whatsapp: str          # E.164 without leading +, e.g. 919876543210
    name: Optional[str] = None
    district: str          # e.g. patiala
    categories: str        # comma-separated: "rice,wheat,pulses"

    @field_validator("whatsapp")
    @classmethod
    def validate_whatsapp(cls, v: str) -> str:
        v = v.strip().lstrip("+")
        if not v.isdigit() or len(v) < 10:
            raise ValueError("whatsapp must be a numeric E.164 number, e.g. 919876543210")
        return v


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    district: Optional[str] = None
    categories: Optional[str] = None
    active: Optional[bool] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_dict(s: Supplier) -> dict:
    return {
        "id": str(s.id),
        "whatsapp": s.whatsapp,
        "name": s.name,
        "district": s.district,
        "categories": s.categories,
        "active": s.active,
        "joined_at": s.joined_at.isoformat() if s.joined_at else None,
        "last_active": s.last_active.isoformat() if s.last_active else None,
    }


def _get_or_404(phone: str, db: Session) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if not supplier:
        raise HTTPException(status_code=404, detail=f"Supplier {phone} not found")
    return supplier


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(require_admin_key)])
async def list_suppliers(
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(Supplier)
    if active_only:
        q = q.filter(Supplier.active == True)  # noqa: E712
    suppliers = q.order_by(Supplier.joined_at.desc()).all()
    return {"total": len(suppliers), "suppliers": [_to_dict(s) for s in suppliers]}


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_key)])
async def create_supplier(body: SupplierCreate, db: Session = Depends(get_db)):
    if db.query(Supplier).filter(Supplier.whatsapp == body.whatsapp).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supplier {body.whatsapp} already exists",
        )
    supplier = Supplier(
        whatsapp=body.whatsapp,
        name=body.name,
        district=body.district.lower().strip(),
        categories=body.categories.lower().strip(),
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return _to_dict(supplier)


@router.patch("/{phone}", dependencies=[Depends(require_admin_key)])
async def update_supplier(phone: str, body: SupplierUpdate, db: Session = Depends(get_db)):
    supplier = _get_or_404(phone, db)
    if body.name is not None:
        supplier.name = body.name
    if body.district is not None:
        supplier.district = body.district.lower().strip()
    if body.categories is not None:
        supplier.categories = body.categories.lower().strip()
    if body.active is not None:
        supplier.active = body.active
    supplier.last_active = datetime.utcnow()
    db.commit()
    db.refresh(supplier)
    return _to_dict(supplier)


@router.delete("/{phone}", dependencies=[Depends(require_admin_key)])
async def deactivate_supplier(phone: str, db: Session = Depends(get_db)):
    supplier = _get_or_404(phone, db)
    supplier.active = False
    db.commit()
    return {"status": "deactivated", "whatsapp": phone}
