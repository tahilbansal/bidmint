from database.connection import SessionLocal
from database.models import Supplier, Alert, Tender
from whatsapp.sender import (
    send_tender_details, send_welcome,
    send_mandi_prices, send_help_menu
)
from scraper.agmarknet import fetch_punjab_prices
from datetime import datetime


async def handle_inbound(phone: str, message: str):
    """
    Route inbound WhatsApp message to correct handler.
    phone: 919XXXXXXXXX format
    """
    msg = message.strip().upper()
    db = SessionLocal()

    try:
        if msg.startswith("JOIN"):
            await _handle_join(phone, msg, db)
        elif msg == "YES":
            await _handle_yes(phone, db)
        elif msg == "NO":
            await _handle_no(phone, db)
        elif msg == "PRICE":
            supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
            cats = supplier.categories if supplier else "rice,wheat"
            prices = await fetch_punjab_prices()
            await send_mandi_prices(phone, cats, prices)
        elif msg == "HELP":
            await send_help_menu(phone)
        elif msg == "STOP":
            await _handle_stop(phone, db)
        elif msg.startswith("ADD "):
            await _handle_add_category(phone, msg, db)
        elif msg.startswith("REMOVE "):
            await _handle_remove_category(phone, msg, db)
        else:
            await send_help_menu(phone)
    finally:
        db.close()


async def _handle_join(phone: str, msg: str, db):
    """Register new supplier or update existing one."""
    parts = msg.split()
    category = parts[1].lower() if len(parts) > 1 else "general"
    district = parts[2].lower() if len(parts) > 2 else "punjab"

    existing = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if existing:
        existing.categories = category
        existing.district = district
        existing.active = True
        existing.last_active = datetime.utcnow()
    else:
        db.add(Supplier(
            whatsapp=phone,
            categories=category,
            district=district
        ))
    db.commit()
    await send_welcome(phone, category, district)


async def _handle_yes(phone: str, db):
    """Handle YES reply — send full tender details for most recent unanswered alert."""
    alert = (
        db.query(Alert)
        .join(Supplier, Alert.supplier_id == Supplier.id)
        .filter(Supplier.whatsapp == phone)
        .filter(Alert.response == None)  # noqa: E711
        .order_by(Alert.sent_at.desc())
        .first()
    )
    if alert:
        alert.response = "YES"
        alert.responded_at = datetime.utcnow()
        db.commit()
        tender = db.query(Tender).filter(Tender.id == alert.tender_id).first()
        if tender:
            await send_tender_details(phone, tender)

    # Update last_active
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        supplier.last_active = datetime.utcnow()
        db.commit()


async def _handle_no(phone: str, db):
    """Handle NO reply — log decline for most recent unanswered alert."""
    alert = (
        db.query(Alert)
        .join(Supplier, Alert.supplier_id == Supplier.id)
        .filter(Supplier.whatsapp == phone)
        .filter(Alert.response == None)  # noqa: E711
        .order_by(Alert.sent_at.desc())
        .first()
    )
    if alert:
        alert.response = "NO"
        alert.responded_at = datetime.utcnow()
        db.commit()


async def _handle_stop(phone: str, db):
    """Deactivate supplier immediately."""
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        supplier.active = False
        db.commit()


async def _handle_add_category(phone: str, msg: str, db):
    """Add a new product category to supplier's profile."""
    parts = msg.split()
    if len(parts) < 2:
        return
    new_cat = parts[1].lower()
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        existing_cats = [c.strip() for c in supplier.categories.split(",")]
        if new_cat not in existing_cats:
            existing_cats.append(new_cat)
            supplier.categories = ",".join(existing_cats)
            db.commit()


async def _handle_remove_category(phone: str, msg: str, db):
    """Remove a product category from supplier's profile."""
    parts = msg.split()
    if len(parts) < 2:
        return
    remove_cat = parts[1].lower()
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        existing_cats = [c.strip() for c in supplier.categories.split(",")]
        if remove_cat in existing_cats:
            existing_cats.remove(remove_cat)
            if existing_cats:
                supplier.categories = ",".join(existing_cats)
            else:
                supplier.categories = "general"
            db.commit()
